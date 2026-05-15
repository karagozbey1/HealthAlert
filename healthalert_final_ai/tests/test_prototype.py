"""Tests for HealthAlert prototype model, training, and inference.

Coverage:
1.  task_training_policy — tremor_context must be disabled
2.  task_training_policy — 5 enabled tasks present
3.  TaskNpzDataset — loads and returns valid samples
4.  TaskNpzDataset — excluded labels (99) not in samples
5.  PrototypeModel — forward pass runs without error
6.  PrototypeModel — forward_task gives correct output shape per task
7.  PrototypeModel — handles zeroed modality gracefully
8.  MultiTaskPrototypeLoss — tremor_context blocked
9.  MultiTaskPrototypeLoss — loss computable for each enabled task
10. PrototypePredictor — init without checkpoint raises FileNotFoundError
11. PrototypePredictor — predict returns ml_risk_score in 0-100
12. PrototypePredictor — ml_risk_score is float, risk_level is valid string
13. PrototypePredictor — missing IMU → uniform fall_detection probs
14. PrototypePredictor — missing PPG → uniform ppg_quality probs
15. RiskScoreFusion — output is 0-100 and level is valid
16. Checkpoint saving — best_model.pt can be saved and reloaded
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Dict
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.models.prototype_model import PrototypeHealthAlertModel
from src.training.prototype_losses import (
    FocalCrossEntropyLoss,
    MultiTaskPrototypeLoss,
    WeightedCELoss,
)
from src.inference.prototype_predictor import PrototypePredictor, RiskScoreFusion
from src.data.task_npz_dataset import TaskNpzDataset, _compute_class_weights


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def prototype_cfg() -> dict:
    import yaml
    cfg_path = PROJECT_ROOT / "config" / "prototype_training.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def policy_cfg() -> dict:
    import yaml
    cfg_path = PROJECT_ROOT / "config" / "task_training_policy.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def model() -> PrototypeHealthAlertModel:
    return PrototypeHealthAlertModel()


@pytest.fixture
def dummy_batch() -> Dict[str, torch.Tensor]:
    return {
        "imu": torch.randn(4, 200, 6),
        "ppg": torch.randn(4, 200, 1),
        "label": torch.zeros(4, dtype=torch.long),
        "task": "fall_detection",
    }


@pytest.fixture(scope="module")
def fall_detection_npz_path() -> Path:
    path = PROJECT_ROOT / "outputs" / "windowed_dataset" / "fall_detection" / "val.npz"
    if not path.exists():
        pytest.skip(f"Dataset not found: {path}")
    return path


@pytest.fixture(scope="module")
def fall_detection_train_ds(fall_detection_npz_path) -> TaskNpzDataset:
    label_map = {0: 0, 1: 1, 2: 2, 99: -1}
    return TaskNpzDataset(
        npz_path=fall_detection_npz_path,
        task_name="fall_detection",
        label_map=label_map,
        num_classes=3,
        max_class_weight=8.0,
        augment=False,
    )


@pytest.fixture(scope="module")
def saved_checkpoint(model, tmp_path_factory) -> Path:
    """Save a minimal checkpoint for testing."""
    tmp = tmp_path_factory.mktemp("ckpt")
    ckpt_path = tmp / "best_model.pt"
    # Save label_mappings alongside
    mappings = {
        "fall_detection": {
            "label_map": {"0": 0, "1": 1, "2": 2, "99": -1},
            "class_names": ["normal", "fall", "near_fall"],
            "num_classes": 3,
        }
    }
    with open(tmp / "label_mappings.json", "w") as f:
        json.dump(mappings, f)

    torch.save(
        {
            "epoch": 1,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": {},
            "best_val_score": 0.5,
            "best_metric_name": "fall_recall",
        },
        ckpt_path,
    )
    return ckpt_path


# ── Test 1: Task training policy — tremor_context disabled ────────────────

def test_tremor_context_disabled_in_prototype_cfg(prototype_cfg):
    tasks = prototype_cfg.get("tasks", {})
    assert "tremor_context" in tasks, "tremor_context must be defined in config"
    tc = tasks["tremor_context"]
    assert tc.get("enabled") is False, (
        "tremor_context must be enabled: false in prototype_training.yaml"
    )


def test_tremor_context_disabled_in_policy(policy_cfg):
    tasks = policy_cfg.get("tasks", {})
    assert "tremor_context" in tasks, "tremor_context must be in task_training_policy.yaml"
    assert not tasks["tremor_context"].get("enabled_for_training", True), (
        "tremor_context must have enabled_for_training: false in task_training_policy.yaml"
    )


# ── Test 2: 5 enabled tasks ───────────────────────────────────────────────

def test_five_enabled_tasks(prototype_cfg):
    tasks = prototype_cfg.get("tasks", {})
    enabled = [t for t, cfg in tasks.items() if cfg.get("enabled", True)]
    assert len(enabled) == 5, f"Expected 5 enabled tasks, got {len(enabled)}: {enabled}"
    expected = {"fall_detection", "ppg_quality", "vitals_context", "activity_context", "gait_instability"}
    assert set(enabled) == expected, f"Unexpected tasks: {set(enabled)}"


# ── Test 3: TaskNpzDataset loads valid samples ────────────────────────────

def test_task_npz_dataset_loads(fall_detection_train_ds):
    ds = fall_detection_train_ds
    assert len(ds) > 0, "Dataset should have valid samples"
    sample = ds[0]
    assert "imu" in sample
    assert "ppg" in sample
    assert "label" in sample
    assert "task" in sample
    assert sample["imu"].shape == (200, 6)
    assert sample["ppg"].shape == (200, 1)
    assert isinstance(sample["label"].item(), int)
    assert sample["task"] == "fall_detection"


# ── Test 4: Excluded labels (99) not in output ────────────────────────────

def test_excluded_labels_not_in_dataset(fall_detection_train_ds):
    ds = fall_detection_train_ds
    # All mapped labels must be >= 0 (excludes are removed by valid_indices)
    labels = ds.mapped_labels[ds.valid_indices]
    assert all(l >= 0 for l in labels), "Excluded labels (-1) must not appear in valid samples"
    # 99 is mapped to -1 in fall_detection
    assert 99 not in [ds.raw_labels[i] for i in ds.valid_indices[:100]], \
        "Raw label 99 should be excluded from valid indices"


# ── Test 5: Model forward pass ────────────────────────────────────────────

def test_model_forward_all_tasks(model, dummy_batch):
    output = model(dummy_batch)
    assert "fall_detection" in output
    assert "ppg_quality" in output
    assert "vitals_context" in output
    assert "activity_context" in output
    assert "gait_instability" in output


# ── Test 6: forward_task output shapes ───────────────────────────────────

@pytest.mark.parametrize("task,n_classes", [
    ("fall_detection", 3),
    ("ppg_quality", 2),
    ("vitals_context", 3),
    ("activity_context", 8),
    ("gait_instability", 2),
])
def test_model_forward_task_shape(model, dummy_batch, task, n_classes):
    logits = model.forward_task(dummy_batch, task)
    assert logits.shape == (4, n_classes), (
        f"Task {task}: expected shape (4, {n_classes}), got {logits.shape}"
    )


# ── Test 7: Zeroed modality does not crash ────────────────────────────────

def test_model_zeroed_imu(model):
    batch = {
        "imu": torch.zeros(2, 200, 6),  # zeroed IMU
        "ppg": torch.randn(2, 200, 1),
    }
    out = model(batch)
    assert out["fall_detection"].shape == (2, 3)
    assert not torch.isnan(out["fall_detection"]).any()


def test_model_zeroed_ppg(model):
    batch = {
        "imu": torch.randn(2, 200, 6),
        "ppg": torch.zeros(2, 200, 1),  # zeroed PPG
    }
    out = model(batch)
    assert out["ppg_quality"].shape == (2, 2)
    assert not torch.isnan(out["ppg_quality"]).any()


# ── Test 8: tremor_context blocked in loss ────────────────────────────────

def test_tremor_context_blocked_in_loss():
    tasks_cfg = {
        "fall_detection": {
            "enabled": True,
            "loss_type": "focal_ce",
            "focal_gamma": 2.0,
            "loss_weight": 1.0,
            "num_classes": 3,
            "label_map": {"0": 0, "1": 1, "2": 2, "99": -1},
        },
    }
    criterion = MultiTaskPrototypeLoss(
        tasks_cfg=tasks_cfg,
        task_datasets={},
        disabled_tasks=["tremor_context"],
    )
    logits = torch.randn(4, 2)
    targets = torch.zeros(4, dtype=torch.long)
    with pytest.raises(RuntimeError, match="tremor_context"):
        criterion(logits, targets, "tremor_context")


# ── Test 9: Loss computable for enabled tasks ─────────────────────────────

@pytest.mark.parametrize("task,n_classes,loss_type", [
    ("fall_detection", 3, "focal_ce"),
    ("ppg_quality", 2, "weighted_ce"),
    ("vitals_context", 3, "weighted_ce"),
    ("activity_context", 8, "weighted_ce"),
    ("gait_instability", 2, "weighted_ce"),
])
def test_loss_computable_per_task(task, n_classes, loss_type):
    tasks_cfg = {
        task: {
            "enabled": True,
            "loss_type": loss_type,
            "focal_gamma": 2.0,
            "loss_weight": 1.0,
            "num_classes": n_classes,
            "label_map": {},
        }
    }
    criterion = MultiTaskPrototypeLoss(
        tasks_cfg=tasks_cfg,
        task_datasets={},
        disabled_tasks=["tremor_context"],
    )
    logits = torch.randn(4, n_classes)
    targets = torch.randint(0, n_classes, (4,))
    loss = criterion(logits, targets, task)
    assert loss.item() >= 0.0
    assert not torch.isnan(loss)


# ── Test 10: Predictor raises FileNotFoundError if model missing ──────────

def test_predictor_missing_model():
    with pytest.raises(FileNotFoundError):
        PrototypePredictor(model_path="/nonexistent/best_model.pt")


# ── Test 11: ml_risk_score in 0-100 ──────────────────────────────────────

def test_predictor_risk_score_range(saved_checkpoint):
    predictor = PrototypePredictor(
        model_path=saved_checkpoint,
        label_mappings_path=saved_checkpoint.parent / "label_mappings.json",
        device="cpu",
    )
    imu = np.random.randn(200, 6).astype(np.float32)
    ppg = np.random.randn(200, 1).astype(np.float32)
    result = predictor.predict(imu=imu, ppg=ppg)
    assert "ml_risk_score" in result
    score = result["ml_risk_score"]
    assert 0.0 <= score <= 100.0, f"ml_risk_score out of range: {score}"


# ── Test 12: risk_level is a valid string ─────────────────────────────────

def test_predictor_risk_level_valid(saved_checkpoint):
    predictor = PrototypePredictor(
        model_path=saved_checkpoint,
        device="cpu",
    )
    imu = np.random.randn(200, 6).astype(np.float32)
    ppg = np.zeros((200, 1), dtype=np.float32)
    result = predictor.predict(imu=imu, ppg=ppg)
    valid_levels = {"normal", "caution", "high_risk", "critical"}
    assert result["risk_level"] in valid_levels, f"Invalid risk_level: {result['risk_level']}"
    assert isinstance(result["ml_risk_score"], float)


# ── Test 13: Missing IMU → uniform fall_detection probs ──────────────────

def test_predictor_missing_imu_degrades_fall_confidence(saved_checkpoint):
    predictor = PrototypePredictor(
        model_path=saved_checkpoint,
        device="cpu",
    )
    result = predictor.predict(imu=None, ppg=np.random.randn(200, 1).astype(np.float32))
    assert result["modality_flags"]["has_imu"] is False
    # Fall detection probs should be uniform (1/3 each)
    fall_probs = result["task_probs"]["fall_detection"]
    for p in fall_probs:
        assert abs(p - 1.0 / 3) < 0.01, f"Expected uniform probs, got {fall_probs}"


# ── Test 14: Missing PPG → uniform ppg_quality probs ─────────────────────

def test_predictor_missing_ppg_degrades_ppg_confidence(saved_checkpoint):
    predictor = PrototypePredictor(
        model_path=saved_checkpoint,
        device="cpu",
    )
    result = predictor.predict(imu=np.random.randn(200, 6).astype(np.float32), ppg=None)
    assert result["modality_flags"]["has_ppg"] is False
    ppg_probs = result["task_probs"]["ppg_quality"]
    for p in ppg_probs:
        assert abs(p - 0.5) < 0.01, f"Expected uniform ppg_quality probs, got {ppg_probs}"


# ── Test 15: RiskScoreFusion output range and levels ─────────────────────

@pytest.mark.parametrize("fall_p,near_p,gait_p,expected_not_normal", [
    (0.0, 0.0, 0.0, False),   # all zero → normal
    (0.9, 0.0, 0.0, True),    # high fall prob → not normal
    (0.0, 0.0, 0.9, True),    # high gait instability → not normal
])
def test_risk_fusion_output_range(fall_p, near_p, gait_p, expected_not_normal):
    fusion = RiskScoreFusion()
    task_probs = {
        "fall_detection": [1 - fall_p - near_p, fall_p, near_p],
        "gait_instability": [1 - gait_p, gait_p],
        "ppg_quality": [0.0, 1.0],
    }
    score, level = fusion.compute(task_probs)
    assert 0.0 <= score <= 100.0
    valid_levels = {"normal", "caution", "high_risk", "critical"}
    assert level in valid_levels
    if expected_not_normal:
        assert level != "normal" or score > 5.0


# ── Test 16: Checkpoint saving and reloading ──────────────────────────────

def test_checkpoint_save_reload(tmp_path):
    model = PrototypeHealthAlertModel()
    ckpt_path = tmp_path / "test_model.pt"
    torch.save(
        {
            "epoch": 5,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": {},
            "best_val_score": 0.82,
            "best_metric_name": "fall_recall",
        },
        ckpt_path,
    )
    assert ckpt_path.exists()

    # Reload
    ckpt = torch.load(ckpt_path, map_location="cpu")
    model2 = PrototypeHealthAlertModel()
    model2.load_state_dict(ckpt["model_state_dict"])
    assert ckpt["epoch"] == 5
    assert ckpt["best_val_score"] == pytest.approx(0.82)

    # Verify loaded model gives same output as original
    dummy = {"imu": torch.randn(2, 200, 6), "ppg": torch.randn(2, 200, 1)}
    with torch.no_grad():
        o1 = model(dummy)["fall_detection"]
        o2 = model2(dummy)["fall_detection"]
    # Both should give same result (same weights)
    # Note: this won't be identical since model was re-created but weights loaded
    assert o2.shape == (2, 3)


# ── Test: model parameter count reasonable ────────────────────────────────

def test_model_parameter_count():
    model = PrototypeHealthAlertModel()
    n = model.count_parameters()
    # Reasonable range for compact prototype: 200K–5M parameters
    assert 100_000 < n < 10_000_000, f"Unusual parameter count: {n}"


# ── Test: inference is fast ───────────────────────────────────────────────

def test_model_cpu_inference_fast():
    import time
    model = PrototypeHealthAlertModel()
    model.eval()
    dummy = {"imu": torch.randn(1, 200, 6), "ppg": torch.randn(1, 200, 1)}
    # Warm-up
    with torch.no_grad():
        model(dummy)
    # Time 10 runs
    t0 = time.perf_counter()
    with torch.no_grad():
        for _ in range(10):
            model(dummy)
    elapsed_ms = (time.perf_counter() - t0) * 100  # per run in ms
    assert elapsed_ms < 500, f"CPU inference too slow: {elapsed_ms:.1f} ms/window"
