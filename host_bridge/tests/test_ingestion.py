"""
HealthAlert Module 3 – Tests for ingestion logic.

Tests the ingestion router's computation functions and schema validation
without requiring a live database or SQLAlchemy (which needs Python ≤3.13).
"""
import math
import pytest
import sys
from pathlib import Path

# Add host_bridge to path for packet_schema
sys.path.insert(0, str(Path(__file__).parent.parent))

from packet_schema import DevicePacketSchema, validate_packet


def _valid_packet(**overrides) -> dict:
    base = {
        "device_id": "ha-esp32-test",
        "timestamp_ms": 100000,
        "mode": "mock",
        "packet_seq": 1,
        "accel_x": 0.01,
        "accel_y": -0.02,
        "accel_z": 1.0,
        "gyro_x": 0.5,
        "gyro_y": -0.3,
        "gyro_z": 0.1,
        "red_value": 75000,
        "ir_value": 80000,
        "heart_rate": 72.5,
        "spo2": 97.8,
        "signal_quality": 0.91,
        "imu_ok": True,
        "ppg_ok": True,
        "hr_valid": True,
        "spo2_valid": True,
        "finger_detected": True,
        "state_hint": "normal",
    }
    base.update(overrides)
    return base


# ── Motion score computation (mirroring ingestion_router logic) ─────────────

def compute_motion_score(ax, ay, az, gx, gy, gz):
    accel_mag = math.sqrt(ax * ax + ay * ay + az * az)
    accel_dev = abs(accel_mag - 1.0)
    gyro_mag = math.sqrt(gx * gx + gy * gy + gz * gz)
    score = min(1.0, (accel_dev * 2.0) + (gyro_mag / 50.0))
    return round(score, 3)


def compute_risk_score(hr, spo2, hr_valid, spo2_valid, motion):
    risk = 0.0
    if hr_valid:
        if hr > 120:
            risk += 0.3
        elif hr > 100:
            risk += 0.15
        elif hr < 50:
            risk += 0.2
    if spo2_valid:
        if spo2 < 90:
            risk += 0.4
        elif spo2 < 94:
            risk += 0.2
    risk += motion * 0.2
    return round(min(1.0, risk), 3)


class TestMotionScoreComputation:
    def test_stationary(self):
        score = compute_motion_score(0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
        assert score < 0.05

    def test_slight_motion(self):
        score = compute_motion_score(0.1, 0.05, 1.0, 2.0, 1.0, 0.5)
        assert 0.01 < score < 0.5

    def test_heavy_motion(self):
        score = compute_motion_score(0.8, 0.5, 1.5, 20.0, 15.0, 10.0)
        assert score > 0.5

    def test_extreme_motion_clamps_to_1(self):
        score = compute_motion_score(5.0, 5.0, 5.0, 100.0, 100.0, 100.0)
        assert score == 1.0

    def test_zero_gravity(self):
        score = compute_motion_score(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        assert score > 0


class TestRiskScoreComputation:
    def test_normal_vitals_low_risk(self):
        risk = compute_risk_score(72, 98, True, True, 0.05)
        assert risk < 0.1

    def test_high_hr_increases_risk(self):
        risk_normal = compute_risk_score(72, 98, True, True, 0.05)
        risk_high = compute_risk_score(125, 98, True, True, 0.05)
        assert risk_high > risk_normal

    def test_very_high_hr(self):
        risk = compute_risk_score(125, 98, True, True, 0.0)
        assert risk >= 0.3

    def test_low_spo2_critical(self):
        risk = compute_risk_score(72, 85, True, True, 0.0)
        assert risk >= 0.4

    def test_low_spo2_warning(self):
        risk = compute_risk_score(72, 92, True, True, 0.0)
        assert risk >= 0.2

    def test_low_hr(self):
        risk = compute_risk_score(45, 98, True, True, 0.0)
        assert risk >= 0.2

    def test_invalid_vitals_no_risk_from_hr(self):
        risk = compute_risk_score(200, 60, False, False, 0.0)
        assert risk == 0.0

    def test_motion_adds_risk(self):
        risk_still = compute_risk_score(72, 98, True, True, 0.0)
        risk_moving = compute_risk_score(72, 98, True, True, 0.8)
        assert risk_moving > risk_still

    def test_combined_critical(self):
        risk = compute_risk_score(130, 85, True, True, 0.8)
        assert risk >= 0.8

    def test_risk_clamps_to_1(self):
        risk = compute_risk_score(200, 50, True, True, 1.0)
        assert risk <= 1.0


class TestIngestionSchemaValidation:
    def test_valid_packet_accepted(self):
        pkt = validate_packet(_valid_packet())
        assert pkt.device_id == "ha-esp32-test"

    def test_invalid_mode_rejected(self):
        with pytest.raises(Exception):
            validate_packet(_valid_packet(mode="invalid"))

    def test_missing_field_rejected(self):
        data = _valid_packet()
        del data["heart_rate"]
        with pytest.raises(Exception):
            validate_packet(data)

    def test_mock_mode_accepted(self):
        pkt = validate_packet(_valid_packet(mode="mock"))
        assert pkt.mode == "mock"

    def test_real_mode_accepted(self):
        pkt = validate_packet(_valid_packet(mode="real"))
        assert pkt.mode == "real"

    def test_multiple_packets_sequential(self):
        for seq in range(10):
            pkt = validate_packet(_valid_packet(packet_seq=seq))
            assert pkt.packet_seq == seq

    def test_degraded_mode_packet(self):
        pkt = validate_packet(_valid_packet(imu_ok=False, ppg_ok=True))
        assert not pkt.imu_ok
        assert pkt.ppg_ok

    def test_no_finger_packet(self):
        pkt = validate_packet(_valid_packet(
            finger_detected=False, hr_valid=False, spo2_valid=False,
            signal_quality=0.0, heart_rate=0, spo2=0,
        ))
        assert not pkt.finger_detected
        assert not pkt.hr_valid
