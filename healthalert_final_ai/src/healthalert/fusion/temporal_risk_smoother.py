from __future__ import annotations

import time
from collections import deque
from typing import Any, Dict, List


LEVELS = ["normal", "caution", "high_risk", "critical"]
ACTION_BY_LEVEL = {
    "normal": "continue_monitoring",
    "caution": "increase_monitoring",
    "high_risk": "prepare_alert",
    "critical": "immediate_check",
}


def _idx(level: str) -> int:
    try:
        return LEVELS.index(level)
    except ValueError:
        return 0


def _level(i: int) -> str:
    return LEVELS[max(0, min(len(LEVELS) - 1, i))]


class TemporalRiskSmoother:
    def __init__(
        self,
        history_size: int = 5,
        escalation_windows: int = 2,
        deescalation_windows: int = 3,
        cooldown_seconds: float = 120.0,
        ema_alpha: float = 0.4,
    ) -> None:
        self.history = deque(maxlen=history_size)
        self.escalation_windows = escalation_windows
        self.deescalation_windows = deescalation_windows
        self.cooldown_seconds = cooldown_seconds
        self.ema_alpha = ema_alpha
        self._smoothed_score = None
        self._current_level = "normal"
        self._up_count = 0
        self._down_count = 0
        self._cooldown_until = 0.0

    def update(
        self,
        fusion_result: Dict[str, Any],
        *,
        user_confirmed_okay: bool = False,
    ) -> Dict[str, Any]:
        if user_confirmed_okay:
            self._cooldown_until = time.time() + min(30.0, self.cooldown_seconds / 4.0)
            self._current_level = "normal"
            self._smoothed_score = 0.0
            out = dict(fusion_result)
            out["final_risk_score"] = 0.0
            out["risk_level"] = "normal"
            out["reasons"] = list(out.get("reasons", [])) + ["user_confirmed_okay_cooldown"]
            out["temporal_smoothing_applied"] = True
            return out

        raw_score = float(fusion_result.get("final_risk_score", 0.0))
        raw_level = fusion_result.get("risk_level", "normal")

        first_observation = self._smoothed_score is None
        if first_observation:
            self._smoothed_score = raw_score
            self._current_level = raw_level
        else:
            self._smoothed_score = self.ema_alpha * raw_score + (1.0 - self.ema_alpha) * self._smoothed_score
        self._smoothed_score = max(0.0, min(100.0, self._smoothed_score))
        self.history.append({"score": raw_score, "level": raw_level})

        now = time.time()
        cur_i = _idx(self._current_level)
        raw_i = _idx(raw_level)

        if first_observation:
            self._up_count = 0
            self._down_count = 0
        elif raw_i > cur_i:
            self._up_count += 1
            self._down_count = 0
        elif raw_i < cur_i:
            self._down_count += 1
            self._up_count = 0
        else:
            self._up_count = 0
            self._down_count = 0

        if self._up_count >= self.escalation_windows:
            self._current_level = _level(cur_i + 1)
            self._up_count = 0
        elif self._down_count >= self.deescalation_windows:
            self._current_level = _level(cur_i - 1)
            self._down_count = 0

        if now < self._cooldown_until and _idx(self._current_level) > _idx("high_risk"):
            self._current_level = "high_risk"

        out = dict(fusion_result)
        out["raw_final_risk_score"] = round(raw_score, 3)
        out["raw_risk_level"] = raw_level
        out["final_risk_score"] = round(self._smoothed_score, 3)
        out["risk_level"] = self._current_level
        out["recommended_action"] = ACTION_BY_LEVEL.get(self._current_level, "continue_monitoring")
        out["temporal_smoothing_applied"] = True
        return out
