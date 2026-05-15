from src.healthalert.fusion.runtime_vitals_rules import compute_runtime_vitals_adjustment


def test_ppg_bad_disables_vitals_adjustment():
    out = compute_runtime_vitals_adjustment(
        ppg_quality_label="bad_quality",
        ppg_quality_score=0.1,
        vitals={"hr": 120.0, "spo2": 90.0},
        baseline={"resting_hr_median": 72.0, "spo2_median": 97.0},
    )
    assert out["adjustment"] == 0.0
    assert "ppg_quality_gate_closed" in out["reasons"]


def test_good_ppg_with_abnormal_vitals_increases_adjustment():
    out = compute_runtime_vitals_adjustment(
        ppg_quality_label="good_quality",
        ppg_quality_score=0.95,
        vitals={"hr": 110.0, "spo2": 92.0},
        baseline={"resting_hr_median": 70.0, "spo2_median": 97.0},
    )
    assert out["adjustment"] > 0.0
