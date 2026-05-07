from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _ml_result(
    *,
    available: bool = True,
    confidence: float = 0.8,
    model_ready: bool = True,
    sample_rate_warning: bool = False,
):
    return {
        "fall_probability": 0.9,
        "instability_probability": 0.7,
        "ppg_quality_score": 0.9,
        "ml_risk_score": 0.8,
        "confidence": confidence,
        "ml_available": available,
        "model_ready": model_ready,
        "sample_rate_warning": sample_rate_warning,
        "ml_skipped": False,
    }


class TestMLEvidenceFusion:
    def test_ml_result_none_adjustment_zero(self):
        from services.ml_evidence_fusion_service import ml_evidence_fusion_service

        fusion = ml_evidence_fusion_service.apply_ml_evidence_adjustment(0.4, None)
        assert fusion["ml_adjustment"] == 0.0
        assert fusion["final_risk_score"] == 0.4

    def test_model_ready_false_adjustment_zero(self):
        from services.ml_evidence_fusion_service import ml_evidence_fusion_service

        evidence = ml_evidence_fusion_service.compute_ml_evidence_score(
            _ml_result(model_ready=False), {"model_ready": False}
        )
        fusion = ml_evidence_fusion_service.apply_ml_evidence_adjustment(
            0.4, evidence, model_ready=False
        )
        assert fusion["ml_adjustment"] == 0.0

    def test_sample_rate_warning_adjustment_zero(self):
        from services.ml_evidence_fusion_service import ml_evidence_fusion_service

        evidence = ml_evidence_fusion_service.compute_ml_evidence_score(
            _ml_result(sample_rate_warning=True), {"model_ready": True}
        )
        fusion = ml_evidence_fusion_service.apply_ml_evidence_adjustment(
            0.4, evidence, model_ready=True, sample_rate_warning=True
        )
        assert fusion["ml_adjustment"] == 0.0

    def test_low_confidence_adjustment_zero(self):
        from services.ml_evidence_fusion_service import ml_evidence_fusion_service

        evidence = ml_evidence_fusion_service.compute_ml_evidence_score(
            _ml_result(confidence=0.2), {"model_ready": True}
        )
        fusion = ml_evidence_fusion_service.apply_ml_evidence_adjustment(
            0.4, evidence, model_ready=True
        )
        assert fusion["ml_adjustment"] == 0.0

    def test_high_ml_evidence_bounded_positive(self):
        from services.ml_evidence_fusion_service import ml_evidence_fusion_service

        evidence = ml_evidence_fusion_service.compute_ml_evidence_score(
            _ml_result(), {"model_ready": True}
        )
        fusion = ml_evidence_fusion_service.apply_ml_evidence_adjustment(
            0.2, evidence, model_ready=True
        )
        assert fusion["ml_adjustment"] > 0
        assert fusion["ml_adjustment"] <= 0.15

    def test_max_adjustment_never_exceeds_point_15(self):
        from services.ml_evidence_fusion_service import ml_evidence_fusion_service

        huge = {
            "ml_evidence_score": 1.0,
            "ml_confidence": 0.99,
            "ml_usable": True,
            "reason": "ok",
            "components": {},
        }
        fusion = ml_evidence_fusion_service.apply_ml_evidence_adjustment(
            0.0, huge, model_ready=True
        )
        assert fusion["ml_adjustment"] <= 0.15

    def test_negative_adjustment_disabled_by_default(self):
        from services.ml_evidence_fusion_service import ml_evidence_fusion_service

        low = {
            "ml_evidence_score": 0.1,
            "ml_confidence": 0.9,
            "ml_usable": True,
            "reason": "ok",
            "components": {},
        }
        fusion = ml_evidence_fusion_service.apply_ml_evidence_adjustment(
            0.7, low, model_ready=True
        )
        assert fusion["ml_adjustment"] == 0.0

    def test_fusion_disabled_keeps_personalized_score(self):
        from services.ml_evidence_fusion_service import ml_evidence_fusion_service

        evidence = {
            "ml_evidence_score": 0.9,
            "ml_confidence": 0.9,
            "ml_usable": True,
            "reason": "ok",
            "components": {},
        }
        with mock.patch("services.ml_evidence_fusion_service.settings") as s:
            s.ML_EVIDENCE_FUSION_ENABLED = False
            s.ML_EVIDENCE_WEIGHT = 0.25
            s.ML_EVIDENCE_MAX_POSITIVE_ADJUSTMENT = 0.15
            s.ML_EVIDENCE_ALLOW_NEGATIVE_ADJUSTMENT = False
            s.ML_EVIDENCE_MIN_CONFIDENCE = 0.60
            s.ML_EVIDENCE_REQUIRE_MODEL_READY_WINDOW = True
            s.ML_EVIDENCE_REQUIRE_SAMPLE_RATE_OK = True
            fusion = ml_evidence_fusion_service.apply_ml_evidence_adjustment(
                0.45, evidence
            )
        assert fusion["final_risk_score"] == 0.45

    def test_final_risk_clamped(self):
        from services.ml_evidence_fusion_service import ml_evidence_fusion_service

        evidence = {
            "ml_evidence_score": 1.0,
            "ml_confidence": 0.95,
            "ml_usable": True,
            "reason": "ok",
            "components": {},
        }
        fusion = ml_evidence_fusion_service.apply_ml_evidence_adjustment(
            0.95, evidence, model_ready=True
        )
        assert 0.0 <= fusion["final_risk_score"] <= 1.0

    def test_risk_breakdown_contains_ml_adjustment(self):
        from services.ml_evidence_fusion_service import ml_evidence_fusion_service

        evidence = ml_evidence_fusion_service.compute_ml_evidence_score(
            _ml_result(), {"model_ready": True}
        )
        fusion = ml_evidence_fusion_service.apply_ml_evidence_adjustment(
            0.2, evidence, model_ready=True
        )
        assert "ml_adjustment" in fusion
        assert "final_risk_score" in fusion

    def test_alert_chain_uses_final_score_contract(self):
        # Contract check: fusion output exposes final_risk_score only once.
        from services.ml_evidence_fusion_service import ml_evidence_fusion_service

        evidence = ml_evidence_fusion_service.compute_ml_evidence_score(
            _ml_result(), {"model_ready": True}
        )
        fusion = ml_evidence_fusion_service.apply_ml_evidence_adjustment(
            0.5, evidence, model_ready=True
        )
        assert "final_risk_score" in fusion
