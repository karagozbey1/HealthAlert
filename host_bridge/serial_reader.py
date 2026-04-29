
from __future__ import annotations

import asyncio
import csv
import json
import logging
import sys
from pathlib import Path

import click
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from packet_schema import DevicePacketSchema, validate_packet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ble_reader")

NUS_SERVICE_UUID = "6e400001-b5b3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID      = "6e400003-b5b3-f393-e0a9-e50e24dcca9e"

CSV_FIELDS = [
    "device_id", "timestamp_ms", "mode", "packet_seq",
    "accel_x", "accel_y", "accel_z",
    "gyro_x", "gyro_y", "gyro_z",
    "red_value", "ir_value", "heart_rate", "spo2", "signal_quality",
    "imu_ok", "ppg_ok", "hr_valid", "spo2_valid", "finger_detected",
    "state_hint",
]

_partial_buf: str = ""

async def _scan_for_device(name: str, timeout: float = 10.0) -> str:
    logger.info("Scanning for BLE device '%s' (%.0fs timeout)...", name, timeout)
    device = await BleakScanner.find_device_by_name(name, timeout=timeout)
    if device is None:
        logger.error("Device '%s' not found. Ensure it is powered on and advertising.", name)
        sys.exit(1)
    logger.info("Found: %s  [%s]", device.name, device.address)
    return device.address

class PacketWriter:

    def __init__(self, path: Path | None, fmt: str):
        self._file = None
        self._csv_writer = None
        self._fmt = fmt
        if path:
            mode = "a" if path.exists() else "w"
            self._file = open(path, mode, newline="", encoding="utf-8")
            if fmt == "csv" and mode == "w":
                self._csv_writer = csv.DictWriter(self._file, fieldnames=CSV_FIELDS)
                self._csv_writer.writeheader()
            elif fmt == "csv":
                self._csv_writer = csv.DictWriter(self._file, fieldnames=CSV_FIELDS)

    def write(self, pkt: DevicePacketSchema) -> None:
        if self._file is None:
            return
        data = pkt.model_dump()
        if self._fmt == "jsonl":
            self._file.write(json.dumps(data) + "\n")
        elif self._csv_writer:
            self._csv_writer.writerow(data)
        self._file.flush()

    def close(self) -> None:
        if self._file:
            self._file.close()

def _pretty_print(pkt: DevicePacketSchema) -> None:
    hr_str = f"{pkt.heart_rate:.1f}" if pkt.hr_valid else "---"
    spo2_str = f"{pkt.spo2:.1f}" if pkt.spo2_valid else "---"
    finger = "F" if pkt.finger_detected else "-"
    mode = pkt.mode[0].upper()
    imu = "I" if pkt.imu_ok else "!"
    ppg = "P" if pkt.ppg_ok else "!"
    logger.info(
        "[%s] seq=%d  HR=%s  SpO2=%s  SQ=%.2f  %s  %s%s  ax=%.2f ay=%.2f az=%.2f  | %s",
        mode, pkt.packet_seq, hr_str, spo2_str, pkt.signal_quality,
        finger, imu, ppg, pkt.accel_x, pkt.accel_y, pkt.accel_z, pkt.state_hint,
    )

def _make_notification_handler(writer: PacketWriter, quiet: bool, counters: dict):
    partial_buf = [""]

    def on_notification(sender, data: bytearray) -> None:
        try:
            chunk = data.decode("utf-8", errors="replace")
        except Exception:
            return

        partial_buf[0] += chunk

        while "\n" in partial_buf[0]:
            line, partial_buf[0] = partial_buf[0].split("\n", 1)
            line = line.strip()
            if not line:
                continue
            if not line.startswith("{"):
                counters["fw_lines"] += 1
                if not quiet:
                    print(f"  [FW] {line}")
                continue
            try:
                pkt = validate_packet(json.loads(line))
                counters["valid"] += 1
                if not quiet:
                    _pretty_print(pkt)
                writer.write(pkt)
            except Exception as exc:
                counters["invalid"] += 1
                logger.warning("Invalid packet: %s", exc)

    return on_notification

async def _run_ble(address: str, writer: PacketWriter, quiet: bool) -> None:
    counters = {"valid": 0, "invalid": 0, "fw_lines": 0}
    handler = _make_notification_handler(writer, quiet, counters)

    logger.info("Connecting to %s ...", address)
    async with BleakClient(address, timeout=15.0) as client:
        logger.info("Connected. Subscribing to NUS TX (BLE UART) ...")
        await client.start_notify(NUS_TX_UUID, handler)
        logger.info("Listening for packets... (Ctrl+C to stop)")
        try:
            while client.is_connected:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            try:
                await client.stop_notify(NUS_TX_UUID)
            except Exception:
                pass
            logger.info(
                "Disconnected. Valid=%d  Invalid=%d  FW-lines=%d",
                counters["valid"], counters["invalid"], counters["fw_lines"],
            )

async def _run_mock_tcp(host: str, port: int, writer: PacketWriter, quiet: bool) -> None:
    counters = {"valid": 0, "invalid": 0}
    logger.info("Connecting to mock TCP server at %s:%d ...", host, port)
    reader, _ = await asyncio.open_connection(host, port)
    logger.info("Mock TCP connected. Listening for packets... (Ctrl+C to stop)")
    try:
        while True:
            raw = await reader.readline()
            if not raw:
                logger.warning("Mock server closed connection.")
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("{"):
                continue
            try:
                pkt = validate_packet(json.loads(line))
                counters["valid"] += 1
                if not quiet:
                    _pretty_print(pkt)
                writer.write(pkt)
            except Exception as exc:
                counters["invalid"] += 1
                logger.warning("Invalid packet: %s", exc)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Stopped. Valid=%d  Invalid=%d", counters["valid"], counters["invalid"])

@click.command()
@click.option("--device", default="HealthAlert-ESP32", help="BLE device name to scan for")
@click.option("--address", default=None, help="BLE MAC address (skips scan, e.g. AA:BB:CC:DD:EE:FF)")
@click.option("--output", default=None, type=click.Path(), help="Output file path")
@click.option("--format", "fmt", default="jsonl", type=click.Choice(["jsonl", "csv"]), help="Output format")
@click.option("--quiet", is_flag=True, help="Suppress per-packet console output")
@click.option("--mock-tcp-host", default=None, help="Use mock TCP server instead of BLE (local testing)")
@click.option("--mock-tcp-port", default=9001, help="Mock TCP server port")
def main(
    device: str,
    address: str | None,
    output: str | None,
    fmt: str,
    quiet: bool,
    mock_tcp_host: str | None,
    mock_tcp_port: int,
) -> None:
    out_path = Path(output) if output else None
    writer = PacketWriter(out_path, fmt)

    async def run():
        try:
            if mock_tcp_host:
                await _run_mock_tcp(mock_tcp_host, mock_tcp_port, writer, quiet)
            else:
                addr = address or await _scan_for_device(device)
                await _run_ble(addr, writer, quiet)
        except BleakError as exc:
            logger.error("BLE error: %s", exc)
        except KeyboardInterrupt:
            pass
        finally:
            writer.close()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
