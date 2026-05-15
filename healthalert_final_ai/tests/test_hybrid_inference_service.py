import numpy as np

from src.healthalert.inference.hybrid_inference_service import HybridInferenceService


def _imu():
    rng = np.random.RandomState(0)
    return rng.normal(0, 1, (6, 200)).astype(np.float32)


def _ppg():
    t = np.linspace(0, 4, 200)
    return (np.sin(2 * np.pi * 1.2 * t)).astype(np.float32)


def test_imu_only_no_crash_and_ppg_missing_reason():
    s = HybridInferenceService(
        config_path="config/hybrid_runtime_config.yaml",
        device="cpu",
        enable_temporal_smoothing=False,
    )
    out = s.infer(imu_window=_imu(), ppg_window=None, vitals_values=None, user_id="t1")
    assert out["ppg_quality_label"] == "missing"
    assert "ppg_missing" in out["reasons"]
    assert 0.0 <= out["final_risk_score"] <= 100.0


def test_vitals_and_gait_ml_disabled_still_runs():
    s = HybridInferenceService(
        config_path="config/hybrid_runtime_config.yaml",
        device="cpu",
        enable_temporal_smoothing=False,
    )
    out = s.infer(
        imu_window=_imu(),
        ppg_window=_ppg(),
        vitals_values={"hr": 102.0, "spo2": 94.0},
        user_id="t2",
    )
    assert "risk_level" in out
    assert out["risk_level"] in {"normal", "caution", "high_risk", "critical"}
    assert len(out["reasons"]) > 0
