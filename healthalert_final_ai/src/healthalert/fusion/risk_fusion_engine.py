from __future__ import annotations

from typing import Any, Dict, List, Optional


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _risk_level(score_0_100: float) -> str:
    if score_0_100 < 25.0:
        return "normal"
    if score_0_100 < 50.0:
        return "caution"
    if score_0_100 < 75.0:
        return "high_risk"
    return "critical"


def _recommended_action(level: str) -> str:
    mapping = {
        "normal": "continue_monitoring",
        "caution": "increase_monitoring",
        "high_risk": "prepare_alert",
        "critical": "immediate_check",
    }
    return mapping.get(level, "continue_monitoring")


class RiskFusionEngine:
    """
    Final runtime risk fusion engine.
    Produces score in 0-100 and never crashes on missing modalities.
    """

    def __init__(
        self,
        *,
        fall_threshold_caution: float = 0.35,
        fall_threshold_balanced: float = 0.45,
        gait_max_contribution_points: float = 5.0,
    ) -> None:
        self.fall_threshold_caution = float(fall_threshold_caution)
        self.fall_threshold_balanced = float(fall_threshold_balanced)
        self.fall_threshold_very_high = 0.85
        self.gait_max_contribution_points = float(gait_max_contribution_points)

    def fuse(
        self,
        *,
        fall_probability: float,
        activity_context: str,
        ppg_quality_score: Optional[float],
        ppg_quality_label: Optional[str],
        runtime_vitals_adjustment: float,
        runtime_gait_motion_score: float,
        personalization_adjustment: float,
        signal_confidence: float,
        missing_modality_flags: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Any]:
        flags = missing_modality_flags or {}
        imu_missing = bool(flags.get("imu_missing", False))
        ppg_missing = bool(flags.get("ppg_missing", ppg_quality_score is None))
        baseline_missing = bool(flags.get("baseline_missing", False))
        post_impact_low_motion = bool(flags.get("post_impact_low_motion", False))

        reasons: List[str] = []

        fall_p = _clip01(fall_probability)
        gait_motion = _clip01(runtime_gait_motion_score)
        sig_conf = _clip01(signal_confidence)

        ppg_q = None if ppg_quality_score is None else _clip01(ppg_quality_score)
        ppg_label = ppg_quality_label or ("missing" if ppg_missing else "unknown")
        if ppg_missing:
            reasons.append("ppg_missing")

        if imu_missing:
            reasons.append("imu_missing")

        fall_component = 0.0
        if imu_missing:
            fall_component = 0.0
        elif fall_p < self.fall_threshold_caution:
            fall_component = 15.0 * (fall_p / self.fall_threshold_caution)
        elif fall_p < self.fall_threshold_balanced:
            fall_component = 20.0 + 15.0 * (
                (fall_p - self.fall_threshold_caution)
                / (self.fall_threshold_balanced - self.fall_threshold_caution)
            )
            reasons.append("fall_probability_caution_band")
        elif fall_p < self.fall_threshold_very_high:
            fall_component = 35.0 + 35.0 * (
                (fall_p - self.fall_threshold_balanced)
                / (self.fall_threshold_very_high - self.fall_threshold_balanced)
            )
            reasons.append("fall_probability_medium_high")
        else:
            fall_component = 78.0 + 12.0 * (
                (fall_p - self.fall_threshold_very_high)
                / (1.0 - self.fall_threshold_very_high)
            )
            reasons.append("fall_probability_very_high")
            if post_impact_low_motion:
                reasons.append("post_impact_low_motion")

        gait_component = 0.0
        if not imu_missing:
            raw_gait_component = self.gait_max_contribution_points * gait_motion
            if fall_p < self.fall_threshold_caution:
                gait_component = min(2.0, raw_gait_component * 0.4)
            else:
                gait_component = raw_gait_component
            gait_component = min(self.gait_max_contribution_points, gait_component)
            if gait_motion >= 0.6:
                reasons.append("gait_auxiliary_abnormal")
            elif gait_motion >= 0.1:
                reasons.append("gait_auxiliary_low_weight")

        vitals_component = 0.0
        if ppg_missing:
            vitals_component = 0.0
        elif ppg_label == "bad_quality" or (ppg_q is not None and ppg_q < 0.5):
            vitals_component = max(0.0, runtime_vitals_adjustment * 0.25)
            reasons.append("ppg_quality_bad_vitals_reduced")
        else:
            vitals_component = max(0.0, runtime_vitals_adjustment)
            reasons.append("ppg_quality_good")

        activity_modifier = 0.0
        if activity_context in {"lying", "sitting"} and fall_p >= self.fall_threshold_balanced:
            activity_modifier += 3.0
            reasons.append(f"activity_context_{activity_context}")
        if activity_context in {"walking", "running"} and fall_p < self.fall_threshold_balanced:
            activity_modifier -= 2.0

        personal_adj = float(personalization_adjustment)
        if baseline_missing:
            personal_adj = 0.0
            reasons.append("baseline_missing")

        raw = fall_component + gait_component + vitals_component + activity_modifier + personal_adj
        raw = raw * (0.7 + 0.3 * sig_conf)
        final_score = max(0.0, min(100.0, raw))
        level = _risk_level(final_score)

        if post_impact_low_motion and fall_p >= self.fall_threshold_very_high:
            level = "critical"
            final_score = max(final_score, 85.0)

        if not reasons:
            reasons.append("no_strong_risk_signals")

        confidence = sig_conf
        if imu_missing or ppg_missing:
            confidence = max(0.2, confidence - 0.2)
        confidence = _clip01(confidence)

        return {
            "fall_probability": round(fall_p, 4),
            "activity_context": activity_context,
            "ppg_quality": {
                "score": None if ppg_q is None else round(ppg_q, 4),
                "label": ppg_label,
            },
            "vitals_contribution": round(vitals_component, 3),
            "gait_contribution": round(gait_component, 3),
            "personalization_adjustment": round(personal_adj, 3),
            "final_risk_score": round(final_score, 3),
            "risk_level": level,
            "confidence_score": round(confidence, 4),
            "reasons": reasons,
            "recommended_action": _recommended_action(level),
        }
