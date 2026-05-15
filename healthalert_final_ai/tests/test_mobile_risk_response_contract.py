from src.healthalert.api.schemas.hybrid_inference_schema import HybridInferenceRequest
from src.healthalert.api.services.hybrid_inference_api_service import (
    HybridInferenceAPIService,
    UI_MAPPING,
)
from src.healthalert.fusion.risk_fusion_engine import RiskFusionEngine


def _imu_window():
    return [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6] for _ in range(200)]


def _ppg_window():
    return [1200.0 + i for i in range(200)]


def test_final_response_contains_mobile_risk_screen_contract_fields():
    service = HybridInferenceAPIService()
    out = service.infer(
        HybridInferenceRequest(
            patient_id="mobile_contract_patient",
            timestamp="2026-05-15T12:03:00Z",
            data_mode="live",
            imu_window=_imu_window(),
            ppg_window=_ppg_window(),
            heart_rate=82,
            spo2=97,
        )
    ).model_dump()

    assert {"final_risk_score", "risk_level", "confidence_score", "recommended_action", "reasons"}.issubset(
        out["risk"]
    )
    assert {"title", "message", "color_level", "show_alert", "ask_user_confirmation"}.issubset(
        out["ui"]
    )
    assert {"fall", "activity", "ppg_quality", "gait", "vitals"}.issubset(out["experts"])
    assert "fall_probability" in out["experts"]["fall"]
    assert "activity_context" in out["experts"]["activity"]
    assert "quality_label" in out["experts"]["ppg_quality"]
    assert "gait_abnormal_probability" in out["experts"]["gait"]
    assert "contribution" in out["experts"]["vitals"]
    assert {"imu_missing", "ppg_missing", "baseline_missing"}.issubset(out["missing_modalities"])
    assert {
        "baseline_available",
        "cold_start_mode",
        "personalization_adjustment",
    }.issubset(out["personalization"])


def test_risk_level_ui_color_mapping():
    assert UI_MAPPING["normal"]["color_level"] == "green"
    assert UI_MAPPING["caution"]["color_level"] == "yellow"
    assert UI_MAPPING["high_risk"]["color_level"] == "orange"
    assert UI_MAPPING["critical"]["color_level"] == "red"
    assert UI_MAPPING["normal"]["show_alert"] is False
    assert UI_MAPPING["critical"]["ask_user_confirmation"] is True


def test_activity_context_alone_cannot_create_critical_level():
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
    assert 0 <= out["final_risk_score"] <= 100
