"""
test_risk_fusion_engine.py
─────────────────────────────────────────────────────────────────────────────
Quick functional test script for the Risk Fusion Engine.

Tests:
  1. Output is always in [0, 100]
  2. Missing PPG does not crash
  3. Missing IMU gives zero fall contribution
  4. High fall + post-impact → critical level
  5. Running activity reduces gait/near_fall risk
  6. Personalization adjustment requires confidence >= 0.30
  7. Output contains all required keys

Usage:
  python scripts/test_risk_fusion_engine.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.healthalert.fusion.risk_fusion_engine import RiskFusionEngine
from src.healthalert.fusion.risk_thresholds import score_to_risk_level

REQUIRED_KEYS = {
    "ml_risk_score", "personalization_adjustment", "confidence_score",
    "final_risk_score", "risk_level", "reasons", "recommended_action",
}

engine = RiskFusionEngine()
passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f": {detail}" if detail else ""))
    if condition:
        passed += 1
    else:
        failed += 1


print("\n=== Risk Fusion Engine Tests ===\n")

# ── Test 1: Output always 0-100 ───────────────────────────────────────────────
for fp in [0.0, 0.3, 0.7, 0.99]:
    r = engine.fuse(fall_probability=fp)
    check(
        f"score_in_range (fall_prob={fp})",
        0.0 <= r["final_risk_score"] <= 100.0,
        f"score={r['final_risk_score']}"
    )

# ── Test 2: Missing PPG (None) does not crash ─────────────────────────────────
try:
    r = engine.fuse(
        fall_probability=0.2,
        ppg_quality_score=None,
        missing_modality_flags={"ppg_missing": True},
    )
    check("missing_ppg_no_crash", True, f"risk_level={r['risk_level']}")
    check("missing_ppg_reason_present", "ppg_missing_vitals_unavailable" in r["reasons"])
except Exception as e:
    check("missing_ppg_no_crash", False, str(e))

# ── Test 3: Missing IMU → zero fall contribution ──────────────────────────────
r_imu_miss = engine.fuse(
    fall_probability=0.95,
    missing_modality_flags={"imu_missing": True},
)
check(
    "missing_imu_zero_fall_score",
    r_imu_miss["_components"]["fall_score"] == 0.0,
    f"fall_score={r_imu_miss['_components']['fall_score']}"
)
check(
    "missing_imu_reason_present",
    "imu_missing_fall_detection_unavailable" in r_imu_miss["reasons"]
)

# ── Test 4: High fall + post-impact → high risk ───────────────────────────────
r_fall = engine.fuse(
    fall_probability=0.90,
    gait_instability_score=0.8,
    activity_context_probs={"lying": 0.8, "walking": 0.1},
)
check(
    "high_fall_plus_post_impact_high_risk",
    r_fall["risk_level"] in ("high_risk", "critical"),
    f"risk_level={r_fall['risk_level']}, score={r_fall['final_risk_score']}"
)

# ── Test 5: Running activity reduces score vs walking ─────────────────────────
r_running = engine.fuse(
    fall_probability=0.2,
    gait_instability_score=0.4,
    activity_context_probs={"running": 0.7},
)
r_walking = engine.fuse(
    fall_probability=0.2,
    gait_instability_score=0.4,
    activity_context_probs={"walking": 0.7},
)
check(
    "running_reduces_risk_vs_walking",
    r_running["final_risk_score"] <= r_walking["final_risk_score"],
    f"running={r_running['final_risk_score']}, walking={r_walking['final_risk_score']}"
)

# ── Test 6: Personalization adjustment gated by confidence ────────────────────
r_low_conf = engine.fuse(fall_probability=0.1, personal_deviation_score=0.9, personalization_confidence=0.1)
r_high_conf = engine.fuse(fall_probability=0.1, personal_deviation_score=0.9, personalization_confidence=0.8)
check(
    "personalization_cold_start_no_adjustment",
    r_low_conf["personalization_adjustment"] == 0.0,
    f"adjustment={r_low_conf['personalization_adjustment']}"
)
check(
    "personalization_high_conf_adjustment_positive",
    r_high_conf["personalization_adjustment"] > 0.0,
    f"adjustment={r_high_conf['personalization_adjustment']}"
)

# ── Test 7: All required keys present ────────────────────────────────────────
r_full = engine.fuse(
    fall_probability=0.3,
    gait_instability_score=0.2,
    ppg_quality_score=0.8,
    vitals_context_score=0.3,
    personal_deviation_score=0.4,
    personalization_confidence=0.6,
    signal_confidence=0.9,
)
missing_keys = REQUIRED_KEYS - set(r_full.keys())
check("all_required_keys_present", len(missing_keys) == 0, f"missing={missing_keys}")

# ── Test 8: Normal baseline → normal risk ─────────────────────────────────────
r_normal = engine.fuse(
    fall_probability=0.01,
    gait_instability_score=0.05,
    ppg_quality_score=0.95,
    vitals_context_score=0.05,
    personal_deviation_score=0.0,
    personalization_confidence=0.0,
    signal_confidence=1.0,
)
check("normal_baseline_normal_risk", r_normal["risk_level"] == "normal", f"risk_level={r_normal['risk_level']}")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n=== Results: {passed} PASSED, {failed} FAILED ===\n")

out = ROOT / "outputs" / "hybrid_redesign" / "fusion"
out.mkdir(parents=True, exist_ok=True)
with open(out / "risk_fusion_test_results.json", "w") as f:
    json.dump({"passed": passed, "failed": failed, "sample_result": r_full}, f, indent=2)

print(f"Results written → {out / 'risk_fusion_test_results.json'}")
sys.exit(0 if failed == 0 else 1)
