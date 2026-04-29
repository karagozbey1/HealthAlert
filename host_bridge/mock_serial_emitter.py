from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time

import click

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mock_emitter")

SCENARIOS = {
    "normal":               {"hr": (68, 76), "spo2": (97, 99), "acc": 0.02, "gyro": 0.5, "sq": 0.92},
    "elevated_hr":          {"hr": (95, 115), "spo2": (96, 97), "acc": 0.08, "gyro": 2.0, "sq": 0.80},
    "low_spo2":             {"hr": (72, 82), "spo2": (86, 91), "acc": 0.03, "gyro": 1.0, "sq": 0.75},
    "motion_instability":   {"hr": (78, 88), "spo2": (95, 97), "acc": 0.40, "gyro": 15.0, "sq": 0.55},
    "warning_state":        {"hr": (118, 130), "spo2": (93, 95), "acc": 0.15, "gyro": 4.0, "sq": 0.70},
    "critical_state":       {"hr": (130, 145), "spo2": (83, 88), "acc": 0.25, "gyro": 6.0, "sq": 0.55},
    "recovery_state":       {"hr": (74, 84), "spo2": (95, 98), "acc": 0.04, "gyro": 1.5, "sq": 0.85},
}

DEVICE_ID = "ha-esp32-mock"

def _noise(amp: float) -> float:
    return random.uniform(-amp, amp)

def _generate_packet(seq: int, scenario_name: str, t: float) -> dict:
    s = SCENARIOS[scenario_name]
    hr_lo, hr_hi = s["hr"]
    spo2_lo, spo2_hi = s["spo2"]
    acc_amp = s["acc"]
    gyro_amp = s["gyro"]
    sq = s["sq"]

    hr = random.uniform(hr_lo, hr_hi) + 2.0 * math.sin(t * 0.15)
    spo2 = random.uniform(spo2_lo, spo2_hi) + 0.3 * math.sin(t * 0.08)
    spo2 = max(0, min(100, spo2))

    ir_base = 75000 + _noise(5000)
    red_base = 70000 + _noise(5000)

    return {
        "device_id": DEVICE_ID,
        "timestamp_ms": int(time.time() * 1000),
        "mode": "mock",
        "packet_seq": seq,
        "accel_x": round(acc_amp * math.sin(t * 1.1) + _noise(acc_amp), 3),
        "accel_y": round(acc_amp * math.cos(t * 0.9) + _noise(acc_amp), 3),
        "accel_z": round(1.0 + acc_amp * math.sin(t * 0.7) + _noise(acc_amp), 3),
        "gyro_x": round(_noise(gyro_amp), 2),
        "gyro_y": round(_noise(gyro_amp), 2),
        "gyro_z": round(_noise(gyro_amp), 2),
        "red_value": int(red_base),
        "ir_value": int(ir_base),
        "heart_rate": round(hr, 1),
        "spo2": round(spo2, 1),
        "signal_quality": round(sq + _noise(0.05), 2),
        "imu_ok": True,
        "ppg_ok": True,
        "hr_valid": sq > 0.3,
        "spo2_valid": sq > 0.4,
        "finger_detected": True,
        "state_hint": scenario_name,
    }

@click.command()
@click.option("--scenario", default="normal", type=click.Choice(list(SCENARIOS.keys())),
              help="Mock scenario")
@click.option("--interval", default=1.0, help="Packet interval in seconds")
@click.option("--count", default=0, help="Number of packets (0 = infinite)")
@click.option("--cycle", is_flag=True, help="Auto-cycle through all scenarios")
@click.option("--cycle-packets", default=30, help="Packets per scenario in cycle mode")
@click.option("--tcp-port", default=None, type=int,
              help="Serve packets over TCP on this port (for BLE tool testing). "
                   "If not set, prints to stdout.")
def main(scenario: str, interval: float, count: int, cycle: bool, cycle_packets: int,
         tcp_port: int | None) -> None:
    if tcp_port:
        asyncio.run(_run_tcp_server(tcp_port, scenario, interval, count, cycle, cycle_packets))
    else:
        _run_stdout(scenario, interval, count, cycle, cycle_packets)

def _run_stdout(scenario: str, interval: float, count: int, cycle: bool, cycle_packets: int) -> None:
    scenario_list = list(SCENARIOS.keys())
    current_scenario = scenario
    seq = 0
    t = 0.0
    cycle_counter = 0
    cycle_index = scenario_list.index(scenario)

    logger.info("Mock emitter started (stdout). Scenario=%s  Interval=%.1fs", current_scenario, interval)

    try:
        while True:
            pkt = _generate_packet(seq, current_scenario, t)
            print(json.dumps(pkt), flush=True)
            seq += 1
            t += interval
            cycle_counter += 1

            if cycle and cycle_counter >= cycle_packets:
                cycle_counter = 0
                cycle_index = (cycle_index + 1) % len(scenario_list)
                current_scenario = scenario_list[cycle_index]
                logger.info("Scenario → %s", current_scenario)

            if count > 0 and seq >= count:
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("Stopped after %d packets.", seq)

async def _run_tcp_server(
    port: int,
    scenario: str,
    interval: float,
    count: int,
    cycle: bool,
    cycle_packets: int,
) -> None:
    clients: list[asyncio.StreamWriter] = []

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        addr = writer.get_extra_info("peername")
        logger.info("Client connected: %s", addr)
        clients.append(writer)
        try:
            await reader.read()
        finally:
            if writer in clients:
                clients.remove(writer)
            writer.close()
            logger.info("Client disconnected: %s", addr)

    server = await asyncio.start_server(handle_client, "127.0.0.1", port)
    logger.info("Mock TCP server listening on port %d (Ctrl+C to stop)", port)
    logger.info("Connect: python serial_reader.py --mock-tcp-host localhost --mock-tcp-port %d", port)

    scenario_list = list(SCENARIOS.keys())
    current_scenario = scenario
    seq = 0
    t = 0.0
    cycle_counter = 0
    cycle_index = scenario_list.index(scenario)

    async with server:
        try:
            while True:
                pkt = _generate_packet(seq, current_scenario, t)
                line = (json.dumps(pkt) + "\n").encode("utf-8")

                dead = []
                for writer in list(clients):
                    try:
                        writer.write(line)
                        await writer.drain()
                    except Exception:
                        dead.append(writer)
                for w in dead:
                    if w in clients:
                        clients.remove(w)

                seq += 1
                t += interval
                cycle_counter += 1

                if cycle and cycle_counter >= cycle_packets:
                    cycle_counter = 0
                    cycle_index = (cycle_index + 1) % len(scenario_list)
                    current_scenario = scenario_list[cycle_index]
                    logger.info("Scenario → %s", current_scenario)

                if count > 0 and seq >= count:
                    break

                await asyncio.sleep(interval)

        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            logger.info("Stopped after %d packets.", seq)

if __name__ == "__main__":
    main()
