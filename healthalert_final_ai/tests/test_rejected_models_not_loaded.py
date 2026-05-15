import numpy as np

from src.healthalert.inference.hybrid_inference_service import HybridInferenceService


REJECTED_MARKERS = [
    "activity_expert/best_model.pt",
    "activity_expert_balanced",
    "activity_expert_v2/best_model.pt",
    "exp_b_pamap2_only_baseline",
    "exp_c_mixed_global_zscore",
    "exp_d_mixed_per_window_zscore",
    "exp_e_mixed_source_balanced",
    "exp_f_mixed_class_source_balanced",
    "exp_g_mixed_global_zscore_clipped",
    "exp_h_mixed_sensor_ankle",
    "exp_h_mixed_sensor_chest",
    "exp_h_mixed_sensor_hand",
    "gait_instability_v2_2_ablation",
    "gait_instability_expert/best_model.pt",
    "vitals_context_expert",
]

ACCEPTED_MARKERS = [
    "fall_expert_core_no_umafall/best_model.pt",
    "ppg_quality_expert/best_model.pt",
    "activity_expert_v2_uci_only/best_model.pt",
    "gait_instability_v2_ablation/pw2.0_lr3e-04_ft0.30/best_model.pt",
]


def _imu():
    rng = np.random.RandomState(123)
    return rng.normal(0, 1, (6, 200)).astype(np.float32)


def _ppg():
    t = np.linspace(0, 4, 200)
    return np.sin(2 * np.pi * 1.2 * t).astype(np.float32)


def test_only_final_accepted_checkpoints_are_loaded():
    service = HybridInferenceService(
        config_path="config/hybrid_runtime_config.yaml",
        device="cpu",
        enable_temporal_smoothing=False,
    )
    service.infer(
        imu_window=_imu(),
        ppg_window=_ppg(),
        vitals_values={"hr": 82.0, "spo2": 97.0},
        user_id="test_rejected_models_not_loaded",
    )

    loaded = "\n".join(service.loaded_model_paths)
    for marker in ACCEPTED_MARKERS:
        assert marker in loaded
    for marker in REJECTED_MARKERS:
        assert marker not in loaded


def test_disabled_models_are_reported_in_runtime_output():
    service = HybridInferenceService(
        config_path="config/hybrid_runtime_config.yaml",
        device="cpu",
        enable_temporal_smoothing=False,
    )
    out = service.infer(imu_window=_imu(), ppg_window=None, user_id="disabled_models_report")
    disabled = set(out["disabled_models"])
    assert {
        "activity_v0",
        "activity_balanced_v1",
        "activity_v2_pamap2_mixed",
        "gait_v2_2",
        "old_gait_instability",
        "vitals_context_expert",
        "vitals_context_model",
        "tremor_context",
    }.issubset(disabled)
