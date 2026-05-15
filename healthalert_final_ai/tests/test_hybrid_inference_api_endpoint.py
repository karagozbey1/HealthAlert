import asyncio
import numpy as np
import pytest

httpx = pytest.importorskip("httpx")

from src.healthalert.api.app import create_app
from src.healthalert.api.routes.hybrid_inference_routes import service


app = create_app()


def _imu():
    return np.random.RandomState(0).normal(0, 1, (200, 6)).tolist()


def _ppg():
    t = np.linspace(0, 4, 200)
    return np.sin(2 * np.pi * 1.2 * t).tolist()


def test_imu_only_request_200():
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/healthalert/inference",
                json={
                    "patient_id": "demo_patient_001",
                    "timestamp": "2026-05-14T12:00:00Z",
                    "data_mode": "live",
                    "imu_window": _imu(),
                },
            )
    res = asyncio.run(_run())
    assert res.status_code == 200
    body = res.json()
    assert 0 <= body["risk"]["final_risk_score"] <= 100


def test_imu_plus_ppg_request_200():
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/healthalert/inference",
                json={
                    "patient_id": "demo_patient_002",
                    "timestamp": "2026-05-14T12:00:01Z",
                    "data_mode": "live",
                    "imu_window": _imu(),
                    "ppg_window": _ppg(),
                    "heart_rate": 82,
                    "spo2": 97,
                },
            )
    res = asyncio.run(_run())
    assert res.status_code == 200
    assert res.json()["experts"]["ppg_quality"]["quality_label"] in {"good_quality", "bad_quality", "missing", "unknown"}


def test_ppg_missing_reason_present():
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/healthalert/inference",
                json={
                    "patient_id": "demo_patient_003",
                    "timestamp": "2026-05-14T12:00:02Z",
                    "data_mode": "live",
                    "imu_window": _imu(),
                },
            )
    res = asyncio.run(_run())
    assert res.status_code == 200
    assert "ppg_missing" in res.json()["risk"]["reasons"]


def test_baseline_missing_sets_cold_start_mode():
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/healthalert/inference",
                json={
                    "patient_id": "new_user_no_baseline",
                    "timestamp": "2026-05-14T12:00:03Z",
                    "data_mode": "demo",
                    "imu_window": _imu(),
                },
            )
    res = asyncio.run(_run())
    assert res.status_code == 200
    assert res.json()["personalization"]["cold_start_mode"] is True


def test_allowed_risk_level_and_nonempty_action():
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/healthalert/inference",
                json={
                    "patient_id": "demo_patient_004",
                    "timestamp": "2026-05-14T12:00:04Z",
                    "data_mode": "npz_demo",
                    "imu_window": _imu(),
                    "ppg_window": _ppg(),
                },
            )
    res = asyncio.run(_run())
    body = res.json()
    assert body["risk"]["risk_level"] in {"normal", "caution", "high_risk", "critical"}
    assert body["risk"]["recommended_action"]
    assert isinstance(body["risk"]["reasons"], list)


def test_rejected_models_not_loaded():
    assert service.runtime_service.config["vitals_context_model"]["enabled"] is False
    assert service.runtime_service.config["gait_instability_model"]["enabled"] is True
    assert service.runtime_service.config["gait_instability_model"]["status"] == (
        "accepted_auxiliary_low_weight"
    )
    for block in service.runtime_service.config["rejected_models"].values():
        assert block["enabled"] is False


def test_malformed_input_returns_422():
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/healthalert/inference",
                json={
                    "patient_id": "demo_patient_005",
                    "timestamp": "2026-05-14T12:00:05Z",
                    "imu_window": [1, 2, 3],
                },
            )
    res = asyncio.run(_run())
    assert res.status_code == 422
