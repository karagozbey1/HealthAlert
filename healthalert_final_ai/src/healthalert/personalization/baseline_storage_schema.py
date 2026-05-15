"""
baseline_storage_schema.py
─────────────────────────────────────────────────────────────────────────────
JSON schema and dataclass definitions for the UserBaselineProfile.

IMPORTANT:
  This is NOT model training.
  No backpropagation. No weight updates.
  This stores each user's normal values only.

  Expert model parameters are NEVER modified per user.
  The personalization layer stores baseline statistics and
  updates them only during verified safe/normal periods.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class UserBaselineProfile:
    """
    Stores a user's normal physiological and motion baseline.
    Updated at runtime only during safe (normal/low risk) periods.
    """

    user_id: str

    # Resting heart rate statistics (BPM)
    resting_hr_median: Optional[float] = None
    resting_hr_iqr: Optional[float] = None

    # Walking heart rate statistics (BPM)
    walking_hr_median: Optional[float] = None

    # SpO2 baseline (if available, 0-100)
    spo2_median: Optional[float] = None

    # Motion intensity (device-specific units)
    motion_intensity_median: Optional[float] = None
    motion_intensity_iqr: Optional[float] = None

    # Gait instability score (0-1 from gait expert)
    gait_instability_median: Optional[float] = None

    # Risk score during normal periods (0-100)
    normal_risk_score_median: Optional[float] = None

    # PPG quality typical value (0-1)
    ppg_quality_typical: Optional[float] = None

    # Daily activity pattern summary (activity_class -> frequency fraction)
    daily_activity_pattern: Dict[str, float] = field(default_factory=dict)

    # Calibration metadata
    calibration_days: int = 0
    n_baseline_windows: int = 0
    confidence: float = 0.0   # 0.0=cold-start, 1.0=fully calibrated

    # Timestamps (ISO8601 strings)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str | Path) -> "UserBaselineProfile":
        with open(path, encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def cold_start(cls, user_id: str) -> "UserBaselineProfile":
        """Return a zero-confidence baseline for a new user."""
        return cls(user_id=user_id, confidence=0.0, calibration_days=0)

    def is_calibrated(self, min_confidence: float = 0.3) -> bool:
        """True if baseline has enough data to be used for personalization."""
        return self.confidence >= min_confidence and self.n_baseline_windows >= 50


# Baseline update guard — rules that must ALL be True before updating baseline
def baseline_update_allowed(
    final_risk_score: float,
    fall_probability: float,
    ppg_quality_score: Optional[float],
    risk_level: str,
    user_confirmed_emergency: bool = False,
    signal_confidence: float = 1.0,
) -> bool:
    """
    Returns True only if conditions are safe enough to update baseline.

    Safe update conditions:
      - risk_level is "normal" or "caution"
      - fall_probability < 0.3
      - final_risk_score < 40
      - ppg_quality >= 0.5 (if PPG baseline is being updated)
      - user did not confirm emergency
      - signal_confidence >= 0.5

    Does NOT update baseline during:
      - high fall_probability
      - high final_risk_score
      - high_risk or critical risk_level
      - poor PPG signal (for PPG-related baseline values)
      - missing or corrupt sensor data
      - unresolved user emergency
    """
    if user_confirmed_emergency:
        return False
    if risk_level in ("high_risk", "critical"):
        return False
    if fall_probability >= 0.3:
        return False
    if final_risk_score >= 40.0:
        return False
    if signal_confidence < 0.5:
        return False
    # PPG quality check is handled separately in update logic
    return True


# Export example schema JSON
def write_schema_example(out_path: Path) -> None:
    """Write an annotated example of the UserBaselineProfile JSON schema."""
    example = UserBaselineProfile(
        user_id="demo_user_001",
        resting_hr_median=68.5,
        resting_hr_iqr=8.2,
        walking_hr_median=95.0,
        spo2_median=97.5,
        motion_intensity_median=0.15,
        motion_intensity_iqr=0.08,
        gait_instability_median=0.12,
        normal_risk_score_median=12.4,
        ppg_quality_typical=0.88,
        daily_activity_pattern={"sitting": 0.45, "walking": 0.25, "standing": 0.20, "lying": 0.10},
        calibration_days=7,
        n_baseline_windows=2500,
        confidence=0.85,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    example.save(out_path)
