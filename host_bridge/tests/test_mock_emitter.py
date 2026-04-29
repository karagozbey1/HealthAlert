"""
HealthAlert Module 3 – Tests for mock serial emitter packet generation.
"""
import json
import math

import pytest

# Import the generation function directly
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mock_serial_emitter import _generate_packet, SCENARIOS


class TestMockPacketGeneration:
    def test_all_scenarios_produce_valid_packets(self):
        from packet_schema import validate_packet
        for name in SCENARIOS:
            pkt = _generate_packet(seq=0, scenario_name=name, t=0.0)
            validated = validate_packet(pkt)
            assert validated.state_hint == name
            assert validated.mode == "mock"

    def test_packet_seq_increments(self):
        for seq in range(10):
            pkt = _generate_packet(seq=seq, scenario_name="normal", t=float(seq))
            assert pkt["packet_seq"] == seq

    def test_normal_scenario_ranges(self):
        for t in [0.0, 1.0, 5.0, 10.0]:
            pkt = _generate_packet(seq=0, scenario_name="normal", t=t)
            # Normal HR should be roughly 68–76 ± noise
            assert 50 < pkt["heart_rate"] < 100
            assert 90 < pkt["spo2"] <= 100

    def test_elevated_hr_scenario(self):
        hrs = []
        for t in range(20):
            pkt = _generate_packet(seq=t, scenario_name="elevated_hr", t=float(t))
            hrs.append(pkt["heart_rate"])
        avg_hr = sum(hrs) / len(hrs)
        assert avg_hr > 90  # should be elevated

    def test_low_spo2_scenario(self):
        spo2s = []
        for t in range(20):
            pkt = _generate_packet(seq=t, scenario_name="low_spo2", t=float(t))
            spo2s.append(pkt["spo2"])
        avg_spo2 = sum(spo2s) / len(spo2s)
        assert avg_spo2 < 95  # should be low

    def test_critical_state_high_risk_indicators(self):
        pkt = _generate_packet(seq=0, scenario_name="critical_state", t=5.0)
        assert pkt["heart_rate"] > 100
        assert pkt["spo2"] < 95

    def test_motion_instability_has_large_accel(self):
        accels = []
        for t in range(20):
            pkt = _generate_packet(seq=t, scenario_name="motion_instability", t=float(t))
            mag = math.sqrt(pkt["accel_x"]**2 + pkt["accel_y"]**2 + (pkt["accel_z"] - 1.0)**2)
            accels.append(mag)
        avg_accel = sum(accels) / len(accels)
        # Motion instability should have notably higher acceleration noise
        assert avg_accel > 0.1

    def test_finger_always_detected_in_mock(self):
        for name in SCENARIOS:
            pkt = _generate_packet(seq=0, scenario_name=name, t=0.0)
            assert pkt["finger_detected"] is True

    def test_imu_and_ppg_ok_in_mock(self):
        for name in SCENARIOS:
            pkt = _generate_packet(seq=0, scenario_name=name, t=0.0)
            assert pkt["imu_ok"] is True
            assert pkt["ppg_ok"] is True

    def test_packet_has_all_required_fields(self):
        required = {
            "device_id", "timestamp_ms", "mode", "packet_seq",
            "accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z",
            "red_value", "ir_value", "heart_rate", "spo2", "signal_quality",
            "imu_ok", "ppg_ok", "hr_valid", "spo2_valid", "finger_detected",
            "state_hint",
        }
        pkt = _generate_packet(seq=0, scenario_name="normal", t=0.0)
        assert required.issubset(set(pkt.keys()))
