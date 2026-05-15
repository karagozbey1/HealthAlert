from src.healthalert.fusion.temporal_risk_smoother import TemporalRiskSmoother


def test_temporal_smoother_applies_and_keeps_bounds():
    s = TemporalRiskSmoother()
    out = s.update({"final_risk_score": 80.0, "risk_level": "critical", "reasons": ["x"]})
    assert out["temporal_smoothing_applied"] is True
    assert 0.0 <= out["final_risk_score"] <= 100.0


def test_user_confirmed_okay_resets_to_normal():
    s = TemporalRiskSmoother()
    out = s.update(
        {"final_risk_score": 60.0, "risk_level": "high_risk", "reasons": ["x"]},
        user_confirmed_okay=True,
    )
    assert out["risk_level"] == "normal"
