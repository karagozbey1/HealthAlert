"""
risk_thresholds.py
─────────────────────────────────────────────────────────────────────────────
Risk level thresholds and component scoring weights for the Risk Fusion Engine.

These values control the final_risk_score → risk_level mapping
and the contribution weights from each expert.

Adjust these thresholds based on clinical validation outcomes.
Do NOT increase fall component weight above 0.55 without evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

# ─── Risk level thresholds (final_risk_score 0-100) ──────────────────────────

RISK_LEVEL_THRESHOLDS: Dict[str, float] = {
    "normal": 25.0,     # score < 25  → normal
    "caution": 50.0,    # 25 <= score < 50  → caution
    "high_risk": 70.0,  # 50 <= score < 70  → high_risk
    "critical": 100.0,  # score >= 70  → critical
}


def score_to_risk_level(score: float) -> str:
    if score < RISK_LEVEL_THRESHOLDS["normal"]:
        return "normal"
    if score < RISK_LEVEL_THRESHOLDS["caution"]:
        return "caution"
    if score < RISK_LEVEL_THRESHOLDS["high_risk"]:
        return "high_risk"
    return "critical"


# ─── Component weights (must sum to 1.0 for base components) ─────────────────

@dataclass
class FusionWeights:
    """
    Weights for each component in the Risk Fusion Engine.

    Base component max scores sum to 90 points (post-impact can push to 100).
    Personalization adjustment: -10 to +20 points.
    Quality/confidence adjustment: reduces unreliable components.
    """

    # Base component max contributions (points out of 100)
    fall_component_max: float = 55.0       # fall expert contribution
    gait_component_max: float = 15.0       # gait instability contribution
    vitals_component_max: float = 10.0     # vitals context contribution
    near_fall_component_max: float = 10.0  # near_fall signal / fall uncertainty band

    # Personalization adjustment range
    personalization_min_adjustment: float = -10.0
    personalization_max_adjustment: float = 20.0

    # Activity modifier (running reduces motion-based false positives)
    running_false_positive_reduction: float = 0.30  # 30% reduction when running

    # Collapse / reliability guards
    min_fall_precision_for_full_weight: float = 0.40
    min_ppg_quality_for_vitals: float = 0.50

    # Recommended actions per risk level
    recommended_actions: Dict[str, str] = field(default_factory=lambda: {
        "normal": "continue_monitoring",
        "caution": "increase_monitoring_frequency",
        "high_risk": "prepare_alert",
        "critical": "ask_user_are_you_okay",
    })


DEFAULT_WEIGHTS = FusionWeights()
