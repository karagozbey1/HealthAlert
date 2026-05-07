from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _make_window_payload(*, sample_count: int = 200, sample_rate_hz: int = 50):
    imu = [[0.01, 0.02, 1.0, 0.1, 0.1, 0.1] for _ in range(sample_count)]
    ppg = [[70000.0, 75000.0] for _ in range(sample_count)]
    return {
        "device_id": "ha-esp32-001",
        "mode": "mock",
        "window_seq": 1,
        "sample_rate_hz": sample_rate_hz,
        "sample_count": sample_count,
        "window_duration_ms": 3980,
        "timestamp_start_ms": 1_700_000_000_000,
        "timestamp_end_ms": 1_700_000_003_980,
        "imu_samples": imu,
        "ppg_samples": ppg,
        "quality_summary": {
            "avg_signal_quality": 0.9,
            "expected_sample_count": 200,
        },
        "latest_vitals": {"heart_rate": 76.0, "spo2": 98.0},
        "source": "mock",
    }


class _FakeDB:
    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)

    async def commit(self):
        return None


class _FakeDeviceRepo:
    def __init__(self, registered: bool = True):
        self.registered = registered

    async def get_registration(self, _device_id: str):
        if self.registered:
            return {"user_id": "u1"}
        return None


class _FakeLiveStatusRepo:
    async def get_by_user(self, user_id: str):
        return {
            "id": "ls1",
            "user_id": user_id,
            "heart_rate": 72.0,
            "spo2": 98.0,
            "motion_score": 0.1,
            "risk_score": 0.35,
            "scenario": "normal",
            "timestamp": datetime.utcnow(),
        }

    async def upsert(self, _user_id: str, data):
        return data


class _FakePersonalizationRepo:
    def __init__(self):
        self.profile = {
            "id": "p1",
            "user_id": "u1",
            "personalization_level": "learning",
            "ml_window_count": 0,
            "ml_usable_window_count": 0,
            "ml_evidence_mean": 0.0,
            "ml_evidence_std": 0.0,
            "ml_confidence_mean": 0.0,
            "ml_positive_support_count": 0,
            "ml_personal_disagreement_count": 0,
            "total_feedback_count": 0,
            "total_valid_samples": 100,
        }

    async def get_or_create_profile(self, _user_id: str):
        return dict(self.profile)

    async def update_profile(self, _user_id: str, updates):
        self.profile.update(updates)
        return dict(self.profile)

    async def add_risk_memory(self, data):
        return data


class _FakeRepos:
    def __init__(self, registered: bool = True):
        self.devices = _FakeDeviceRepo(registered=registered)
        self.live_status = _FakeLiveStatusRepo()
        self.personalization = _FakePersonalizationRepo()
        self.learning = None


class TestModelWindowSchemaValidation:
    def test_valid_200_sample_window_accepted(self):
        from schemas import DeviceModelWindowRequest

        obj = DeviceModelWindowRequest(**_make_window_payload())
        assert obj.sample_count == 200

    def test_invalid_sample_count_rejected(self):
        from schemas import DeviceModelWindowRequest

        payload = _make_window_payload(sample_count=200)
        payload["imu_samples"] = payload["imu_samples"][:-1]
        with pytest.raises(ValidationError):
            DeviceModelWindowRequest(**payload)

    def test_invalid_imu_shape_rejected(self):
        from schemas import DeviceModelWindowRequest

        payload = _make_window_payload()
        payload["imu_samples"][0] = [1, 2, 3]
        with pytest.raises(ValidationError):
            DeviceModelWindowRequest(**payload)

    def test_invalid_ppg_shape_rejected(self):
        from schemas import DeviceModelWindowRequest

        payload = _make_window_payload()
        payload["ppg_samples"][0] = [1, 2, 3]
        with pytest.raises(ValidationError):
            DeviceModelWindowRequest(**payload)


class TestModelWindowEndpointFlow:
    def test_sample_rate_1hz_marks_model_not_ready(self):
        from schemas import DeviceModelWindowRequest
        from routers.model_window_router import ingest_model_window

        async def run():
            req = DeviceModelWindowRequest(**_make_window_payload(sample_rate_hz=1))
            repos = _FakeRepos(registered=True)
            db = _FakeDB()
            resp = await ingest_model_window(req, db=db, repos=repos)
            assert resp.model_ready is False
            assert resp.fusion_result is not None
            assert float(resp.fusion_result["ml_adjustment"]) == 0.0

        asyncio.run(run())

    def test_registered_device_returns_user_id(self):
        from schemas import DeviceModelWindowRequest
        from routers.model_window_router import ingest_model_window

        async def run():
            req = DeviceModelWindowRequest(**_make_window_payload())
            repos = _FakeRepos(registered=True)
            db = _FakeDB()
            resp = await ingest_model_window(req, db=db, repos=repos)
            assert resp.user_id == "u1"

        asyncio.run(run())

    def test_unregistered_device_no_500(self):
        from schemas import DeviceModelWindowRequest
        from routers.model_window_router import ingest_model_window

        async def run():
            req = DeviceModelWindowRequest(**_make_window_payload())
            repos = _FakeRepos(registered=False)
            db = _FakeDB()
            resp = await ingest_model_window(req, db=db, repos=repos)
            assert resp.user_id is None
            assert resp.status == "accepted"

        asyncio.run(run())

    def test_ml_model_unavailable_fail_open(self):
        from schemas import DeviceModelWindowRequest
        from routers.model_window_router import ingest_model_window
        from services.ml_inference_service import ml_inference_service

        async def run():
            req = DeviceModelWindowRequest(**_make_window_payload())
            repos = _FakeRepos(registered=True)
            db = _FakeDB()

            prev_loaded = ml_inference_service._loaded
            prev_available = ml_inference_service._available
            prev_predictor = ml_inference_service._predictor
            prev_post = ml_inference_service._postprocessor
            try:
                ml_inference_service._loaded = True
                ml_inference_service._available = False
                ml_inference_service._predictor = None
                ml_inference_service._postprocessor = None
                resp = await ingest_model_window(req, db=db, repos=repos)
                assert resp.ml_live_result is not None
                assert resp.ml_live_result.get("ml_available") is False
            finally:
                ml_inference_service._loaded = prev_loaded
                ml_inference_service._available = prev_available
                ml_inference_service._predictor = prev_predictor
                ml_inference_service._postprocessor = prev_post

        asyncio.run(run())

    def test_device_packet_schema_still_intact(self):
        from schemas import DevicePacketRequest

        pkt = DevicePacketRequest(
            device_id="ha-esp32-001",
            timestamp_ms=1_700_000_000_000,
            mode="mock",
            packet_seq=7,
            accel_x=0.1,
            accel_y=0.1,
            accel_z=1.0,
            gyro_x=0.0,
            gyro_y=0.0,
            gyro_z=0.0,
            red_value=70000,
            ir_value=75000,
            heart_rate=78.0,
            spo2=98.0,
            signal_quality=0.9,
            imu_ok=True,
            ppg_ok=True,
            hr_valid=True,
            spo2_valid=True,
            finger_detected=True,
            state_hint="normal",
        )
        assert pkt.packet_seq == 7
