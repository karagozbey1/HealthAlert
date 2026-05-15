"""
simulate_personalization_engine.py
─────────────────────────────────────────────────────────────────────────────
Demonstration of the runtime personalization engine.

Shows:
  1. Cold-start behavior (no baseline)
  2. Baseline accumulation over safe windows
  3. Deviation scoring against accumulated baseline
  4. Baseline update blocking during high-risk periods

Usage:
  python scripts/simulate_personalization_engine.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.healthalert.personalization.user_baseline import UserBaselineEngine
from src.healthalert.personalization.baseline_storage_schema import write_schema_example

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("simulate_personalization")

OUT_DIR = ROOT / "outputs" / "hybrid_redesign" / "personalization"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def simulate_normal_period(engine: UserBaselineEngine, n: int, rng: np.random.RandomState) -> None:
    """Simulate safe/normal windows to build up baseline."""
    for _ in range(n):
        obs = {
            "heart_rate": float(rng.normal(70, 8)),
            "spo2": float(rng.normal(97.5, 0.5)),
            "motion_intensity": float(abs(rng.normal(0.15, 0.05))),
            "gait_instability_score": float(abs(rng.normal(0.10, 0.04))),
            "activity_class": rng.choice(["sitting", "standing", "walking"]),
            "risk_score": float(abs(rng.normal(12.0, 4.0))),
        }
        ppg_quality = float(rng.uniform(0.75, 0.99))
        if engine.should_update(
            final_risk_score=obs["risk_score"],
            fall_probability=0.02,
            ppg_quality_score=ppg_quality,
            risk_level="normal",
        ):
            engine.update(obs, ppg_quality_score=ppg_quality)


def main() -> None:
    rng = np.random.RandomState(42)

    # Write schema example
    schema_path = OUT_DIR / "user_baseline_schema.json"
    write_schema_example(schema_path)
    log.info(f"Schema example written → {schema_path}")

    # === Cold-start user ===
    engine = UserBaselineEngine(user_id="demo_user_cold")
    dev_cold = engine.compute_deviation({
        "heart_rate": 95.0,
        "activity_class": "sitting",
        "gait_instability_score": 0.25,
        "motion_intensity": 0.20,
    })
    log.info(f"\nCold-start deviation: {dev_cold}")
    assert dev_cold["confidence"] == 0.0, "Cold-start must have confidence=0"

    # === Baseline accumulation (50 safe windows) ===
    simulate_normal_period(engine, 50, rng)
    log.info(f"After 50 safe windows — confidence: {engine.profile.confidence:.3f}")
    log.info(f"  resting_hr_median: {engine.profile.resting_hr_median}")
    log.info(f"  gait_instability_median: {engine.profile.gait_instability_median}")

    # === More safe windows (200 total) ===
    simulate_normal_period(engine, 150, rng)
    log.info(f"After 200 safe windows — confidence: {engine.profile.confidence:.3f}")

    # === Deviation during normal observation ===
    normal_obs = {
        "heart_rate": 72.0,
        "activity_class": "sitting",
        "gait_instability_score": 0.10,
        "motion_intensity": 0.15,
    }
    dev_normal = engine.compute_deviation(normal_obs)
    log.info(f"\nDeviation (normal observation): {dev_normal}")

    # === Deviation during abnormal observation ===
    abnormal_obs = {
        "heart_rate": 130.0,   # very high while sitting
        "activity_class": "sitting",
        "gait_instability_score": 0.75,  # much higher than baseline
        "motion_intensity": 0.80,
    }
    dev_abnormal = engine.compute_deviation(abnormal_obs)
    log.info(f"\nDeviation (abnormal observation): {dev_abnormal}")
    assert dev_abnormal["personal_deviation_score"] > dev_normal["personal_deviation_score"], \
        "Abnormal observation must score higher than normal"

    # === Update blocking during high risk ===
    blocked = engine.should_update(
        final_risk_score=80.0,
        fall_probability=0.85,
        ppg_quality_score=0.9,
        risk_level="critical",
    )
    log.info(f"\nBaseline update during critical risk: {blocked} (expected: False)")
    assert not blocked, "Baseline must NOT update during critical risk"

    # === Save baseline ===
    baseline_path = OUT_DIR / "demo_user_baseline.json"
    engine.save(str(baseline_path))
    log.info(f"\nBaseline saved → {baseline_path}")

    # === Load and verify ===
    engine2 = UserBaselineEngine(user_id="demo_user_cold")
    engine2.load(str(baseline_path))
    assert engine2.profile.n_baseline_windows == engine.profile.n_baseline_windows

    log.info("\n=== Personalization engine simulation PASSED ===")

    # Write summary
    summary = {
        "cold_start_deviation": dev_cold,
        "normal_deviation": dev_normal,
        "abnormal_deviation": dev_abnormal,
        "baseline_blocked_during_critical": blocked,
        "final_profile": engine.profile.to_dict(),
    }
    with open(OUT_DIR / "personalization_simulation_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"Summary → {OUT_DIR / 'personalization_simulation_summary.json'}")


if __name__ == "__main__":
    main()
