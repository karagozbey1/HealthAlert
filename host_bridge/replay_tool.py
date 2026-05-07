from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path

import click
import requests

from packet_schema import DevicePacketSchema, validate_packet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("replay_tool")

DEFAULT_INGEST_PATH = "/ingest/device-packet"

BOOL_MAP = {"true": True, "false": False, "True": True, "False": False, "1": True, "0": False}
INT_FIELDS = {"timestamp_ms", "packet_seq", "red_value", "ir_value"}
FLOAT_FIELDS = {"accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z",
                "heart_rate", "spo2", "signal_quality"}
BOOL_FIELDS = {"imu_ok", "ppg_ok", "hr_valid", "spo2_valid", "finger_detected"}

# JSONL yakalama dosyasini paket listesine cevirir.
def _load_jsonl(path: Path) -> list[dict]:
    packets = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                packets.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("Line %d: JSON error – %s", lineno, exc)
    return packets

# CSV yakalama dosyasini tip donusumleriyle yukler.
def _load_csv(path: Path) -> list[dict]:
    packets = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for k in INT_FIELDS:
                if k in row:
                    row[k] = int(row[k])
            for k in FLOAT_FIELDS:
                if k in row:
                    row[k] = float(row[k])
            for k in BOOL_FIELDS:
                if k in row:
                    row[k] = BOOL_MAP.get(row[k], False)
            packets.append(row)
    return packets

# Dosya uzantisina gore uygun yukleyiciyi secer.
def _load_packets(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _load_csv(path)
    return _load_jsonl(path)

# Kaydedilmis paketleri sirayla backend'e tekrar oynatir.
@click.command()
@click.option("--file", "filepath", required=True, type=click.Path(exists=True), help="Capture file (JSONL or CSV)")
@click.option("--backend", default="http://localhost:8000", help="Backend base URL")
@click.option("--token", default=None, help="JWT bearer token")
@click.option("--path", default=DEFAULT_INGEST_PATH, help="Ingestion endpoint path")
@click.option("--speed", default=1.0, help="Replay speed multiplier (2.0 = 2x faster)")
@click.option("--interval", default=1.0, help="Default interval between packets (seconds)")
@click.option("--dry-run", is_flag=True, help="Validate packets without sending")
def main(filepath: str, backend: str, token: str | None, path: str,
         speed: float, interval: float, dry_run: bool) -> None:
    file_path = Path(filepath)
    raw_packets = _load_packets(file_path)
    logger.info("Loaded %d packets from %s", len(raw_packets), file_path.name)

    if not raw_packets:
        logger.error("No packets found.")
        return

    ingest_url = backend.rstrip("/") + path
    session = requests.Session()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    sent = 0
    errors = 0
    prev_ts = None

    for i, raw in enumerate(raw_packets):
        try:
            pkt = validate_packet(raw)
        except Exception as exc:
            logger.warning("Packet %d invalid: %s", i, exc)
            errors += 1
            continue

        delay = interval / speed
        if prev_ts is not None and pkt.timestamp_ms > prev_ts:
            delta_ms = pkt.timestamp_ms - prev_ts
            delay = (delta_ms / 1000.0) / speed
            if delay > 10.0:
                delay = 10.0

        if dry_run:
            logger.info("[DRY] Packet %d seq=%d valid ✓", i, pkt.packet_seq)
        else:
            if i > 0:
                time.sleep(delay)

            pkt_dict = pkt.model_dump()
            try:
                resp = session.post(ingest_url, json=pkt_dict, headers=headers, timeout=5.0)
                if resp.status_code in (200, 201):
                    sent += 1
                    logger.info("→ %d/%d seq=%d OK", i + 1, len(raw_packets), pkt.packet_seq)
                else:
                    errors += 1
                    logger.warning("→ %d/%d seq=%d HTTP %d", i + 1, len(raw_packets),
                                   pkt.packet_seq, resp.status_code)
            except requests.RequestException as exc:
                errors += 1
                logger.warning("→ %d/%d seq=%d ERROR: %s", i + 1, len(raw_packets),
                               pkt.packet_seq, exc)

        prev_ts = pkt.timestamp_ms

    logger.info("Replay complete. Sent=%d  Errors=%d  Total=%d", sent, errors, len(raw_packets))
    session.close()

if __name__ == "__main__":
    main()
