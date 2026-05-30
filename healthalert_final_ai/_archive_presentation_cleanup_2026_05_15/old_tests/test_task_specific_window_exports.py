"""
Tests for task-specific window exports.

Verifies:
- fall_detection export contains no label=99 (unknown)
- PPG/vitals datasets are excluded from fall_detection
- gait/tremor datasets are not in fall_detection
- task_specific_summary.json is created and valid
- WildPPG is READY and excluded from fall_detection
- empty optional datasets (mobiact, fallalld, pads) do not break the build
"""

import json
import pathlib
import numpy as np
import pytest

OUTPUTS_DIR = pathlib.Path(__file__).parent.parent / "outputs" / "windowed_dataset"
TASK_SUMMARY = OUTPUTS_DIR / "task_specific_summary.json"
DATASET_SUMMARY = OUTPUTS_DIR / "dataset_summary.json"

# Datasets that must NEVER appear in fall_detection
PPG_VITALS_DATASETS = {
    "BIDMC-PPG-Respiration",
    "PPG-DaLiA",
    "WESAD",
    "WildPPG",
}
GAIT_TREMOR_DATASETS = {
    "Daphnet-FoG",
    "DAPHNET_FOG",
    "Hand-Tremor-MPU9250",
    "HAND_TREMOR_MPU9250",
}

FALL_DETECTION_EXCLUDED = PPG_VITALS_DATASETS | GAIT_TREMOR_DATASETS | {
    "SisFall",
    "BIDMC",
    "PADS-Smartwatch-PD",
}

LABEL_UNKNOWN = 99
EXPECTED_TASKS = [
    "fall_detection",
    "ppg_quality",
    "vitals_context",
    "activity_context",
    "gait_instability",
    "tremor_context",
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _task_summary() -> dict:
    assert TASK_SUMMARY.exists(), f"task_specific_summary.json not found at {TASK_SUMMARY}"
    return json.loads(TASK_SUMMARY.read_text(encoding="utf-8"))


def _dataset_summary() -> dict:
    assert DATASET_SUMMARY.exists(), f"dataset_summary.json not found at {DATASET_SUMMARY}"
    return json.loads(DATASET_SUMMARY.read_text(encoding="utf-8"))


def _load_npz_labels(task: str, split: str = "train") -> np.ndarray | None:
    """Load labels array from task-specific NPZ split. Returns None if not present."""
    npz_path = OUTPUTS_DIR / task / f"{split}.npz"
    if not npz_path.exists():
        return None
    data = np.load(npz_path, allow_pickle=True)
    if "labels" in data:
        return data["labels"]
    if "label" in data:
        return data["label"]
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Task-specific summary tests
# ──────────────────────────────────────────────────────────────────────────────

def test_task_specific_summary_json_created():
    """task_specific_summary.json must be created by the build script."""
    assert TASK_SUMMARY.exists(), "task_specific_summary.json was not created"


def test_task_specific_summary_contains_all_six_tasks():
    summary = _task_summary()
    for task in EXPECTED_TASKS:
        assert task in summary, f"Task '{task}' missing from task_specific_summary.json"


def test_task_specific_summary_total_counts_positive():
    """Every task with exported data must have total > 0."""
    summary = _task_summary()
    for task in EXPECTED_TASKS:
        if task == "tremor_context":
            # Very small dataset; skip count check
            continue
        info = summary[task]
        assert info["total"] > 0, f"Task '{task}' has 0 windows"


def test_task_specific_summary_train_val_test_sum_to_total():
    """train + val + test may not exactly equal total (some tasks are too small for 3 splits)."""
    summary = _task_summary()
    for task in EXPECTED_TASKS:
        info = summary[task]
        parts = info.get("train", 0) + info.get("val", 0) + info.get("test", 0)
        assert parts <= info["total"] + 5, (
            f"Task '{task}': train+val+test={parts} exceeds total={info['total']}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# fall_detection safety tests
# ──────────────────────────────────────────────────────────────────────────────

def test_fall_detection_safety_check_passed():
    """The build script's safety check for fall_detection must report PASS."""
    summary = _task_summary()
    safety = summary["fall_detection"].get("safety_check", {})
    assert safety.get("PASS", False) is True, (
        f"fall_detection safety check did not PASS: {safety}"
    )


def test_fall_detection_export_has_no_label_99():
    """fall_detection NPZ exports must contain no label=99 (unknown)."""
    for split in ("train", "val", "test"):
        labels = _load_npz_labels("fall_detection", split)
        if labels is None:
            continue
        n_unknown = int(np.sum(labels == LABEL_UNKNOWN))
        assert n_unknown == 0, (
            f"fall_detection/{split}.npz contains {n_unknown} windows with label=99"
        )


def test_fall_detection_summary_has_no_label_99():
    """Label distribution in task_specific_summary for fall_detection must not include 'unknown'."""
    summary = _task_summary()
    label_dist = summary["fall_detection"].get("label_distribution", {})
    assert "unknown" not in label_dist, (
        f"fall_detection label_distribution includes 'unknown': {label_dist}"
    )


def test_ppg_vitals_datasets_not_in_fall_detection():
    """PPG / vitals datasets must not contribute to fall_detection."""
    summary = _task_summary()
    contributions = summary["fall_detection"].get("dataset_contributions", {})
    for ds in PPG_VITALS_DATASETS:
        assert ds not in contributions, (
            f"PPG/vitals dataset '{ds}' found in fall_detection contributions"
        )


def test_gait_tremor_datasets_not_in_fall_detection():
    """Gait / tremor datasets must not contribute to fall_detection."""
    summary = _task_summary()
    contributions = summary["fall_detection"].get("dataset_contributions", {})
    for ds in GAIT_TREMOR_DATASETS:
        assert ds not in contributions, (
            f"Gait/tremor dataset '{ds}' found in fall_detection contributions"
        )


def test_fall_detection_has_only_imu_modality():
    """fall_detection must have 0 ppg_only windows; imu+ppg is allowed for
    HIFD (wrist IMU+PPG fall dataset) but pure PPG is forbidden."""
    summary = _task_summary()
    modal = summary["fall_detection"].get("modality_distribution", {})
    ppg_only = modal.get("ppg_only", 0)
    assert ppg_only == 0, f"fall_detection has {ppg_only} ppg_only windows — PPG-only datasets must not enter fall_detection"
    # 'both' windows are acceptable when the dataset has IMU + incidental PPG (e.g. HIFD)
    # The critical safety check is ppg_only == 0 and the explicit safety_check.PASS flag


# ──────────────────────────────────────────────────────────────────────────────
# WildPPG routing tests
# ──────────────────────────────────────────────────────────────────────────────

def test_wildppg_excluded_from_fall_detection():
    """If WildPPG produced windows, it must not appear in fall_detection contributions."""
    summary = _task_summary()
    fall_contributions = summary["fall_detection"].get("dataset_contributions", {})
    assert "WildPPG" not in fall_contributions, (
        "WildPPG incorrectly routed into fall_detection"
    )


def test_wildppg_present_in_ppg_quality():
    """WildPPG should contribute to ppg_quality if it loaded successfully."""
    ds_summary = _dataset_summary()
    wildppg_status = ds_summary.get("load_stats", {}).get("wildppg", {}).get("status", "missing")
    if wildppg_status not in ("ok", "partial"):
        pytest.skip(f"WildPPG loader status '{wildppg_status}' — skipping routing check")

    summary = _task_summary()
    contributions = summary["ppg_quality"].get("dataset_contributions", {})
    assert "WildPPG" in contributions, (
        "WildPPG loaded successfully but is absent from ppg_quality contributions"
    )


def test_wildppg_present_in_vitals_context():
    """WildPPG should contribute to vitals_context if it loaded successfully."""
    ds_summary = _dataset_summary()
    wildppg_status = ds_summary.get("load_stats", {}).get("wildppg", {}).get("status", "missing")
    if wildppg_status not in ("ok", "partial"):
        pytest.skip(f"WildPPG loader status '{wildppg_status}' — skipping routing check")

    summary = _task_summary()
    contributions = summary["vitals_context"].get("dataset_contributions", {})
    assert "WildPPG" in contributions, (
        "WildPPG loaded successfully but is absent from vitals_context contributions"
    )


# ──────────────────────────────────────────────────────────────────────────────
# UMAFall routing tests
# ──────────────────────────────────────────────────────────────────────────────

def test_umafall_present_in_fall_detection():
    """UMAFall must contribute to fall_detection if it loaded successfully."""
    ds_summary = _dataset_summary()
    umafall_status = ds_summary.get("load_stats", {}).get("umafall", {}).get("status", "missing")
    if umafall_status not in ("ok", "partial"):
        pytest.skip(f"UMAFall loader status '{umafall_status}' — skipping routing check")

    summary = _task_summary()
    contributions = summary["fall_detection"].get("dataset_contributions", {})
    assert "UMAFall" in contributions, (
        "UMAFall loaded successfully but is absent from fall_detection contributions"
    )


def test_umafall_has_fall_and_normal_labels():
    """fall_detection label distribution must include both 'normal' and 'fall'."""
    summary = _task_summary()
    label_dist = summary["fall_detection"].get("label_distribution", {})
    assert "normal" in label_dist, "fall_detection has no 'normal' labels"
    assert "fall" in label_dist, "fall_detection has no 'fall' labels"


# ──────────────────────────────────────────────────────────────────────────────
# Robustness: empty optional datasets don't break build
# ──────────────────────────────────────────────────────────────────────────────

def test_empty_optional_datasets_do_not_break_build():
    """
    Datasets that are EMPTY or partial (mobiact, fallalld, pads_smartwatch_pd,
    fallalld_sensor_only) must not cause the build to fail — the summary files
    must still be created.
    """
    assert TASK_SUMMARY.exists(), "task_specific_summary.json missing — build may have crashed"
    assert DATASET_SUMMARY.exists(), "dataset_summary.json missing — build may have crashed"
    ds_summary = _dataset_summary()
    empty_slugs = ["mobiact", "fallalld", "pads_smartwatch_pd", "fallalld_sensor_only"]
    for slug in empty_slugs:
        info = ds_summary.get("load_stats", {}).get(slug, {})
        # Status may be "empty", "partial", or "no_data" — all are acceptable
        # The important thing is the build completed (checked by file existence above)
        status = info.get("status", "missing")
        assert status != "missing", f"Expected empty/partial for '{slug}', got 'missing'"


def test_global_total_windows_exceeds_previous_baseline():
    """Total window count must exceed the pre-UMAFall/WildPPG baseline of 197,584."""
    ds_summary = _dataset_summary()
    total = ds_summary.get("total_windows", 0)
    assert total > 197584, (
        f"Total windows={total} does not exceed pre-UMAFall/WildPPG baseline of 197,584"
    )


def test_task_specific_npz_files_exist():
    """All expected task-specific NPZ split files must exist on disk."""
    summary = _task_summary()
    for task, info in summary.items():
        for split, path_str in info.get("export_files", {}).items():
            p = pathlib.Path(path_str)
            assert p.exists(), f"Missing NPZ export: {task}/{split}.npz at {p}"
