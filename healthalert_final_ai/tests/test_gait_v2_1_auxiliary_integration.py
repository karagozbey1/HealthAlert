from src.healthalert.fusion.risk_fusion_engine import RiskFusionEngine


def _fuse(fall_probability: float, gait_score: float):
    return RiskFusionEngine(gait_max_contribution_points=5).fuse(
        fall_probability=fall_probability,
        activity_context="walking",
        ppg_quality_score=None,
        ppg_quality_label="missing",
        runtime_vitals_adjustment=0.0,
        runtime_gait_motion_score=gait_score,
        personalization_adjustment=0.0,
        signal_confidence=1.0,
        missing_modality_flags={"ppg_missing": True, "baseline_missing": True},
    )


def test_gait_high_fall_low_does_not_create_critical():
    out = _fuse(fall_probability=0.05, gait_score=1.0)
    assert out["risk_level"] != "critical"
    assert out["gait_contribution"] <= 2.0


def test_gait_high_fall_medium_raises_risk_but_is_capped():
    no_gait = _fuse(fall_probability=0.50, gait_score=0.0)
    high_gait = _fuse(fall_probability=0.50, gait_score=1.0)
    assert high_gait["final_risk_score"] > no_gait["final_risk_score"]
    assert high_gait["gait_contribution"] <= 5.0


def test_gait_model_never_has_standalone_critical_authority():
    out = _fuse(fall_probability=0.0, gait_score=1.0)
    assert out["risk_level"] in {"normal", "caution"}
    assert out["gait_contribution"] <= 2.0
