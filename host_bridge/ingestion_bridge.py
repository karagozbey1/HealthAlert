from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections import deque

import click
import requests
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from packet_schema import validate_packet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ble_bridge")

NUS_TX_UUID = "6e400003-b5b3-f393-e0a9-e50e24dcca9e"

DEFAULT_INGEST_PATH = "/ingest/device-packet"
MAX_RETRY_QUEUE = 50

async def _scan_for_device(name: str, timeout: float = 10.0) -> str:
    logger.info("Scanning for BLE device '%s' (%.0fs)...", name, timeout)
    device = await BleakScanner.find_device_by_name(name, timeout=timeout)
    if device is None:
        logger.error("Device '%s' not found. Ensure it is powered on and advertising.", name)
        sys.exit(1)
    logger.info("Found: %s  [%s]", device.name, device.address)
    return device.address

def _post_packet(
    session: requests.Session,
    url: str,
    data: dict,
    token: str | None,
    timeout: float = 5.0,
) -> bool:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = session.post(url, json=data, headers=headers, timeout=timeout)
        if resp.status_code in (200, 201):
            return True
        logger.warning("Backend returned %d: %s", resp.status_code, resp.text[:200])
        return False
    except requests.RequestException as exc:
        logger.warning("HTTP error: %s", exc)
        return False

def _make_forward_handler(session, ingest_url, token, quiet, retry_queue, counters):
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
            if not line or not line.startswith("{"):
                if line and not quiet:
                    print(f"  [FW] {line}")
                continue

            try:
                pkt = validate_packet(json.loads(line))
                pkt_dict = pkt.model_dump()
            except Exception as exc:
                logger.warning("Bad packet: %s", exc)
                counters["failed"] += 1
                return

            while retry_queue:
                if _post_packet(session, ingest_url, retry_queue[0], token):
                    retry_queue.popleft()
                    counters["sent"] += 1
                else:
                    break

            if _post_packet(session, ingest_url, pkt_dict, token):
                counters["sent"] += 1
                if not quiet:
                    logger.info("→ seq=%d OK (total=%d)", pkt.packet_seq, counters["sent"])
            else:
                retry_queue.append(pkt_dict)
                counters["failed"] += 1
                if not quiet:
                    logger.info("→ seq=%d QUEUED (queue=%d)", pkt.packet_seq, len(retry_queue))

    return on_notification

async def _run_ble(address: str, ingest_url: str, token: str | None, quiet: bool) -> None:
    session = requests.Session()
    retry_queue: deque[dict] = deque(maxlen=MAX_RETRY_QUEUE)
    counters = {"sent": 0, "failed": 0}
    handler = _make_forward_handler(session, ingest_url, token, quiet, retry_queue, counters)

    logger.info("Connecting to %s ...", address)
    async with BleakClient(address, timeout=15.0) as client:
        logger.info("Connected. Forwarding to: %s", ingest_url)
        await client.start_notify(NUS_TX_UUID, handler)
        logger.info("Listening... (Ctrl+C to stop)")
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
                "Stopped. Sent=%d  Failed=%d  Queued=%d",
                counters["sent"], counters["failed"], len(retry_queue),
            )
            session.close()

async def _run_mock_tcp(host: str, port: int, ingest_url: str, token: str | None, quiet: bool) -> None:
    session = requests.Session()
    retry_queue: deque[dict] = deque(maxlen=MAX_RETRY_QUEUE)
    counters = {"sent": 0, "failed": 0}

    logger.info("Connecting to mock TCP server at %s:%d ...", host, port)
    reader, _ = await asyncio.open_connection(host, port)
    logger.info("Mock TCP connected. Forwarding to: %s", ingest_url)
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
                pkt_dict = pkt.model_dump()
            except Exception as exc:
                logger.warning("Bad packet: %s", exc)
                counters["failed"] += 1
                continue

            while retry_queue:
                if _post_packet(session, ingest_url, retry_queue[0], token):
                    retry_queue.popleft()
                    counters["sent"] += 1
                else:
                    break

            if _post_packet(session, ingest_url, pkt_dict, token):
                counters["sent"] += 1
                if not quiet:
                    logger.info("→ seq=%d OK (total=%d)", pkt.packet_seq, counters["sent"])
            else:
                retry_queue.append(pkt_dict)
                counters["failed"] += 1
    except asyncio.CancelledError:
        pass
    finally:
        logger.info(
            "Stopped. Sent=%d  Failed=%d  Queued=%d",
            counters["sent"], counters["failed"], len(retry_queue),
        )
        session.close()

@click.command()
@click.option("--device", default="HealthAlert-ESP32", help="BLE device name to scan for")
@click.option("--address", default=None, help="BLE MAC address (skips scan)")
@click.option("--backend", default="http://localhost:8000", help="Backend base URL")
@click.option("--token", default=None, help="JWT bearer token for auth")
@click.option("--path", default=DEFAULT_INGEST_PATH, help="Ingestion endpoint path")
@click.option("--quiet", is_flag=True, help="Suppress per-packet logging")
@click.option("--mock-tcp-host", default=None, help="Use mock TCP server instead of BLE (local testing)")
@click.option("--mock-tcp-port", default=9001, help="Mock TCP server port")
def main(
    device: str,
    address: str | None,
    backend: str,
    token: str | None,
    path: str,
    quiet: bool,
    mock_tcp_host: str | None,
    mock_tcp_port: int,
) -> None:
    ingest_url = backend.rstrip("/") + path

    async def run():
        try:
            if mock_tcp_host:
                await _run_mock_tcp(mock_tcp_host, mock_tcp_port, ingest_url, token, quiet)
            else:
                addr = address or await _scan_for_device(device)
                await _run_ble(addr, ingest_url, token, quiet)
        except BleakError as exc:
            logger.error("BLE error: %s", exc)
        except KeyboardInterrupt:
            pass

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
@click.option("--token", default=None, help="JWT bearer token for auth")
@click.option("--path", default=DEFAULT_INGEST_PATH, help="Ingestion endpoint path")
@click.option("--quiet", is_flag=True, help="Suppress per-packet logging")
def main(port: str, baud: int, backend: str, token: str | None, path: str, quiet: bool) -> None:
    ingest_url = backend.rstrip("/") + path
    logger.info("Forwarding to: %s", ingest_url)

    ser = _open_serial(port, baud)
    session = requests.Session()
    retry_queue: deque[dict] = deque(maxlen=MAX_RETRY_QUEUE)

    sent = 0
    failed = 0

    try:
        while True:
            while retry_queue:
                queued = retry_queue[0]
                if _post_packet(session, ingest_url, queued, token):
                    retry_queue.popleft()
                    sent += 1
                else:
                    break

            try:
                raw = ser.readline()
            except serial.SerialException:
                logger.warning("Serial disconnected. Reconnecting...")
                ser.close()
                time.sleep(2)
                ser = _open_serial(port, baud)
                continue

            if not raw:
                continue

            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue

            if not line.startswith("{"):
                if line and not quiet:
                    print(f"  [FW] {line}")
                continue

            try:
                data = json.loads(line)
                pkt = validate_packet(data)
                pkt_dict = pkt.model_dump()
            except Exception as exc:
                logger.warning("Bad packet: %s", exc)
                failed += 1
                continue

            if _post_packet(session, ingest_url, pkt_dict, token):
                sent += 1
                if not quiet:
                    logger.info("→ seq=%d OK (total=%d)", pkt.packet_seq, sent)
            else:
                retry_queue.append(pkt_dict)
                failed += 1
                if not quiet:
                    logger.info("→ seq=%d QUEUED (queue=%d)", pkt.packet_seq, len(retry_queue))

    except KeyboardInterrupt:
        logger.info("Stopped. Sent=%d  Failed=%d  Queued=%d", sent, failed, len(retry_queue))
    finally:
        ser.close()
        session.close()

if __name__ == "__main__":
    main()
