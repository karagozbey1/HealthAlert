from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Optional

import click
import requests

from packet_schema import (
    ModelWindowPayload,
    RawSensorSample,
    validate_model_window_payload,
    validate_raw_sample,
)

logger = logging.getLogger("model_window_collector")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

DEFAULT_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
DEFAULT_RAW_SAMPLE_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


@dataclass
class DeviceBufferState:
    samples: Deque[RawSensorSample] = field(default_factory=deque)
    missing_samples: int = 0
    last_sample_seq: Optional[int] = None


class ModelWindowCollector:
    def __init__(
        self,
        *,
        window_size: int = 200,
        sample_rate: int = 50,
        source: str = "mock",
    ) -> None:
        self.window_size = window_size
        self.sample_rate = sample_rate
        self.source = source
        self._buffers: Dict[str, DeviceBufferState] = defaultdict(DeviceBufferState)

    def add_sample(self, sample: RawSensorSample) -> Optional[ModelWindowPayload]:
        state = self._buffers[sample.device_id]
        if state.last_sample_seq is not None and sample.sample_seq > state.last_sample_seq + 1:
            state.missing_samples += sample.sample_seq - state.last_sample_seq - 1
        state.last_sample_seq = sample.sample_seq

        state.samples.append(sample)
        if len(state.samples) < self.window_size:
            return None

        window_samples = [state.samples.popleft() for _ in range(self.window_size)]
        payload = self._to_window_payload(window_samples, state.missing_samples)
        state.missing_samples = 0
        return payload

    def _to_window_payload(
        self, samples: List[RawSensorSample], missing_sample_count: int
    ) -> ModelWindowPayload:
        start_ts = samples[0].timestamp_ms
        end_ts = samples[-1].timestamp_ms
        duration_ms = max(0, end_ts - start_ts)
        effective_rate = (
            (len(samples) / (duration_ms / 1000.0)) if duration_ms > 0 else 0.0
        )

        imu_ok_ratio = sum(1 for s in samples if s.imu_ok) / len(samples)
        ppg_ok_ratio = sum(1 for s in samples if s.ppg_ok) / len(samples)
        finger_ratio = sum(1 for s in samples if s.finger_detected) / len(samples)
        avg_signal_quality = sum(float(s.signal_quality) for s in samples) / len(samples)
        model_ready = (
            len(samples) == self.window_size
            and abs(effective_rate - self.sample_rate) <= 5.0
            and missing_sample_count == 0
        )

        payload = {
            "device_id": samples[0].device_id,
            "mode": samples[0].mode,
            "window_seq": samples[-1].window_seq,
            "sample_rate_hz": samples[0].sample_rate_hz,
            "sample_count": len(samples),
            "window_duration_ms": duration_ms,
            "timestamp_start_ms": start_ts,
            "timestamp_end_ms": end_ts,
            "imu_samples": [
                [s.accel_x, s.accel_y, s.accel_z, s.gyro_x, s.gyro_y, s.gyro_z]
                for s in samples
            ],
            "ppg_samples": [[float(s.red_value), float(s.ir_value)] for s in samples],
            "quality_summary": {
                "sample_count": len(samples),
                "expected_sample_count": self.window_size,
                "missing_sample_count": missing_sample_count,
                "duration_ms": duration_ms,
                "effective_sample_rate_hz": round(effective_rate, 3),
                "imu_ok_ratio": round(imu_ok_ratio, 4),
                "ppg_ok_ratio": round(ppg_ok_ratio, 4),
                "finger_detected_ratio": round(finger_ratio, 4),
                "avg_signal_quality": round(avg_signal_quality, 4),
                "model_ready": model_ready,
            },
            "latest_vitals": None,
            "source": self.source,
        }
        return validate_model_window_payload(payload)


def _post_model_window(
    *,
    backend: str,
    token: Optional[str],
    payload: ModelWindowPayload,
    timeout: float = 6.0,
) -> tuple[bool, bool]:
    url = backend.rstrip("/") + "/ingest/model-window"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.post(url, json=payload.model_dump(), headers=headers, timeout=timeout)
        if resp.status_code in (200, 201):
            return True, False
        # Validation errors are terminal; do not retry.
        if resp.status_code in (400, 401, 403, 404, 409, 422):
            logger.warning("Dropped window (HTTP %d): %s", resp.status_code, resp.text[:180])
            return False, False
        logger.warning("Temporary backend error HTTP %d", resp.status_code)
        return False, True
    except requests.RequestException as exc:
        logger.warning("Network error while posting model-window: %s", exc)
        return False, True


def _mock_samples(sample_rate: int) -> Iterable[RawSensorSample]:
    device_id = "ha-esp32-001"
    sample_seq = 0
    start = time.time()
    while True:
        t = time.time() - start
        window_seq = sample_seq // 200
        sample = {
            "device_id": device_id,
            "timestamp_ms": int(time.time() * 1000),
            "sample_seq": sample_seq,
            "window_seq": window_seq,
            "sample_rate_hz": sample_rate,
            "mode": "mock",
            "accel_x": round(0.08 * math.sin(t * 2.0) + random.uniform(-0.01, 0.01), 4),
            "accel_y": round(0.08 * math.cos(t * 1.8) + random.uniform(-0.01, 0.01), 4),
            "accel_z": round(1.0 + 0.04 * math.sin(t * 1.2), 4),
            "gyro_x": round(random.uniform(-2.0, 2.0), 3),
            "gyro_y": round(random.uniform(-2.0, 2.0), 3),
            "gyro_z": round(random.uniform(-2.0, 2.0), 3),
            "red_value": int(70000 + random.uniform(-3000, 3000)),
            "ir_value": int(75000 + random.uniform(-3000, 3000)),
            "imu_ok": True,
            "ppg_ok": True,
            "finger_detected": True,
            "signal_quality": round(random.uniform(0.75, 0.95), 3),
        }
        yield validate_raw_sample(sample)
        sample_seq += 1
        time.sleep(1.0 / max(1, sample_rate))


def _replay_samples(path: Path) -> Iterable[RawSensorSample]:
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            raw = line.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
                yield validate_raw_sample(data)
            except Exception as exc:
                logger.warning("Replay line %d ignored: %s", line_no, exc)


async def _ble_samples(
    *,
    device_name: str,
    service_uuid: str,
    raw_char_uuid: str,
) -> Iterable[RawSensorSample]:
    try:
        from bleak import BleakClient, BleakScanner
    except Exception as exc:
        raise RuntimeError(
            "bleak is required for BLE mode. Install with: pip install bleak"
        ) from exc

    queue: asyncio.Queue[RawSensorSample] = asyncio.Queue()
    partial = {"buf": ""}

    def _on_notify(_sender: int, data: bytearray) -> None:
        text = data.decode("utf-8", errors="ignore")
        partial["buf"] += text
        while "\n" in partial["buf"]:
            line, partial["buf"] = partial["buf"].split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                sample = validate_raw_sample(json.loads(line))
                queue.put_nowait(sample)
            except Exception:
                continue

    logger.info("Scanning BLE device: %s", device_name)
    dev = await BleakScanner.find_device_by_name(device_name, timeout=10.0)
    if dev is None:
        raise RuntimeError(f"BLE device not found: {device_name}")

    async with BleakClient(dev) as client:
        logger.info("Connected %s (%s)", dev.name, dev.address)
        await client.start_notify(raw_char_uuid, _on_notify)
        try:
            while client.is_connected:
                yield await queue.get()
        finally:
            await client.stop_notify(raw_char_uuid)


def _log_window(payload: ModelWindowPayload, *, prefix: str = "") -> None:
    q = payload.quality_summary or {}
    logger.info(
        "%swindow_seq=%s count=%s duration_ms=%s effective_hz=%.2f model_ready=%s",
        prefix,
        payload.window_seq,
        payload.sample_count,
        payload.window_duration_ms,
        float(q.get("effective_sample_rate_hz", 0.0)),
        q.get("model_ready"),
    )


@click.command()
@click.option("--device-name", default="HealthAlert", help="BLE device name")
@click.option("--service-uuid", default=DEFAULT_SERVICE_UUID, help="BLE service uuid")
@click.option(
    "--raw-char-uuid",
    default=DEFAULT_RAW_SAMPLE_CHAR_UUID,
    help="Raw sample characteristic UUID",
)
@click.option("--backend", default="http://127.0.0.1:18765", help="Backend base URL")
@click.option("--token", default=None, help="Bearer token")
@click.option("--window-size", default=200, type=int, help="Model window size")
@click.option("--sample-rate", default=50, type=int, help="Expected sample rate")
@click.option("--dry-run", is_flag=True, help="Build windows but do not POST")
@click.option("--mock", is_flag=True, help="Use local mock sample generator")
@click.option("--replay", default=None, help="Replay raw_samples.jsonl")
def main(
    device_name: str,
    service_uuid: str,
    raw_char_uuid: str,
    backend: str,
    token: Optional[str],
    window_size: int,
    sample_rate: int,
    dry_run: bool,
    mock: bool,
    replay: Optional[str],
):
    source = "mock" if mock else ("replay" if replay else "ble")
    collector = ModelWindowCollector(
        window_size=window_size,
        sample_rate=sample_rate,
        source=source,
    )
    retry_queue: Deque[ModelWindowPayload] = deque(maxlen=20)

    def _handle_window(payload: ModelWindowPayload) -> None:
        _log_window(payload, prefix="[DRY] " if dry_run else "")
        if dry_run:
            return

        while retry_queue:
            ok, retry = _post_model_window(
                backend=backend,
                token=token,
                payload=retry_queue[0],
            )
            if ok:
                retry_queue.popleft()
                continue
            if retry:
                break
            retry_queue.popleft()

        ok, retry = _post_model_window(backend=backend, token=token, payload=payload)
        if not ok and retry:
            retry_queue.append(payload)

    if mock:
        for sample in _mock_samples(sample_rate):
            payload = collector.add_sample(sample)
            if payload is not None:
                _handle_window(payload)
    elif replay:
        replay_path = Path(replay)
        for sample in _replay_samples(replay_path):
            payload = collector.add_sample(sample)
            if payload is not None:
                _handle_window(payload)
        logger.info("Replay completed.")
    else:
        async def _run_ble() -> None:
            async for sample in _ble_samples(
                device_name=device_name,
                service_uuid=service_uuid,
                raw_char_uuid=raw_char_uuid,
            ):
                payload = collector.add_sample(sample)
                if payload is not None:
                    _handle_window(payload)

        asyncio.run(_run_ble())


if __name__ == "__main__":
    main()
