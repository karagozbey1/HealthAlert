import numpy as np

from src.healthalert.inference.hybrid_inference_service import HybridInferenceService


RISK_LEVELS = {"normal", "caution", "high_risk", "critical"}


def _service():
    return HybridInferenceService(
        config_path="config/hybrid_runtime_config.yaml",
        device="cpu",
        enable_temporal_smoothing=False,
    )


def _imu(seed=7):
    rng = np.random.RandomState(seed)
    return rng.normal(0, 1, (6, 200)).astype(np.float32)


def _ppg():
    t = np.linspace(0, 4, 200)
    return np.sin(2 * np.pi * 1.2 * t).astype(np.float32)


def _assert_common_output(out):
    assert 0.0 <= out["final_risk_score"] <= 100.0
    assert out["risk_level"] in RISK_LEVELS
    assert "fall_probability" in out
    assert "activity_context" in out
    assert "ppg_quality_label" in out
    assert "gait_abnormal_probability" in out
    assert "gait_contribution" in out
    assert "vitals_contribution" in out
    assert "personalization_adjustment" in out
    assert isinstance(out["reasons"], list)
    assert out["recommended_action"]
    assert isinstance(out["disabled_models"], list)


def test_imu_only_inference_works():
    out = _service().infer(imu_window=_imu(), ppg_window=None, user_id="imu_only_final")
    _assert_common_output(out)
    assert out["ppg_quality_label"] == "missing"


def test_imu_plus_ppg_inference_works():
    out = _service().infer(
        imu_window=_imu(),
        ppg_window=_ppg(),
        vitals_values={"hr": 84.0, "spo2": 97.0},
        user_id="imu_plus_ppg_final",
    )
    _assert_common_output(out)
    assert out["ppg_quality_label"] in {"good_quality", "bad_quality", "motion_artifact", "unknown"}


def test_ppg_missing_does_not_crash_and_zeroes_vitals_contribution():
    out = _service().infer(
        imu_window=_imu(),
        ppg_window=None,
        vitals_values={"hr": 92.0, "spo2": 96.0},
        user_id="ppg_missing_final",
    )
    _assert_common_output(out)
    assert out["vitals_contribution"] == 0.0
    assert "ppg_missing" in out["reasons"]


def test_missing_baseline_does_not_crash():
    out = _service().infer(
        imu_window=_imu(8),
        ppg_window=_ppg(),
        vitals_values={"hr": 88.0, "spo2": 96.0},
        user_id="baseline_missing_final",
    )
    _assert_common_output(out)
    assert out["cold_start_mode"] is True
