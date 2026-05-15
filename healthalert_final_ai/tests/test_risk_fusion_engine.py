from src.healthalert.fusion.risk_fusion_engine import RiskFusionEngine


def test_risk_score_clipped_and_level_valid():
    e = RiskFusionEngine()
    out = e.fuse(
        fall_probability=1.0,
        activity_context="lying",
        ppg_quality_score=0.9,
        ppg_quality_label="good_quality",
        runtime_vitals_adjustment=20.0,
        runtime_gait_motion_score=1.0,
        personalization_adjustment=50.0,
        signal_confidence=1.0,
        missing_modality_flags={"post_impact_low_motion": True},
    )
    assert 0.0 <= out["final_risk_score"] <= 100.0
    assert out["risk_level"] in {"normal", "caution", "high_risk", "critical"}
    assert len(out["reasons"]) > 0


def test_ppg_missing_disables_vitals():
    e = RiskFusionEngine()
    out = e.fuse(
        fall_probability=0.5,
        activity_context="walking",
        ppg_quality_score=None,
        ppg_quality_label=None,
        runtime_vitals_adjustment=9.0,
        runtime_gait_motion_score=0.2,
        personalization_adjustment=0.0,
        signal_confidence=0.8,
        missing_modality_flags={"ppg_missing": True},
    )
    assert out["vitals_contribution"] == 0.0
    assert "ppg_missing" in out["reasons"]
