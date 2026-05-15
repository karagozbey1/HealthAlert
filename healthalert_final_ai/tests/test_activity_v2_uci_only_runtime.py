from pathlib import Path

import yaml

from src.healthalert.fusion.risk_fusion_engine import RiskFusionEngine


def test_activity_v2_uses_uci_only_artifact_and_policy_flags():
    cfg = yaml.safe_load(Path("config/hybrid_runtime_config.yaml").read_text(encoding="utf-8"))
    activity = cfg["activity_expert"]
    assert activity["enabled"] is True
    assert activity["status"] == "accepted_single_source_baseline"
    assert activity["classes"] == ["walking", "sitting", "standing", "lying"]
    assert activity["source_limitation"] == "UCI-HAR-only"
    assert activity["standalone_alert_allowed"] is False
    assert activity["critical_trigger_allowed"] is False
    assert "activity_expert_v2_uci_only" in activity["model_path"]
    assert "activity_expert_v2/best_model.pt" not in activity["model_path"]


def test_activity_context_alone_does_not_trigger_critical():
    out = RiskFusionEngine().fuse(
        fall_probability=0.0,
        activity_context="lying",
        ppg_quality_score=None,
        ppg_quality_label="missing",
        runtime_vitals_adjustment=0.0,
        runtime_gait_motion_score=0.0,
        personalization_adjustment=0.0,
        signal_confidence=1.0,
        missing_modality_flags={"ppg_missing": True, "baseline_missing": True},
    )
    assert out["risk_level"] != "critical"
    assert out["final_risk_score"] <= 25.0
