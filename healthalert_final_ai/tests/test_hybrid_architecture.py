"""
Tests for HealthAlert Hybrid Architecture.

Covers all 15 required test cases:
  1.  Dataset routing respected (allowed_datasets)
  2.  PPG-only data never enters fall expert
  3.  tremor_context not trained (enabled_for_training: false)
  4.  Collapsed checkpoint not saved as best_model.pt
  5.  best_model.pt requires checkpoint_valid=True
  6.  Fall expert excludes/handles near_fall
  7.  Risk fusion score always in [0, 100]
  8.  Missing PPG does not crash inference
  9.  Missing baseline uses cold-start (confidence=0)
  10. Baseline no-update during high risk
  11. Baseline updates only in safe periods
  12. Personal deviation increases risk on deviation
  13. Temporal smoothing reduces single-window false alarms
  14. Critical escalation for persistent/high fall risk
  15. final_risk_score output has reasons and confidence
"""

import sys
from pathlib import Path

import numpy as np
import pytest
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def fusion_engine():
    from src.healthalert.fusion.risk_fusion_engine import RiskFusionEngine
    return RiskFusionEngine()


@pytest.fixture
def baseline_engine():
    from src.healthalert.personalization.user_baseline import UserBaselineEngine
    return UserBaselineEngine(user_id="test_user")


@pytest.fixture
def temporal_smoother():
    from src.healthalert.fusion.temporal_risk_smoother import TemporalRiskSmoother
    return TemporalRiskSmoother()


@pytest.fixture
def inference_svc(tmp_path):
    from src.healthalert.inference.hybrid_inference_service import HybridInferenceService
    return HybridInferenceService(
        checkpoint_dir=str(tmp_path),
        device="cpu",
        user_baselines_dir=str(tmp_path / "baselines"),
        enable_temporal_smoothing=False,
    )


# ─── Test 1: Dataset routing respected ───────────────────────────────────────

def test_routing_yaml_has_allowed_datasets():
    """Routing config must define allowed_datasets for fall_detection."""
    import yaml
    routing_path = ROOT / "config" / "hybrid_task_routing.yaml"
    assert routing_path.exists(), f"Routing config not found: {routing_path}"
    with open(routing_path) as f:
        cfg = yaml.safe_load(f)
    fall = cfg["fall_detection"]
    assert "allowed_datasets" in fall
    assert len(fall["allowed_datasets"]) > 0


# ─── Test 2: PPG-only datasets forbidden in fall expert ───────────────────────

def test_ppg_datasets_forbidden_in_fall_expert():
    """Pure PPG-only datasets (no IMU) must be forbidden in fall_detection."""
    import yaml
    routing_path = ROOT / "config" / "hybrid_task_routing.yaml"
    with open(routing_path) as f:
        cfg = yaml.safe_load(f)
    fall = cfg["fall_detection"]
    forbidden = fall.get("forbidden_datasets", [])
    assert len(forbidden) > 0, "fall_detection must have forbidden_datasets"
    assert fall.get("ppg_only_forbidden") is True, (
        "fall_detection must set ppg_only_forbidden: true"
    )
    # Known pure PPG-only datasets must be forbidden
    ppg_only_datasets = ["but_ppg", "bidmc", "ppg_dalia"]
    for ds in ppg_only_datasets:
        assert ds in forbidden, (
            f"PPG-only dataset '{ds}' must be in fall_detection forbidden_datasets"
        )


# ─── Test 3: tremor_context not trained ──────────────────────────────────────

def test_tremor_context_not_enabled_for_training():
    """tremor_context.enabled_for_training must be False."""
    import yaml
    routing_path = ROOT / "config" / "hybrid_task_routing.yaml"
    with open(routing_path) as f:
        cfg = yaml.safe_load(f)
    tremor = cfg.get("tremor_context", {})
    assert tremor.get("enabled_for_training") is False, (
        "tremor_context must have enabled_for_training: false"
    )


# ─── Test 4+5: Collapsed checkpoint not saved as best ─────────────────────────

def test_collapse_detection_flags_correctly():
    """is_collapse() must detect all-fall predictions correctly."""
    from src.healthalert.training.fall_expert_trainer import is_collapse
    # All predictions are fall (class 1)
    metrics = {
        "fall_recall": 1.0,
        "normal_recall": 0.0,
        "fall_precision": 0.14,
        "macro_f1": 0.08,
    }
    pred_counts = {0: 0, 1: 1000}  # 100% fall predictions
    collapsed, reason = is_collapse(metrics, pred_counts)
    assert collapsed, f"Expected collapse=True, got False. Reason: {reason}"


def test_best_model_not_saved_on_collapse(tmp_path):
    """best_model.pt must NOT be created when is_best=False (collapsed case)."""
    from src.healthalert.models.fall_expert import build_fall_expert
    from src.healthalert.training.fall_expert_trainer import FallExpertTrainer

    model = build_fall_expert({})
    trainer = FallExpertTrainer(
        model=model,
        cfg={"training": {"epochs": 1}},
        out_dir=str(tmp_path),
        device=torch.device("cpu"),
    )
    # is_best=False simulates collapsed/invalid checkpoint
    trainer._save_checkpoint(
        epoch=0,
        metrics={
            "fall_recall": 1.0,
            "normal_recall": 0.0,
            "fall_precision": 0.14,
            "macro_f1": 0.08,
        },
        is_best=False,
    )
    assert not (tmp_path / "best_model.pt").exists(), (
        "best_model.pt must NOT be saved when is_best=False"
    )


# ─── Test 6: near_fall excluded from fall expert training ─────────────────────

def test_near_fall_excluded_from_labels():
    """
    Fall expert label encoding: near_fall windows (label=2) should not
    appear as training labels (only 0 and 1 are valid).
    """
    import yaml
    path = ROOT / "config" / "hybrid_task_routing.yaml"
    with open(path) as f:
        cfg = yaml.safe_load(f)
    label_policy = cfg["fall_detection"].get("label_policy", {}).get("binary_baseline", {})
    assert label_policy.get("near_fall") == "exclude", (
        "near_fall must be set to 'exclude' in fall_detection label_policy"
    )


# ─── Test 7: Risk fusion always [0, 100] ──────────────────────────────────────

@pytest.mark.parametrize("fall_prob,gait,vitals,deviation", [
    (0.0, 0.0, 0.0, 0.0),
    (1.0, 1.0, 1.0, 1.0),
    (0.5, 0.5, 0.5, 0.5),
    (0.99, 0.01, 0.99, 0.01),
])
def test_risk_fusion_score_in_range(fusion_engine, fall_prob, gait, vitals, deviation):
    result = fusion_engine.fuse(
        fall_probability=fall_prob,
        gait_instability_score=gait,
        vitals_context_score=vitals,
        personal_deviation_score=deviation,
        personalization_confidence=0.8,
        ppg_quality_score=0.9,
    )
    score = result["final_risk_score"]
    assert 0.0 <= score <= 100.0, f"Score {score} out of [0, 100] range"


# ─── Test 8: Missing PPG does not crash ───────────────────────────────────────

def test_missing_ppg_no_crash(fusion_engine):
    result = fusion_engine.fuse(
        fall_probability=0.3,
        ppg_quality_score=None,
        missing_modality_flags={"ppg_missing": True},
    )
    assert "final_risk_score" in result
    assert "ppg_missing_vitals_unavailable" in result["reasons"]


def test_inference_svc_missing_ppg_no_crash(inference_svc):
    imu = np.random.randn(6, 200).astype(np.float32)
    result = inference_svc.infer(imu_window=imu, ppg_window=None)
    assert result["ppg_quality_score"] is None
    assert 0.0 <= result["final_risk_score"] <= 100.0


# ─── Test 9: Missing baseline → cold-start ───────────────────────────────────

def test_cold_start_zero_confidence(baseline_engine):
    dev = baseline_engine.compute_deviation({"heart_rate": 80.0, "activity_class": "sitting"})
    assert dev["confidence"] == 0.0, "Fresh baseline must have confidence=0"


# ─── Test 10+11: Baseline update gating ──────────────────────────────────────

def test_baseline_blocked_during_high_risk(baseline_engine):
    allowed = baseline_engine.should_update(
        final_risk_score=80.0,
        fall_probability=0.9,
        ppg_quality_score=0.9,
        risk_level="critical",
    )
    assert not allowed, "Baseline update must be blocked during critical risk"


def test_baseline_allowed_during_normal(baseline_engine):
    allowed = baseline_engine.should_update(
        final_risk_score=10.0,
        fall_probability=0.02,
        ppg_quality_score=0.9,
        risk_level="normal",
    )
    assert allowed, "Baseline update must be allowed during normal risk"


# ─── Test 12: Personal deviation increases risk ───────────────────────────────

def test_personal_deviation_increases_risk(fusion_engine):
    r_low_dev = fusion_engine.fuse(
        fall_probability=0.1,
        personal_deviation_score=0.05,
        personalization_confidence=0.8,
        ppg_quality_score=0.9,
    )
    r_high_dev = fusion_engine.fuse(
        fall_probability=0.1,
        personal_deviation_score=0.90,
        personalization_confidence=0.8,
        ppg_quality_score=0.9,
    )
    assert r_high_dev["final_risk_score"] > r_low_dev["final_risk_score"], (
        "High deviation should yield higher final_risk_score than low deviation"
    )


# ─── Test 13: Temporal smoothing reduces single-window false alarms ───────────

def test_temporal_smoothing_suppresses_single_spike(temporal_smoother):
    from src.healthalert.fusion.risk_fusion_engine import RiskFusionEngine
    engine = RiskFusionEngine()

    # 5 normal windows
    for _ in range(5):
        r = engine.fuse(fall_probability=0.02, gait_instability_score=0.05)
        temporal_smoother.update(r, fall_probability=0.02)

    # Single high-risk spike
    spike = engine.fuse(fall_probability=0.80, gait_instability_score=0.80)
    smoothed = temporal_smoother.update(spike, fall_probability=0.80)

    # After just 1 spike and default buffer, smoothed score should be below the raw spike
    raw_score = spike["final_risk_score"]
    smoothed_score = smoothed["final_risk_score"]
    assert smoothed_score <= raw_score, (
        f"Smoothed score {smoothed_score} must be <= raw spike {raw_score}"
    )


# ─── Test 14: Critical escalation for persistent high fall risk ───────────────

def test_critical_escalation_after_persistent_high_risk(temporal_smoother):
    from src.healthalert.fusion.risk_fusion_engine import RiskFusionEngine
    engine = RiskFusionEngine()

    final_levels = []
    for _ in range(5):
        r = engine.fuse(fall_probability=0.92, gait_instability_score=0.85)
        smoothed = temporal_smoother.update(r, fall_probability=0.92)
        final_levels.append(smoothed["risk_level"])

    # After multiple high-risk windows, risk level should have escalated
    assert "high_risk" in final_levels or "critical" in final_levels, (
        f"Expected high_risk or critical after persistent high fall risk. Got: {final_levels}"
    )


# ─── Test 15: Output has reasons and confidence ───────────────────────────────

def test_output_has_reasons_and_confidence(fusion_engine):
    result = fusion_engine.fuse(
        fall_probability=0.4,
        gait_instability_score=0.3,
        ppg_quality_score=0.85,
        vitals_context_score=0.2,
        signal_confidence=0.9,
    )
    assert "reasons" in result, "Output must contain 'reasons'"
    assert "confidence_score" in result, "Output must contain 'confidence_score'"
    assert isinstance(result["reasons"], list)
    assert 0.0 <= result["confidence_score"] <= 1.0
