from __future__ import annotations

from typing import Any, Dict

from config import settings


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


# ML kanit skorunu sinirli sekilde hesaplayip risk birlesimini uygular.
class MLEvidenceFusionService:

    def compute_ml_evidence_score(
        self, ml_result: Dict[str, Any] | None, window_quality: Dict[str, Any] | None
    ) -> Dict[str, Any]:
        if not ml_result:
            return {
                "ml_evidence_score": 0.0,
                "ml_confidence": 0.0,
                "ml_usable": False,
                "reason": "ml_result_missing",
                "components": {},
            }

        ml_available = bool(ml_result.get("ml_available", False))
        if not ml_available:
            return {
                "ml_evidence_score": 0.0,
                "ml_confidence": float(ml_result.get("confidence", 0.0) or 0.0),
                "ml_usable": False,
                "reason": "ml_unavailable",
                "components": {},
            }

        fall_prob = float(
            ml_result.get("fall_probability", ml_result.get("fall_prob", 0.0)) or 0.0
        )
        instability_prob = float(
            ml_result.get(
                "instability_probability", ml_result.get("instability_prob", 0.0)
            )
            or 0.0
        )
        quality_score = float(
            ml_result.get("ppg_quality_score", ml_result.get("quality_score", 1.0)) or 1.0
        )
        ml_risk_score = float(
            ml_result.get("ml_risk_score", ml_result.get("risk_score", 0.0)) or 0.0
        )
        confidence = float(ml_result.get("confidence", 0.0) or 0.0)

        quality_penalty = _clamp01(1.0 - _clamp01(quality_score))
        fall_component = 0.40 * _clamp01(fall_prob)
        instability_component = 0.25 * _clamp01(instability_prob)
        risk_component = 0.25 * _clamp01(ml_risk_score)
        quality_penalty_component = 0.10 * quality_penalty

        evidence = _clamp01(
            fall_component
            + instability_component
            + risk_component
            + quality_penalty_component
        )

        model_ready = bool(ml_result.get("model_ready", True))
        sample_rate_warning = bool(ml_result.get("sample_rate_warning", False))
        if window_quality is not None and "model_ready" in window_quality:
            model_ready = bool(window_quality.get("model_ready"))

        ml_usable = (
            ml_available
            and not bool(ml_result.get("ml_skipped", False))
            and model_ready
            and (not sample_rate_warning)
            and confidence >= settings.ML_EVIDENCE_MIN_CONFIDENCE
        )

        reason = "ok" if ml_usable else "gated"
        return {
            "ml_evidence_score": round(evidence, 4),
            "ml_confidence": round(confidence, 4),
            "ml_usable": ml_usable,
            "reason": reason,
            "components": {
                "fall_component": round(fall_component, 4),
                "instability_component": round(instability_component, 4),
                "risk_component": round(risk_component, 4),
                "quality_penalty_component": round(quality_penalty_component, 4),
            },
        }

    def apply_ml_evidence_adjustment(
        self,
        personalized_risk_score: float,
        ml_evidence_result: Dict[str, Any] | None,
        *,
        model_ready: bool = True,
        sample_rate_warning: bool = False,
    ) -> Dict[str, Any]:
        pr = _clamp01(personalized_risk_score)
        base = {
            "personalized_risk_score": round(pr, 4),
            "ml_evidence_score": None,
            "ml_adjustment": 0.0,
            "final_risk_score": round(pr, 4),
            "fusion_applied": False,
            "fusion_mode": "bounded_ml_evidence",
            "reason": "fusion_disabled_or_gated",
        }

        if not settings.ML_EVIDENCE_FUSION_ENABLED:
            base["reason"] = "fusion_disabled"
            return base

        if not ml_evidence_result:
            base["reason"] = "ml_evidence_missing"
            return base

        ml_evidence_score = _clamp01(float(ml_evidence_result.get("ml_evidence_score", 0.0)))
        base["ml_evidence_score"] = round(ml_evidence_score, 4)

        if not bool(ml_evidence_result.get("ml_usable", False)):
            base["reason"] = "ml_not_usable"
            return base

        if settings.ML_EVIDENCE_REQUIRE_MODEL_READY_WINDOW and not model_ready:
            base["reason"] = "model_window_not_ready"
            return base

        if settings.ML_EVIDENCE_REQUIRE_SAMPLE_RATE_OK and sample_rate_warning:
            base["reason"] = "sample_rate_warning"
            return base

        ml_conf = float(ml_evidence_result.get("ml_confidence", 0.0) or 0.0)
        if ml_conf < settings.ML_EVIDENCE_MIN_CONFIDENCE:
            base["reason"] = "low_ml_confidence"
            return base

        delta = ml_evidence_score - pr
        adjustment = 0.0
        if delta > 0:
            adjustment = min(
                delta * settings.ML_EVIDENCE_WEIGHT,
                settings.ML_EVIDENCE_MAX_POSITIVE_ADJUSTMENT,
            )
        elif delta < 0:
            if settings.ML_EVIDENCE_ALLOW_NEGATIVE_ADJUSTMENT:
                adjustment = max(delta * settings.ML_EVIDENCE_WEIGHT, -0.05)
            else:
                adjustment = 0.0

        final_score = _clamp01(pr + adjustment)
        return {
            "personalized_risk_score": round(pr, 4),
            "ml_evidence_score": round(ml_evidence_score, 4),
            "ml_adjustment": round(adjustment, 4),
            "final_risk_score": round(final_score, 4),
            "fusion_applied": abs(adjustment) > 1e-9,
            "fusion_mode": "bounded_ml_evidence",
            "reason": "applied" if abs(adjustment) > 1e-9 else "no_delta_or_gated",
        }


ml_evidence_fusion_service = MLEvidenceFusionService()
