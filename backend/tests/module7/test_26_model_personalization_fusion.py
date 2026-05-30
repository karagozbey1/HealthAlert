from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _baseline_result(*, global_risk: float = 0.35, baseline_final: float = 0.42, personal_deviation: float = 0.07):
    return {
        "global_risk_score": global_risk,
        "final_risk_score": baseline_final,
        "personal_deviation_score": personal_deviation,
    }


def _personalization_result(
    *,
    personalized: float = 0.52,
    deviation: float = 0.06,
    trend: float = 0.03,
    feedback: float = 0.01,
):
    return {
        "final_personalized_risk": personalized,
        "baseline_deviation_score": deviation,
        "trend_adjustment": trend,
        "feedback_adjustment": feedback,
    }


def _ml_result(*, available: bool = True, ml_risk_score: float = 0.78, confidence: float = 0.83):
    return {
        "ml_available": available,
        "ml_risk_score": ml_risk_score,
        "confidence": confidence,
        "model_version": "window-model-v1",
        "accuracy": 0.99,
        "f1": 0.98,
    }


def test_ml_available_uses_ml_risk_as_base_score():
    from services.risk_fusion_service import risk_fusion_service

    result = risk_fusion_service.compute_final_risk_with_personalization(
        _ml_result(),
        _baseline_result(),
        _personalization_result(),
        {"quality_confidence": 0.9, "safety_override": False},
    )
    assert result["ml_base_score"] == pytest.approx(0.78)
    assert result["fusion_mode"] == "model_plus_personalization"


def test_ml_unavailable_falls_back_to_personalized_risk():
    from services.risk_fusion_service import risk_fusion_service

    result = risk_fusion_service.compute_final_risk_with_personalization(
        _ml_result(available=False),
        _baseline_result(),
        _personalization_result(personalized=0.51),
        {"quality_confidence": 0.9, "safety_override": False},
    )
    assert result["ml_available"] is False
    assert result["personalized_risk_score"] == pytest.approx(0.51)
    assert result["final_risk_score"] >= 0.51
    assert result["fusion_mode"] == "fallback_personalization_only"


def test_personal_adjustment_capped_at_positive_point_twenty():
    from services.risk_fusion_service import risk_fusion_service

    result = risk_fusion_service.compute_final_risk_with_personalization(
        _ml_result(ml_risk_score=0.4),
        _baseline_result(personal_deviation=0.15),
        _personalization_result(deviation=0.15, trend=0.10, feedback=0.10),
        {"quality_confidence": 0.95, "safety_override": False},
    )
    assert result["personal_adjustment"] <= 0.20


def test_negative_adjustment_disabled_by_default():
    from services.risk_fusion_service import risk_fusion_service

    result = risk_fusion_service.compute_final_risk_with_personalization(
        _ml_result(ml_risk_score=0.7),
        _baseline_result(personal_deviation=-0.10),
        _personalization_result(personalized=0.20, deviation=-0.10, trend=-0.08, feedback=-0.05),
        {"quality_confidence": 0.95, "safety_override": False},
    )
    assert result["personal_adjustment"] == 0.0


def test_final_risk_score_is_clamped_between_zero_and_one():
    from services.risk_fusion_service import risk_fusion_service

    result = risk_fusion_service.compute_final_risk_with_personalization(
        _ml_result(ml_risk_score=0.98),
        _baseline_result(personal_deviation=0.20),
        _personalization_result(personalized=1.0, deviation=0.20, trend=0.20, feedback=0.20),
        {"quality_confidence": 1.0, "safety_override": True},
    )
    assert 0.0 <= result["final_risk_score"] <= 1.0


def test_risk_breakdown_contains_fusion_mode_and_model_version():
    from services.risk_fusion_service import risk_fusion_service

    result = risk_fusion_service.compute_final_risk_with_personalization(
        _ml_result(),
        _baseline_result(),
        _personalization_result(),
        {"quality_confidence": 0.85, "safety_override": False},
    )
    assert result["fusion_mode"] == "model_plus_personalization"
    assert result["model_version"] == "window-model-v1"
    assert "fusion_reason" in result


def test_training_metrics_do_not_override_runtime_ml_score():
    from services.risk_fusion_service import risk_fusion_service

    ml_result = _ml_result(ml_risk_score=0.61)
    ml_result["accuracy"] = 1.0
    ml_result["auc"] = 1.0
    result = risk_fusion_service.compute_final_risk_with_personalization(
        ml_result,
        _baseline_result(),
        _personalization_result(),
        {"quality_confidence": 0.9, "safety_override": False},
    )
    assert result["ml_base_score"] == pytest.approx(0.61)


def test_fusion_output_has_no_ml_only_alert_trigger():
    from services.risk_fusion_service import risk_fusion_service

    result = risk_fusion_service.compute_final_risk_with_personalization(
        _ml_result(),
        _baseline_result(),
        _personalization_result(),
        {"quality_confidence": 0.9, "safety_override": False},
    )
    assert "alert_id" not in result
    assert "immediate_alert" not in result
    assert "final_risk_score" in result