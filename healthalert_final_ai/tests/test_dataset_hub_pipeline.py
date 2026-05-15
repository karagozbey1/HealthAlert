"""Tests for the Dataset Hub & Multi-Source Windowed Training Pipeline.

Covers:
- datasets.yaml parsing
- missing dataset controlled return
- StandardRecord schema validation
- 50Hz 4s → 200 samples
- 25Hz 4s → resample to 200 samples
- 1Hz → fast model rejected / slow_context marked
- label taxonomy unknown label handling
- task mask correctness
- subject-aware split (no subject in both train and test)
- quality report generation
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# 1. datasets.yaml parse
# ─────────────────────────────────────────────────────────────────────────────

def test_datasets_yaml_parseable():
    yaml_path = PROJECT_ROOT / "config" / "datasets.yaml"
    assert yaml_path.exists(), "datasets.yaml must exist"
    with yaml_path.open() as f:
        content = yaml.safe_load(f)
    assert "datasets" in content, "datasets.yaml must have 'datasets' key"
    datasets = content["datasets"]
    assert len(datasets) >= 10, f"Expected >= 10 datasets, got {len(datasets)}"


def test_datasets_yaml_required_fields():
    yaml_path = PROJECT_ROOT / "config" / "datasets.yaml"
    with yaml_path.open() as f:
        content = yaml.safe_load(f)
    for key, val in content["datasets"].items():
        assert val is not None, f"Dataset {key} entry is None"
        assert "local_path" in val, f"Dataset {key} missing 'local_path'"
        assert "sampling_rate_hz" in val, f"Dataset {key} missing 'sampling_rate_hz'"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Label taxonomy
# ─────────────────────────────────────────────────────────────────────────────

def test_label_taxonomy_parseable():
    taxonomy_path = PROJECT_ROOT / "config" / "label_taxonomy.yaml"
    assert taxonomy_path.exists(), "label_taxonomy.yaml must exist"
    with taxonomy_path.open() as f:
        content = yaml.safe_load(f)
    assert "canonical_labels" in content
    labels = content["canonical_labels"]
    for required in ("fall", "normal", "near_fall", "unknown"):
        assert required in labels, f"Canonical label '{required}' missing from taxonomy"


def test_label_taxonomy_unknown_label_has_id_99():
    taxonomy_path = PROJECT_ROOT / "config" / "label_taxonomy.yaml"
    with taxonomy_path.open() as f:
        content = yaml.safe_load(f)
    assert content["canonical_labels"]["unknown"]["id"] == 99


# ─────────────────────────────────────────────────────────────────────────────
# 3. StandardRecord schema
# ─────────────────────────────────────────────────────────────────────────────

def test_standard_record_creation():
    from src.data.standard_schema import StandardRecord
    rec = StandardRecord(
        dataset_name="test_dataset",
        subject_id="s01",
        recording_id="r001",
        sampling_rate_hz=50.0,
        imu_samples=np.random.randn(200, 6).astype(np.float32),
    )
    assert rec.dataset_name == "test_dataset"
    assert rec.n_samples == 200
    assert rec.duration_sec == pytest.approx(4.0)
    assert rec.modality_mask["has_imu"] is True
    assert rec.modality_mask["has_ppg"] is False


def test_standard_record_modality_mask():
    from src.data.standard_schema import StandardRecord
    rec = StandardRecord(
        dataset_name="ppg_ds",
        subject_id="s02",
        recording_id="r002",
        sampling_rate_hz=30.0,
        ppg_samples=np.random.randn(120, 1).astype(np.float32),
    )
    assert rec.modality_mask["has_ppg"] is True
    assert rec.modality_mask["has_imu"] is False


def test_dataset_load_result_missing():
    from src.data.standard_schema import DatasetLoadResult
    result = DatasetLoadResult.missing("TestDS", "/nonexistent/path")
    assert result.status == "missing"
    assert result.n_records == 0
    assert len(result.errors) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Windowing – 50Hz 4s = 200 samples
# ─────────────────────────────────────────────────────────────────────────────

def test_windowing_50hz_4sec_equals_200_samples():
    from src.data.windowing import segment_timeseries_to_windows
    data = np.random.randn(400, 6).astype(np.float32)
    windows = segment_timeseries_to_windows(data, sampling_rate_hz=50, window_sec=4, stride_sec=2)
    assert windows, "Expected at least one window"
    assert windows[0]["sample_count"] == 200


def test_windowing_50hz_fast_model_candidate():
    from src.data.windowing import segment_timeseries_to_windows
    data = np.random.randn(400, 6).astype(np.float32)
    windows = segment_timeseries_to_windows(data, sampling_rate_hz=50, window_sec=4, stride_sec=2)
    assert windows[0]["fast_model_candidate"] is True
    assert windows[0]["slow_model_only"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 5. Windowing – 25Hz resample to 200 samples
# ─────────────────────────────────────────────────────────────────────────────

def test_windowing_25hz_normalizes_to_200_samples():
    from src.data.windowing import normalize_window_shape, segment_timeseries_to_windows
    data = np.random.randn(200, 6).astype(np.float32)
    windows = segment_timeseries_to_windows(data, sampling_rate_hz=25, window_sec=4, stride_sec=2)
    assert windows, "Expected at least one window at 25Hz"
    assert windows[0]["sample_count"] == 100  # 25Hz * 4sec = 100 raw samples
    normalized = normalize_window_shape(windows[0], target_rate_hz=50, target_sample_count=200)
    assert normalized["samples"].shape == (200, 6), \
        f"Expected (200, 6), got {normalized['samples'].shape}"
    assert normalized["resampled"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 6. Windowing – 1Hz → slow model only / rejected for fast model
# ─────────────────────────────────────────────────────────────────────────────

def test_windowing_1hz_marks_slow_model_only():
    from src.data.windowing import compute_window_quality, normalize_window_shape, segment_timeseries_to_windows
    data = np.random.randn(8, 1).astype(np.float32)
    windows = segment_timeseries_to_windows(data, sampling_rate_hz=1, window_sec=4, stride_sec=2)
    assert windows, "Expected at least one window at 1Hz"
    assert windows[0]["fast_model_candidate"] is False
    assert windows[0]["slow_model_only"] is True

    normalized = normalize_window_shape(windows[0], target_rate_hz=50, target_sample_count=200)
    assert normalized["training_candidate"] is False
    assert normalized["slow_model_only"] is True

    quality = compute_window_quality(normalized)
    assert "slow_model_only" in quality["quality_flags"]


# ─────────────────────────────────────────────────────────────────────────────
# 7. Task mask
# ─────────────────────────────────────────────────────────────────────────────

def test_task_mask_fall_dataset():
    from src.data.standard_schema import StandardRecord
    from src.data.windowing import build_standard_windows

    imu = np.random.randn(200, 6).astype(np.float32)
    labels = np.array(["fall"] * 200)
    rec = StandardRecord(
        dataset_name="test_fall",
        subject_id="s01",
        recording_id="r1",
        sampling_rate_hz=50.0,
        imu_samples=imu,
        labels=labels,
        valid_tasks=["fall_detection", "adl_detection"],
    )
    cfg = {"tasks": ["fall_detection", "adl_detection"], "sampling_rate_hz": 50}
    windows = build_standard_windows(rec, config=cfg)
    assert windows, "Expected windows from 200-sample imu record at 50Hz"
    w = windows[0]
    assert w["label_mask"]["fall_detection"] == "fall"
    assert w["label_mask"]["ppg_quality"] == "unknown"  # not in valid_tasks


def test_task_mask_ppg_dataset_no_fall_label():
    from src.data.standard_schema import StandardRecord
    from src.data.windowing import build_standard_windows

    ppg = np.random.randn(200, 1).astype(np.float32)
    rec = StandardRecord(
        dataset_name="test_ppg",
        subject_id="s01",
        recording_id="r2",
        sampling_rate_hz=50.0,
        ppg_samples=ppg,
        valid_tasks=["ppg_quality"],
    )
    cfg = {"tasks": ["ppg_quality"], "sampling_rate_hz": 50}
    windows = build_standard_windows(rec, config=cfg)
    assert windows
    w = windows[0]
    # PPG dataset must NOT invent fall labels
    assert w["label_mask"]["fall_detection"] == "unknown"
    assert w["has_imu"] is False
    assert w["has_ppg"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 8. Subject-aware split – no leakage
# ─────────────────────────────────────────────────────────────────────────────

def test_subject_aware_split_no_leakage():
    from src.data.splitting import subject_aware_split

    # Create 10 subjects, 20 windows each
    windows = []
    for subj_i in range(10):
        for win_j in range(20):
            windows.append({
                "window_id": f"w_{subj_i}_{win_j}",
                "subject_id": f"s{subj_i:02d}",
                "recording_id": f"r{subj_i}",
                "label": "fall" if win_j % 5 == 0 else "normal",
            })

    train, val, test = subject_aware_split(windows)

    assert len(train) + len(val) + len(test) == len(windows)

    train_subjects = {w["subject_id"] for w in train}
    val_subjects = {w["subject_id"] for w in val}
    test_subjects = {w["subject_id"] for w in test}

    assert train_subjects.isdisjoint(test_subjects), \
        f"Data leakage! Subjects in both train and test: {train_subjects & test_subjects}"
    assert train_subjects.isdisjoint(val_subjects), \
        f"Data leakage! Subjects in both train and val: {train_subjects & val_subjects}"


def test_subject_aware_split_ratios():
    from src.data.splitting import subject_aware_split

    windows = [{"subject_id": f"s{i:02d}", "recording_id": f"r{i}", "label": "normal"}
               for i in range(100) for _ in range(5)]

    train, val, test = subject_aware_split(windows, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15)
    total = len(train) + len(val) + len(test)
    assert total == len(windows)
    assert len(train) > len(val)
    assert len(train) > len(test)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Missing dataset → controlled return
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_dataset_controlled_return():
    from src.data.loader_registry import load_dataset_by_name

    result = load_dataset_by_name({
        "name": "SisFall",
        "local_path": "/nonexistent/path/sisfall",
        "sampling_rate_hz": 200,
        "tasks": ["fall_detection"],
    })
    assert result.status == "missing"
    assert result.n_records == 0


def test_missing_ppg_dataset_controlled_return():
    from src.data.loader_registry import load_dataset_by_name

    result = load_dataset_by_name({
        "name": "WESAD",
        "local_path": "/nonexistent/wesad",
        "sampling_rate_hz": 700,
        "tasks": ["physiology_context"],
    })
    assert result.status == "missing"
    assert result.n_records == 0


# ─────────────────────────────────────────────────────────────────────────────
# 10. Quality report generation
# ─────────────────────────────────────────────────────────────────────────────

def test_quality_report_from_windows():
    from src.data.windowing import compute_window_quality, segment_timeseries_to_windows

    data = np.random.randn(400, 6).astype(np.float32)
    # Inject NaNs to lower quality
    data[50:100, :] = np.nan
    windows = segment_timeseries_to_windows(data, sampling_rate_hz=50, window_sec=4, stride_sec=2)

    quality_reports = [compute_window_quality(w) for w in windows]
    assert len(quality_reports) > 0

    scores = [r["quality_score"] for r in quality_reports]
    # At least some windows should have reduced quality due to NaNs
    assert min(scores) < 1.0, "Expected at least one window with quality < 1.0 due to NaNs"

    # nan_heavy flag should appear in at least one window
    all_flags = [flag for r in quality_reports for flag in r["quality_flags"]]
    assert "nan_heavy" in all_flags, "Expected 'nan_heavy' flag in quality reports"


def test_all_quality_scores_between_0_and_1():
    from src.data.windowing import compute_window_quality, segment_timeseries_to_windows

    data = np.random.randn(600, 6).astype(np.float32)
    windows = segment_timeseries_to_windows(data, sampling_rate_hz=50, window_sec=4, stride_sec=2)
    for w in windows:
        q = compute_window_quality(w)
        assert 0.0 <= q["quality_score"] <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 11. loader_registry dispatch
# ─────────────────────────────────────────────────────────────────────────────

def test_loader_registry_unknown_dataset():
    from src.data.loader_registry import load_dataset_by_name

    result = load_dataset_by_name({
        "name": "TOTALLY_UNKNOWN_DATASET_XYZ",
        "local_path": "/does/not/exist",
        "sampling_rate_hz": 50,
        "tasks": [],
    })
    assert result.status == "error"
    assert "No loader registered" in result.errors[0]


# ─────────────────────────────────────────────────────────────────────────────
# 12. build_standard_windows modality mask
# ─────────────────────────────────────────────────────────────────────────────

def test_build_standard_windows_imu_modality_flags():
    from src.data.standard_schema import StandardRecord
    from src.data.windowing import build_standard_windows

    imu = np.ones((400, 6), dtype=np.float32)
    rec = StandardRecord(
        dataset_name="ds",
        subject_id="s1",
        recording_id="r1",
        sampling_rate_hz=50.0,
        imu_samples=imu,
        valid_tasks=["fall_detection"],
    )
    windows = build_standard_windows(rec, window_sec=4, stride_sec=2, target_rate_hz=50)
    assert windows
    for w in windows:
        assert w["has_imu"] is True
        assert w["has_ppg"] is False
        assert w["target_rate_hz"] == 50.0


def test_build_standard_windows_correct_sample_count():
    from src.data.standard_schema import StandardRecord
    from src.data.windowing import build_standard_windows

    imu = np.random.randn(400, 6).astype(np.float32)
    rec = StandardRecord(
        dataset_name="ds",
        subject_id="s1",
        recording_id="r1",
        sampling_rate_hz=50.0,
        imu_samples=imu,
        valid_tasks=["fall_detection"],
    )
    windows = build_standard_windows(rec, window_sec=4, stride_sec=2, target_rate_hz=50, target_sample_count=200)
    assert windows
    for w in windows:
        assert w["imu"] is not None
        assert w["imu"].shape[0] == 200, f"Expected 200 samples, got {w['imu'].shape[0]}"
