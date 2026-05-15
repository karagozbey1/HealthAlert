import asyncio
from uuid import uuid4

import pytest

httpx = pytest.importorskip("httpx")

from src.healthalert.api.app import create_app
from src.healthalert.api.routes.live_sensor_routes import service as live_route_service


app = create_app()
RISK_LEVELS = {"normal", "caution", "high_risk", "critical"}


def _patient(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _esp32_alias_sample(i: int, patient_id: str, *, include_ppg: bool = True):
    sample = {
        "patient_id": patient_id,
        "timestamp": f"2026-05-15T12:02:{i:02d}Z",
        "source": "esp32",
        "ax": 0.1,
        "ay": 0.2,
        "az": 0.3,
        "gx": 0.4,
        "gy": 0.5,
        "gz": 0.6,
    }
    if include_ppg:
        sample["IR"] = 1500 + i
        sample["RED"] = 1200 + i
        sample["heart_rate"] = 82
        sample["spo2"] = 97
    return sample


async def _post_many(patient_id: str, count: int, *, include_ppg: bool = True):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = None
        for i in range(count):
            res = await client.post(
                "/api/healthalert/sensor-sample",
                json=_esp32_alias_sample(i, patient_id, include_ppg=include_ppg),
            )
            assert res.status_code == 200
        return res


def test_199_samples_do_not_trigger_inference():
    patient_id = _patient("endpoint_199")
    body = asyncio.run(_post_many(patient_id, 199)).json()

    assert body["window_ready"] is False
    assert body["inference_triggered"] is False
    assert body["buffered_imu_samples"] == 199


def test_200th_esp32_format_sample_triggers_inference():
    patient_id = _patient("endpoint_200")
    body = asyncio.run(_post_many(patient_id, 200)).json()

    assert body["window_ready"] is True
    assert body["inference_triggered"] is True
    result = body["inference_result"]
    assert result["data_mode"] == "live"
    assert 0 <= result["risk"]["final_risk_score"] <= 100
    assert result["risk"]["risk_level"] in RISK_LEVELS
    assert result["experts"]["gait"]["contribution"] <= 5.0
    assert result["experts"]["activity"]["activity_context"]


def test_ppg_missing_window_does_not_crash():
    patient_id = _patient("endpoint_ppg_missing")
    body = asyncio.run(_post_many(patient_id, 200, include_ppg=False)).json()

    assert body["window_ready"] is True
    assert body["inference_result"]["missing_modalities"]["ppg_missing"] is True
    assert "ppg_missing" in body["inference_result"]["risk"]["reasons"]


def test_malformed_sample_returns_safe_buffering_response():
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/healthalert/sensor-sample",
                json={"patient_id": _patient("endpoint_malformed"), "source": "esp32"},
            )

    res = asyncio.run(_run())
    body = res.json()
    assert res.status_code == 200
    assert body["window_ready"] is False
    assert body["inference_triggered"] is False
    assert body["missing_modalities"]["imu_missing"] is True


def test_patient_id_buffers_are_isolated():
    async def _run():
        p1 = _patient("endpoint_buffer_a")
        p2 = _patient("endpoint_buffer_b")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for i in range(199):
                res1 = await client.post(
                    "/api/healthalert/sensor-sample",
                    json=_esp32_alias_sample(i, p1),
                )
                assert res1.status_code == 200
            res2 = await client.post(
                "/api/healthalert/sensor-sample",
                json=_esp32_alias_sample(0, p2),
            )
            assert res2.status_code == 200
            return res1.json(), res2.json()

    p1_body, p2_body = asyncio.run(_run())
    assert p1_body["buffered_imu_samples"] == 199
    assert p2_body["buffered_imu_samples"] == 1
    assert p2_body["inference_triggered"] is False


def test_endpoint_runtime_does_not_load_rejected_models():
    patient_id = _patient("endpoint_rejected")
    body = asyncio.run(_post_many(patient_id, 200)).json()

    assert body["inference_result"]["experts"]["vitals"]["ml_enabled"] is False
    loaded = "\n".join(live_route_service.hybrid_api.runtime_service.loaded_model_paths)
    assert "activity_expert_balanced" not in loaded
    assert "activity_v2_pamap2_mixed" not in loaded
    assert "gait_instability_v2_2_ablation" not in loaded
    assert "vitals_context_expert" not in loaded
