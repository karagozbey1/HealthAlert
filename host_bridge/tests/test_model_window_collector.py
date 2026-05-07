from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ble_model_window_collector import ModelWindowCollector
from packet_schema import RawSensorSample


def _sample(seq: int, *, window_seq: int = 0) -> RawSensorSample:
    return RawSensorSample(
        device_id="ha-esp32-001",
        timestamp_ms=1_700_000_000_000 + (seq * 20),
        sample_seq=seq,
        window_seq=window_seq,
        sample_rate_hz=50,
        mode="mock",
        accel_x=0.01,
        accel_y=0.02,
        accel_z=1.0,
        gyro_x=0.1,
        gyro_y=0.1,
        gyro_z=0.1,
        red_value=70000,
        ir_value=75000,
        imu_ok=True,
        ppg_ok=True,
        finger_detected=True,
        signal_quality=0.9,
    )


def test_200_samples_creates_one_window():
    collector = ModelWindowCollector(window_size=200, sample_rate=50, source="mock")
    payload = None
    for i in range(200):
        payload = collector.add_sample(_sample(i))
    assert payload is not None
    assert payload.sample_count == 200
    assert payload.quality_summary["model_ready"] is True


def test_199_samples_no_window():
    collector = ModelWindowCollector(window_size=200, sample_rate=50, source="mock")
    payload = None
    for i in range(199):
        payload = collector.add_sample(_sample(i))
    assert payload is None


def test_missing_sample_marks_low_quality():
    collector = ModelWindowCollector(window_size=200, sample_rate=50, source="mock")
    payload = None
    seq = 0
    for _ in range(100):
        payload = collector.add_sample(_sample(seq))
        seq += 1
    # Skip one sequence number.
    seq += 1
    for _ in range(100):
        payload = collector.add_sample(_sample(seq))
        seq += 1

    assert payload is not None
    assert payload.quality_summary["missing_sample_count"] >= 1
    assert payload.quality_summary["model_ready"] is False
