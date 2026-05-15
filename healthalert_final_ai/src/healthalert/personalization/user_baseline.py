"""
user_baseline.py
─────────────────────────────────────────────────────────────────────────────
UserBaselineEngine — Runtime baseline update engine.

IMPORTANT:
  This is NOT model training.
  No backpropagation. No fine-tuning.
  No modification to any expert model weights.

  This engine maintains a rolling statistics store for each user.
  It updates only when the system verifies safe/normal conditions.

Update algorithm:
  Uses exponential moving average (EMA) for smooth adaptation.
  alpha controls adaptation speed (lower = slower adaptation = more stable).

  new_value = alpha * current_observation + (1 - alpha) * old_baseline_value

  alpha is scaled by confidence:
    - cold-start user → alpha=0.5 (fast initial learning)
    - calibrated user → alpha=0.05 (slow stable adaptation)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.healthalert.personalization.baseline_storage_schema import (
    UserBaselineProfile,
    baseline_update_allowed,
)

log = logging.getLogger("healthalert.personalization.user_baseline")

# EMA alpha boundaries
ALPHA_COLD_START = 0.50    # fast update for new users
ALPHA_CALIBRATED = 0.05    # slow stable update for experienced users
CONFIDENCE_FULL = 0.90     # confidence threshold for fully calibrated
CONFIDENCE_THRESHOLD = 0.30  # minimum for baseline to be "active"


class UserBaselineEngine:
    """
    Runtime personalization engine for one user.

    Usage:
        engine = UserBaselineEngine(user_id="user_001")
        engine.load("path/to/user_001_baseline.json")  # or starts cold

        # Each window inference cycle:
        if engine.should_update(risk_score, fall_prob, ppg_quality, risk_level):
            engine.update(observation)

        deviation = engine.compute_deviation(observation)
    """

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.profile = UserBaselineProfile.cold_start(user_id)

    def load(self, path: str) -> None:
        try:
            self.profile = UserBaselineProfile.load(path)
            log.info(f"Loaded baseline for user {self.user_id} (confidence={self.profile.confidence:.2f})")
        except FileNotFoundError:
            log.info(f"No baseline file for user {self.user_id} — cold start.")
        except Exception as exc:
            log.warning(f"Failed to load baseline for {self.user_id}: {exc} — cold start.")

    def save(self, path: str) -> None:
        self.profile.save(path)
        log.debug(f"Baseline saved → {path}")

    def should_update(
        self,
        final_risk_score: float,
        fall_probability: float,
        ppg_quality_score: Optional[float],
        risk_level: str,
        user_confirmed_emergency: bool = False,
        signal_confidence: float = 1.0,
    ) -> bool:
        return baseline_update_allowed(
            final_risk_score=final_risk_score,
            fall_probability=fall_probability,
            ppg_quality_score=ppg_quality_score,
            risk_level=risk_level,
            user_confirmed_emergency=user_confirmed_emergency,
            signal_confidence=signal_confidence,
        )

    def update(
        self,
        observation: Dict[str, Any],
        ppg_quality_score: Optional[float] = None,
    ) -> None:
        """
        Update baseline statistics with a new safe-period observation.

        Args:
            observation: dict with optional keys:
              - heart_rate, spo2, motion_intensity, gait_instability_score,
                risk_score, ppg_quality_score, activity_class
            ppg_quality_score: current PPG quality (skips PPG/vitals update if poor)
        """
        alpha = self._alpha()
        p = self.profile

        # Heart rate updates
        hr = observation.get("heart_rate")
        activity = observation.get("activity_class", "unknown")
        if hr is not None and hr > 0:
            if activity in ("sitting", "standing", "lying", "unknown"):
                p.resting_hr_median = _ema(p.resting_hr_median, hr, alpha)
            elif activity in ("walking",):
                p.walking_hr_median = _ema(p.walking_hr_median, hr, alpha)

        # SpO2 update (only if PPG quality is acceptable)
        spo2 = observation.get("spo2")
        if spo2 is not None and spo2 > 0:
            if ppg_quality_score is None or ppg_quality_score >= 0.5:
                p.spo2_median = _ema(p.spo2_median, spo2, alpha)

        # Motion intensity
        motion = observation.get("motion_intensity")
        if motion is not None:
            p.motion_intensity_median = _ema(p.motion_intensity_median, motion, alpha)

        # Gait instability
        gait = observation.get("gait_instability_score")
        if gait is not None:
            p.gait_instability_median = _ema(p.gait_instability_median, gait, alpha)

        # Normal risk score
        risk = observation.get("risk_score")
        if risk is not None:
            p.normal_risk_score_median = _ema(p.normal_risk_score_median, risk, alpha)

        # PPG quality typical
        if ppg_quality_score is not None and ppg_quality_score >= 0.5:
            p.ppg_quality_typical = _ema(p.ppg_quality_typical, ppg_quality_score, alpha)

        # Activity pattern update
        if activity and activity != "unknown":
            freq = p.daily_activity_pattern.get(activity, 0.0)
            # Smooth frequency estimate
            p.daily_activity_pattern[activity] = _ema(freq if freq > 0 else 0.0, 1.0, alpha * 0.2)

        # Metadata
        p.n_baseline_windows += 1
        p.calibration_days = max(p.calibration_days, 1)
        p.confidence = min(CONFIDENCE_FULL, p.n_baseline_windows / 2500)
        p.updated_at = datetime.utcnow().isoformat() + "Z"

    def compute_deviation(
        self, observation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute PersonalDeviationScore from current observation vs. user baseline.

        Returns:
            {
                "personal_deviation_score": float 0-1,
                "confidence": float 0-1,
                "reasons": List[str]
            }
        """
        if not self.profile.is_calibrated():
            return {
                "personal_deviation_score": 0.0,
                "confidence": 0.0,
                "reasons": ["baseline_not_calibrated_using_population_defaults"],
            }

        p = self.profile
        reasons: list[str] = []
        deviations: list[float] = []

        hr = observation.get("heart_rate")
        activity = observation.get("activity_class", "unknown")
        gait = observation.get("gait_instability_score")
        motion = observation.get("motion_intensity")

        # HR deviation (relative to activity context)
        if hr is not None and hr > 0:
            if activity in ("sitting", "standing", "lying") and p.resting_hr_median is not None:
                ratio = hr / max(p.resting_hr_median, 1.0)
                dev = max(0.0, (ratio - 1.0) / 0.5)  # 50% above baseline = max deviation
                deviations.append(min(dev, 1.0))
                if dev > 0.4:
                    reasons.append("heart_rate_above_user_resting_baseline")
            elif activity == "walking" and p.walking_hr_median is not None:
                ratio = hr / max(p.walking_hr_median, 1.0)
                dev = max(0.0, (ratio - 1.0) / 0.4)
                deviations.append(min(dev, 1.0))
                if dev > 0.3:
                    reasons.append("heart_rate_above_user_walking_baseline")

        # Add activity context to reasons if relevant
        if activity in ("sitting", "standing") and hr and p.resting_hr_median:
            if hr > p.resting_hr_median * 1.4:
                reasons.append(f"activity_context_{activity}")

        # Gait instability deviation
        if gait is not None and p.gait_instability_median is not None:
            dev = max(0.0, (gait - p.gait_instability_median) / max(p.gait_instability_median, 0.1))
            deviations.append(min(dev, 1.0))
            if dev > 0.5:
                reasons.append("gait_instability_above_user_baseline")

        # Motion intensity deviation
        if motion is not None and p.motion_intensity_median is not None:
            dev = max(0.0, abs(motion - p.motion_intensity_median) / max(p.motion_intensity_median, 0.05))
            deviations.append(min(dev * 0.5, 1.0))  # lower weight for motion
            if dev > 1.0:
                reasons.append("motion_intensity_unusual_for_user")

        if not deviations:
            return {
                "personal_deviation_score": 0.0,
                "confidence": self.profile.confidence,
                "reasons": ["no_deviation_signals_available"],
            }

        score = float(sum(deviations) / len(deviations))
        return {
            "personal_deviation_score": round(min(score, 1.0), 4),
            "confidence": round(self.profile.confidence, 4),
            "reasons": reasons,
        }

    def _alpha(self) -> float:
        """EMA alpha: fast for cold-start, slow for calibrated users."""
        if self.profile.confidence <= 0.1:
            return ALPHA_COLD_START
        return ALPHA_COLD_START + (ALPHA_CALIBRATED - ALPHA_COLD_START) * min(
            self.profile.confidence / CONFIDENCE_FULL, 1.0
        )


# ─── EMA helper ──────────────────────────────────────────────────────────────

def _ema(old: Optional[float], new: float, alpha: float) -> float:
    """Exponential moving average. Handles cold-start (old=None) case."""
    if old is None:
        return new
    return alpha * new + (1.0 - alpha) * old
