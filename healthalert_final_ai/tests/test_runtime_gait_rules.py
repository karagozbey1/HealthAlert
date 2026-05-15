import numpy as np

from src.healthalert.fusion.runtime_gait_rules import compute_runtime_gait_motion_score


def test_missing_imu_returns_zero():
    out = compute_runtime_gait_motion_score(None)
    assert out["score"] == 0.0
    assert "imu_missing" in out["reasons"]


def test_valid_imu_returns_score_in_range():
    rng = np.random.RandomState(1)
    imu = rng.normal(0, 1, (6, 200)).astype(np.float32)
    out = compute_runtime_gait_motion_score(imu)
    assert 0.0 <= out["score"] <= 1.0
    assert "motion_intensity" in out["features"]
