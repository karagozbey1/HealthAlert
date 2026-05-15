from pathlib import Path

import yaml


ACCEPTED_PATHS = {
    "fall_expert": "outputs/hybrid_redesign/fall_expert_core_no_umafall/best_model.pt",
    "ppg_quality_expert": "outputs/hybrid_redesign/ppg_quality_expert/best_model.pt",
    "activity_expert": (
        "outputs/hybrid_redesign/activity_expert_v2_uci_only/best_model.pt"
    ),
    "gait_instability_model": (
        "outputs/hybrid_redesign/gait_instability_v2_ablation/"
        "pw2.0_lr3e-04_ft0.30/best_model.pt"
    ),
}

ACCEPTED_NORM_PATHS = {
    "fall_expert": "outputs/hybrid_redesign/fall_expert_core_no_umafall/imu_norm_stats.json",
    "ppg_quality_expert": "outputs/hybrid_redesign/ppg_quality_expert/ppg_norm_stats.json",
    "activity_expert": (
        "outputs/hybrid_redesign/activity_expert_v2_uci_only/imu_norm_stats.json"
    ),
    "gait_instability_model": (
        "outputs/hybrid_redesign/gait_instability_v2_ablation/"
        "pw2.0_lr3e-04_ft0.30/imu_norm_stats.json"
    ),
}


def _cfg():
    return yaml.safe_load(Path("config/hybrid_runtime_config.yaml").read_text(encoding="utf-8"))


def test_runtime_config_points_to_final_accepted_models():
    cfg = _cfg()
    for key, path in ACCEPTED_PATHS.items():
        assert cfg[key]["enabled"] is True
        assert cfg[key]["model_path"] == path
        assert Path(path).exists(), path


def test_runtime_config_points_to_final_norm_stats():
    cfg = _cfg()
    for key, path in ACCEPTED_NORM_PATHS.items():
        assert cfg[key]["norm_stats_path"] == path
        assert Path(path).exists(), path


def test_runtime_config_disables_rejected_models():
    cfg = _cfg()
    assert cfg["vitals_context_model"]["enabled"] is False
    assert cfg["tremor_context"]["enabled"] is False
    for name, block in cfg["rejected_models"].items():
        assert block["enabled"] is False, name
