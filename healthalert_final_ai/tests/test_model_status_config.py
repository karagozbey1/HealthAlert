from pathlib import Path

import yaml


def test_runtime_config_disables_rejected_models():
    p = Path("config/hybrid_runtime_config.yaml")
    assert p.exists()
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert cfg["vitals_context_model"]["enabled"] is False
    assert cfg["gait_instability_model"]["enabled"] is True
    assert cfg["gait_instability_model"]["status"] == "accepted_auxiliary_low_weight"
    for block in cfg["rejected_models"].values():
        assert block["enabled"] is False


def test_current_model_status_file_exists():
    p = Path("outputs/hybrid_redesign/CURRENT_MODEL_STATUS.md")
    assert p.exists()
    txt = p.read_text(encoding="utf-8")
    assert "PPG Quality Expert: `ACCEPTED`" in txt
