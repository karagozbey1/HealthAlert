from src.healthalert.api.schemas.hybrid_inference_schema import (
    HybridInferenceRequest,
    HybridInferenceResponse,
)


def test_request_schema_accepts_imu_only():
    payload = HybridInferenceRequest(
        patient_id="demo_patient_001",
        timestamp="2026-05-14T12:00:00Z",
        data_mode="live",
        imu_window=[[0.0] * 6 for _ in range(200)],
    )
    assert payload.patient_id == "demo_patient_001"


def test_response_schema_core_fields():
    payload = HybridInferenceResponse.model_validate(
        {
            "patient_id": "p1",
            "timestamp": "2026-05-14T12:00:00Z",
            "data_mode": "demo",
            "risk": {
                "final_risk_score": 42.0,
                "risk_level": "caution",
                "confidence_score": 0.7,
                "recommended_action": "increase_monitoring",
                "reasons": ["x"],
            },
            "experts": {
                "fall": {"enabled": True, "fall_probability": 0.5, "threshold_caution": 0.35, "threshold_balanced": 0.45},
                "activity": {"enabled": True, "status": "temporary_context_baseline", "activity_context": "walking", "confidence": 0.8},
                "ppg_quality": {"enabled": True, "quality_label": "good_quality", "quality_score": 0.9},
                "vitals": {"ml_enabled": False, "mode": "runtime_rules_plus_personalization", "contribution": 0.0, "reasons": ["x"]},
                "gait": {"ml_enabled": False, "mode": "runtime_rule_based_imu_score", "contribution": 0.1, "reasons": ["y"]},
            },
            "personalization": {
                "baseline_available": False,
                "cold_start_mode": True,
                "personalization_adjustment": 0.0,
                "baseline_update_allowed": False,
            },
            "missing_modalities": {"imu_missing": False, "ppg_missing": False, "baseline_missing": True},
            "ui": {"title": "Dikkat", "message": "msg", "color_level": "yellow", "show_alert": False, "ask_user_confirmation": False},
        }
    )
    assert payload.risk.risk_level == "caution"
