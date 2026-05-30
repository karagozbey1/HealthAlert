from __future__ import annotations

from typing import Any, Dict, Optional

from config import settings


def _clamp01(value: float) -> float:
    """risk fusion servisindeki HealthAlert iş kuralını uygular."""
    return max(0.0, min(1.0, float(value)))


class RiskFusionService:
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    def compute_final_risk_with_personalization(
        self,
        ml_result: Optional[Dict[str, Any]],
        baseline_result: Optional[Dict[str, Any]],
        personalization_result: Optional[Dict[str, Any]],
        quality_info: Optional[Dict[str, Any]],
        fusion_settings=settings,
    ) -> Dict[str, Any]:
        """risk fusion servisinde risk veya skor değerini hesaplar."""
        baseline_result = baseline_result or {}
        personalization_result = personalization_result or {}
        quality_info = quality_info or {}
        ml_result = ml_result or {}

        heuristic_risk_score = _clamp01(
            baseline_result.get("global_risk_score", baseline_result.get("heuristic_risk_score", 0.0))
        )
        baseline_adjusted_risk = _clamp01(
            baseline_result.get("final_risk_score", heuristic_risk_score)
        )
        personalized_risk_score = _clamp01(
            personalization_result.get("final_personalized_risk", baseline_adjusted_risk)
        )

        ml_available = bool(ml_result.get("ml_available", False))
        ml_base_score = (
            _clamp01(ml_result.get("ml_risk_score", 0.0)) if ml_available else None
        )
        ml_confidence = float(ml_result.get("confidence", 0.0) or 0.0)
        model_version = ml_result.get("model_version")

        baseline_personal_adjustment = float(
            baseline_result.get("personal_deviation_score", 0.0) or 0.0
        )
        adaptive_personal_adjustment = float(
            personalization_result.get("baseline_deviation_score", 0.0) or 0.0
        )
        trend_adjustment = float(
            personalization_result.get("trend_adjustment", 0.0) or 0.0
        )
        feedback_adjustment = float(
            personalization_result.get("feedback_adjustment", 0.0) or 0.0
        )
        raw_personal_adjustment = (
            baseline_personal_adjustment
            + adaptive_personal_adjustment
            + trend_adjustment
            + feedback_adjustment
        )

        max_positive = float(fusion_settings.MAX_PERSONAL_POSITIVE_ADJUSTMENT)
        max_negative = float(fusion_settings.MAX_PERSONAL_NEGATIVE_ADJUSTMENT)
        if not bool(fusion_settings.ALLOW_PERSONAL_NEGATIVE_ADJUSTMENT):
            bounded_personal_adjustment = max(0.0, raw_personal_adjustment)
        else:
            bounded_personal_adjustment = max(-max_negative, raw_personal_adjustment)
        bounded_personal_adjustment = min(max_positive, bounded_personal_adjustment)

        quality_confidence = float(
            quality_info.get("quality_confidence", quality_info.get("avg_signal_quality", 1.0))
            or 1.0
        )
        safety_override = bool(quality_info.get("safety_override", False))

        quality_adjustment = 0.0
        if quality_confidence < 0.5 and ml_available and not safety_override:
            penalty = min(max_negative, (0.5 - quality_confidence) * 0.2)
            quality_adjustment = -penalty if bool(fusion_settings.ALLOW_PERSONAL_NEGATIVE_ADJUSTMENT) else 0.0

        safety_adjustment = 0.0
        if safety_override and ml_available and ml_base_score is not None:
            safety_anchor = max(heuristic_risk_score, baseline_adjusted_risk, personalized_risk_score)
            safety_adjustment = min(max_positive, max(0.0, safety_anchor - ml_base_score))

        if bool(fusion_settings.MODEL_PERSONALIZATION_FUSION_ENABLED) and ml_available and ml_base_score is not None:
            base_score = ml_base_score
            fusion_mode = "model_plus_personalization"
            fusion_reason = "ml_base_plus_personalization"
        elif bool(fusion_settings.FALLBACK_TO_HEURISTIC_IF_MODEL_UNAVAILABLE):
            base_score = personalized_risk_score
            fusion_mode = "fallback_personalization_only"
            fusion_reason = ml_result.get("reason") or "model_unavailable"
        else:
            base_score = heuristic_risk_score
            fusion_mode = "fallback_heuristic_only"
            fusion_reason = ml_result.get("reason") or "heuristic_fallback"

        final_risk_score = _clamp01(
            base_score + bounded_personal_adjustment + quality_adjustment + safety_adjustment
        )

        return {
            "ml_base_score": round(ml_base_score, 4) if ml_base_score is not None else None,
            "ml_available": ml_available,
            "ml_confidence": round(ml_confidence, 4),
            "model_version": model_version,
            "heuristic_risk_score": round(heuristic_risk_score, 4),
            "baseline_adjusted_risk": round(baseline_adjusted_risk, 4),
            "personalized_risk_score": round(personalized_risk_score, 4),
            "baseline_personal_adjustment": round(baseline_personal_adjustment, 4),
            "adaptive_personal_adjustment": round(adaptive_personal_adjustment, 4),
            "trend_adjustment": round(trend_adjustment, 4),
            "feedback_adjustment": round(feedback_adjustment, 4),
            "personal_adjustment": round(bounded_personal_adjustment, 4),
            "quality_adjustment": round(quality_adjustment, 4),
            "safety_adjustment": round(safety_adjustment, 4),
            "final_risk_score": round(final_risk_score, 4),
            "fusion_mode": fusion_mode,
            "fusion_reason": fusion_reason,
        }


risk_fusion_service = RiskFusionService()