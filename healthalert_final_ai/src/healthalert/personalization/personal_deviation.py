"""
personal_deviation.py
─────────────────────────────────────────────────────────────────────────────
PersonalDeviationScore computation helpers.

This module provides standalone deviation scoring that can be used
without a full UserBaselineEngine instance — useful for testing
and for the risk fusion engine when the baseline is passed as a dict.

IMPORTANT:
  This is NOT model training.
  All computations are pure statistics + heuristics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


POPULATION_DEFAULTS = {
    "resting_hr_median": 72.0,
    "resting_hr_iqr": 12.0,
    "walking_hr_median": 100.0,
    "spo2_median": 97.0,
    "motion_intensity_median": 0.20,
    "motion_intensity_iqr": 0.10,
    "gait_instability_median": 0.15,
    "normal_risk_score_median": 15.0,
}


def compute_deviation_score(
    observation: Dict[str, Any],
    baseline: Optional[Dict[str, Any]] = None,
    baseline_confidence: float = 0.0,
) -> Dict[str, Any]:
    """
    Compute PersonalDeviationScore.

    Args:
        observation: current sensor/model outputs, e.g.:
            {
                "heart_rate": float,
                "spo2": float,
                "motion_intensity": float,
                "gait_instability_score": float,
                "activity_class": str,
                "risk_score": float,
            }
        baseline: UserBaselineProfile dict (or None for cold-start)
        baseline_confidence: 0.0 = cold-start, 1.0 = fully calibrated

    Returns:
        {
            "personal_deviation_score": float 0-1,
            "confidence": float 0-1,
            "reasons": List[str]
        }
    """
    if baseline is None or baseline_confidence < 0.30:
        # Cold-start: use population defaults
        baseline = POPULATION_DEFAULTS.copy()
        baseline_confidence = min(baseline_confidence, 0.2)

    reasons: List[str] = []
    deviations: List[float] = []

    hr = observation.get("heart_rate")
    activity = observation.get("activity_class", "unknown")
    gait = observation.get("gait_instability_score")
    motion = observation.get("motion_intensity")

    # ── Heart rate deviation ───────────────────────────────────────────────
    resting_hr = baseline.get("resting_hr_median") or POPULATION_DEFAULTS["resting_hr_median"]
    walking_hr = baseline.get("walking_hr_median") or POPULATION_DEFAULTS["walking_hr_median"]

    if hr and hr > 0:
        if activity in ("sitting", "standing", "lying", "unknown"):
            ratio = hr / max(resting_hr, 1.0)
            dev = max(0.0, (ratio - 1.0) / 0.5)
            deviations.append(min(dev, 1.0))
            if dev > 0.4:
                reasons.append("heart_rate_above_user_resting_baseline")
                if activity in ("sitting", "standing"):
                    reasons.append(f"activity_context_{activity}")
        elif activity == "walking":
            ratio = hr / max(walking_hr, 1.0)
            dev = max(0.0, (ratio - 1.0) / 0.4)
            deviations.append(min(dev, 1.0))
            if dev > 0.3:
                reasons.append("heart_rate_above_user_walking_baseline")

    # ── Gait instability deviation ─────────────────────────────────────────
    gait_base = baseline.get("gait_instability_median") or POPULATION_DEFAULTS["gait_instability_median"]
    if gait is not None:
        dev = max(0.0, (gait - gait_base) / max(gait_base, 0.05))
        deviations.append(min(dev * 0.8, 1.0))
        if dev > 0.5:
            reasons.append("gait_instability_above_user_baseline")

    # ── Motion intensity deviation ─────────────────────────────────────────
    motion_base = baseline.get("motion_intensity_median") or POPULATION_DEFAULTS["motion_intensity_median"]
    if motion is not None:
        dev = max(0.0, abs(motion - motion_base) / max(motion_base, 0.05))
        deviations.append(min(dev * 0.5, 1.0))
        if dev > 1.0:
            reasons.append("motion_intensity_unusual_for_user")

    if not deviations:
        return {
            "personal_deviation_score": 0.0,
            "confidence": round(baseline_confidence, 4),
            "reasons": ["no_deviation_signals_available"],
        }

    score = float(sum(deviations) / len(deviations))
    return {
        "personal_deviation_score": round(min(score, 1.0), 4),
        "confidence": round(baseline_confidence, 4),
        "reasons": reasons,
    }
