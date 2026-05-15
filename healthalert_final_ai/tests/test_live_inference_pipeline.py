import asyncio

import pytest

httpx = pytest.importorskip("httpx")

from src.healthalert.api.app import create_app
from src.healthalert.api.routes.live_sensor_routes import service as live_route_service


app = create_app()
RISK_LEVELS = {"normal", "caution", "high_risk", "critical"}


def _sample(i: int, patient_id: str, include_ppg: bool = True):
    body = {
        "patient_id": patient_id,
        "timestamp": f"2026-05-15T12:01:{i:02d}Z",
        "source": "esp32",
        "imu": {
            "acc_x": 0.1,
            "acc_y": 0.2,
            "acc_z": 0.3,
            "gyro_x": 0.4,
            "gyro_y": 0.5,
            "gyro_z": 0.6,
        },
    }
    if include_ppg:
        body["ppg"] = {"ir": 1400 + i, "red": 1000 + i}
        body["heart_rate"] = 84
        body["spo2"] = 97
    return body


def test_live_endpoint_buffer_then_infer_mobile_schema():
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for i in range(199):
                res = await client.post(
                    "/api/healthalert/sensor-sample",
                    json=_sample(i, patient_id="pipeline_patient_schema"),
                )
                assert res.status_code == 200
                assert res.json()["inference_triggered"] is False
            return await client.post(
                "/api/healthalert/sensor-sample",
                json=_sample(199, patient_id="pipeline_patient_schema"),
            )

    res = asyncio.run(_run())
    body = res.json()
    assert body["window_ready"] is True
    assert body["inference_triggered"] is True

    result = body["inference_result"]
    assert result["data_mode"] == "live"
    assert 0 <= result["risk"]["final_risk_score"] <= 100
    assert result["risk"]["risk_level"] in RISK_LEVELS
    assert result["experts"]["gait"]["contribution"] <= 5.0
    assert {"risk", "ui", "experts", "personalization", "missing_modalities"}.issubset(result)


def test_live_endpoint_imu_only_ppg_missing():
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for i in range(200):
                res = await client.post(
                    "/api/healthalert/sensor-sample",
                    json=_sample(i, patient_id="pipeline_patient_imu_only", include_ppg=False),
                )
            return res

    body = asyncio.run(_run()).json()["inference_result"]
    assert body["missing_modalities"]["ppg_missing"] is True
    assert "ppg_missing" in body["risk"]["reasons"]
    assert 0 <= body["risk"]["final_risk_score"] <= 100


def test_live_endpoint_rejected_models_not_loaded():
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for i in range(200):
                res = await client.post(
                    "/api/healthalert/sensor-sample",
                    json=_sample(i, patient_id="pipeline_patient_rejected"),
                )
            return res

    body = asyncio.run(_run()).json()["inference_result"]
    disabled = body["experts"]
    assert disabled["vitals"]["ml_enabled"] is False
    loaded = "\n".join(live_route_service.hybrid_api.runtime_service.loaded_model_paths)
    assert "activity_expert_balanced" not in loaded
    assert "gait_instability_v2_2_ablation" not in loaded
    assert "vitals_context_expert" not in loaded


def test_activity_context_alone_no_critical_policy():
    from src.healthalert.fusion.risk_fusion_engine import RiskFusionEngine

    out = RiskFusionEngine().fuse(
        fall_probability=0.0,
        activity_context="lying",
        ppg_quality_score=None,
        ppg_quality_label="missing",
        runtime_vitals_adjustment=0.0,
        runtime_gait_motion_score=0.0,
        personalization_adjustment=0.0,
        signal_confidence=1.0,
        missing_modality_flags={"ppg_missing": True, "baseline_missing": True},
    )
    assert out["risk_level"] != "critical"
