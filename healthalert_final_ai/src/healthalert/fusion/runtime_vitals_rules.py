from __future__ import annotations

from typing import Any, Dict, Optional


def compute_runtime_vitals_adjustment(
    *,
    ppg_quality_label: Optional[str],
    ppg_quality_score: Optional[float],
    vitals: Optional[Dict[str, float]],
    baseline: Optional[Dict[str, float]],
) -> Dict[str, Any]:
    reasons = []
    if vitals is None:
        return {"adjustment": 0.0, "reasons": ["vitals_missing"]}
    if ppg_quality_label == "bad_quality" or ppg_quality_score is None or ppg_quality_score < 0.5:
        return {"adjustment": 0.0, "reasons": ["ppg_quality_gate_closed"]}

    hr = vitals.get("hr")
    spo2 = vitals.get("spo2")
    adj = 0.0

    if baseline is None:
        reasons.append("baseline_missing")
        hr_base = 72.0
        spo2_base = 97.0
    else:
        hr_base = float(baseline.get("resting_hr_median", 72.0))
        spo2_base = float(baseline.get("spo2_median", 97.0))

    if hr is not None:
        if hr > hr_base * 1.25:
            adj += 5.0
            reasons.append("hr_above_baseline")
        elif hr < hr_base * 0.70:
            adj += 3.0
            reasons.append("hr_below_baseline")

    if spo2 is not None:
        if spo2 < min(94.0, spo2_base - 2.0):
            adj += 8.0
            reasons.append("spo2_drop")

    return {"adjustment": float(max(0.0, min(15.0, adj))), "reasons": reasons or ["vitals_normal_range"]}
