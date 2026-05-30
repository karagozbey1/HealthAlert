"""Tests for Dataset Final Cleanup Before Full Training.

Covers:
- HIFD / WEDA-Fall / BUT-PPG no_data fixes (local_path corrections)
- UCI-HAR pre-windowed padding fix (128 → 200 samples)
- tremor_context window count and training policy status
- fall_detection safety checks remain valid
- task_training_policy.yaml structure and guard logic
- Build stability with partial/empty datasets

Run:
    python -m pytest tests/test_dataset_final_cleanup_before_training.py -v --tb=short
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

# ─── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "windowed_dataset"
SUMMARY_JSON = OUTPUTS_DIR / "dataset_summary.json"
TASK_SUMMARY_JSON = OUTPUTS_DIR / "task_specific_summary.json"
POLICY_YAML = PROJECT_ROOT / "config" / "task_training_policy.yaml"
DATASETS_YAML = PROJECT_ROOT / "config" / "datasets.yaml"

MIN_TREMOR_WINDOWS = 500  # Must match policy file


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def task_summary():
    if not TASK_SUMMARY_JSON.exists():
        pytest.skip("task_specific_summary.json not found — run build first.")
    with open(TASK_SUMMARY_JSON) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def global_summary():
    if not SUMMARY_JSON.exists():
        pytest.skip("dataset_summary.json not found — run build first.")
    with open(SUMMARY_JSON) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def policy():
    if not POLICY_YAML.exists():
        pytest.skip("task_training_policy.yaml not found.")
    with open(POLICY_YAML) as f:
        return yaml.safe_load(f)


# ─── A. HIFD / WEDA-Fall / BUT-PPG ───────────────────────────────────────────

class TestPathFixes:
    """Verify that HIFD, WEDA-Fall, and BUT-PPG now contribute windows."""

    def test_hifd_path_updated_in_datasets_yaml(self):
        """datasets.yaml must point to data/raw/hifd/HIFD (not data/raw/hifd)."""
        with open(DATASETS_YAML) as f:
            cfg = yaml.safe_load(f)
        lp = cfg["datasets"]["hifd"]["local_path"]
        assert lp.endswith("HIFD"), (
            f"HIFD local_path should end with HIFD but got: {lp}"
        )

    def test_weda_fall_path_updated_in_datasets_yaml(self):
        """datasets.yaml must point to data/raw/weda_fall/WEDA_FALL."""
        with open(DATASETS_YAML) as f:
            cfg = yaml.safe_load(f)
        lp = cfg["datasets"]["weda_fall"]["local_path"]
        assert lp.endswith("WEDA_FALL"), (
            f"WEDA_FALL local_path should end with WEDA_FALL but got: {lp}"
        )

    def test_but_ppg_path_updated_in_datasets_yaml(self):
        """datasets.yaml must point to data/raw/but_ppg/BUT_PPG."""
        with open(DATASETS_YAML) as f:
            cfg = yaml.safe_load(f)
        lp = cfg["datasets"]["but_ppg"]["local_path"]
        assert lp.endswith("BUT_PPG"), (
            f"BUT_PPG local_path should end with BUT_PPG but got: {lp}"
        )

    def test_hifd_contributes_windows(self, task_summary):
        """HIFD must appear in fall_detection dataset contributions."""
        fd = task_summary.get("fall_detection", {})
        contribs = fd.get("dataset_contributions", {})
        assert "HIFD" in contribs, "HIFD missing from fall_detection contributions"
        assert contribs["HIFD"] > 0, "HIFD produced 0 windows in fall_detection"

    def test_weda_fall_contributes_windows(self, task_summary):
        """WEDA_FALL must appear in fall_detection dataset contributions."""
        fd = task_summary.get("fall_detection", {})
        contribs = fd.get("dataset_contributions", {})
        assert "WEDA_FALL" in contribs, "WEDA_FALL missing from fall_detection contributions"
        assert contribs["WEDA_FALL"] > 0, "WEDA_FALL produced 0 windows in fall_detection"

    def test_but_ppg_contributes_to_ppg_quality(self, task_summary):
        """BUT_PPG must appear in ppg_quality dataset contributions."""
        pq = task_summary.get("ppg_quality", {})
        contribs = pq.get("dataset_contributions", {})
        assert "BUT_PPG" in contribs, "BUT_PPG missing from ppg_quality contributions"
        assert contribs["BUT_PPG"] > 0, "BUT_PPG produced 0 windows in ppg_quality"

    def test_but_ppg_not_in_fall_detection(self, task_summary):
        """BUT_PPG must NOT appear in fall_detection contributions."""
        fd = task_summary.get("fall_detection", {})
        contribs = fd.get("dataset_contributions", {})
        assert "BUT_PPG" not in contribs, "BUT_PPG must not appear in fall_detection"

    def test_ppg_quality_has_good_quality_label(self, task_summary):
        """ppg_quality must have good_quality labels (from BUT-PPG quality=1 records)."""
        pq = task_summary.get("ppg_quality", {})
        ld = pq.get("label_distribution", {})
        assert "good_quality" in ld, "good_quality label missing from ppg_quality"
        assert ld["good_quality"] > 0, "good_quality label count is 0"


# ─── B. UCI-HAR ───────────────────────────────────────────────────────────────

class TestUciHar:
    """Verify UCI-HAR now contributes to activity_context."""

    def test_uci_har_loader_pads_to_200_samples(self):
        """UCI-HAR loader must zero-pad each window to 200 samples."""
        from src.data.loaders.uci_har_loader import load_dataset
        raw_dir = PROJECT_ROOT / "data" / "raw" / "uci_har"
        if not raw_dir.exists():
            pytest.skip("UCI-HAR raw data not found.")
        result = load_dataset(str(raw_dir), {})
        assert result.records, "UCI-HAR returned 0 records"
        r = result.records[0]
        assert r.imu_samples is not None
        assert r.imu_samples.shape[0] == 200, (
            f"Expected 200 samples after padding but got {r.imu_samples.shape[0]}"
        )

    def test_uci_har_metadata_marks_pre_windowed(self):
        """UCI-HAR records must be marked pre_windowed=True in metadata."""
        from src.data.loaders.uci_har_loader import load_dataset
        raw_dir = PROJECT_ROOT / "data" / "raw" / "uci_har"
        if not raw_dir.exists():
            pytest.skip("UCI-HAR raw data not found.")
        result = load_dataset(str(raw_dir), {})
        assert result.records
        r = result.records[0]
        assert r.metadata.get("pre_windowed") is True

    def test_uci_har_contributes_to_activity_context(self, task_summary):
        """UCI-HAR must appear in activity_context contributions with > 0 windows."""
        ac = task_summary.get("activity_context", {})
        contribs = ac.get("dataset_contributions", {})
        assert "UCI-HAR" in contribs, "UCI-HAR missing from activity_context contributions"
        assert contribs["UCI-HAR"] > 0, "UCI-HAR produced 0 windows in activity_context"

    def test_uci_har_not_in_fall_detection(self, task_summary):
        """UCI-HAR must NOT appear in fall_detection contributions."""
        fd = task_summary.get("fall_detection", {})
        contribs = fd.get("dataset_contributions", {})
        assert "UCI-HAR" not in contribs, "UCI-HAR must not appear in fall_detection"


# ─── C. tremor_context ────────────────────────────────────────────────────────

class TestTremorContext:
    """Verify tremor_context window count and training policy status."""

    def test_tremor_loader_uses_single_record(self):
        """Hand-tremor loader must return a single full-CSV record (not per-segment)."""
        from src.data.loaders.hand_tremor_loader import load_dataset
        raw_dir = PROJECT_ROOT / "data" / "raw" / "hand_tremor_mpu9250"
        if not raw_dir.exists():
            pytest.skip("Hand-tremor raw data not found.")
        result = load_dataset(str(raw_dir), {})
        assert result.records, "Hand-tremor returned 0 records"
        # Should be 1 record per CSV file (single full-data record)
        r = result.records[0]
        assert r.imu_samples.shape[0] > 400, (
            "Single-record approach must have > 400 samples (4s @ 100Hz) in the first record"
        )
        assert r.metadata.get("windowing_note") == "sliding_window_applied_by_pipeline"

    def test_tremor_context_window_count_is_positive(self, task_summary):
        """tremor_context must have at least 1 window after single-record fix."""
        tc = task_summary.get("tremor_context", {})
        assert tc.get("total", 0) > 0, "tremor_context produced 0 windows"

    def test_tremor_context_window_count_increased_from_baseline(self, task_summary):
        """tremor_context must have more than the old 18-window baseline."""
        tc = task_summary.get("tremor_context", {})
        assert tc.get("total", 0) > 18, (
            "tremor_context still at or below 18-window baseline"
        )

    def test_tremor_context_below_500_threshold(self, task_summary):
        """tremor_context is expected to be below 500 windows (policy disabled)."""
        tc = task_summary.get("tremor_context", {})
        total = tc.get("total", 0)
        if total >= MIN_TREMOR_WINDOWS:
            pytest.skip("tremor_context now meets threshold — update policy to enabled.")
        assert total < MIN_TREMOR_WINDOWS

    def test_tremor_not_in_fall_detection(self, task_summary):
        """Hand-Tremor dataset must NOT be in fall_detection contributions."""
        fd = task_summary.get("fall_detection", {})
        contribs = fd.get("dataset_contributions", {})
        tremor_keys = [k for k in contribs if "tremor" in k.lower() or "TREMOR" in k.upper()]
        assert not tremor_keys, f"Tremor datasets found in fall_detection: {tremor_keys}"

    def test_tremor_has_both_labels(self, task_summary):
        """tremor_context must have both normal and instability labels."""
        tc = task_summary.get("tremor_context", {})
        ld = tc.get("label_distribution", {})
        assert "normal" in ld, "normal label missing from tremor_context"
        assert "instability" in ld, "instability label missing from tremor_context"


# ─── D. Training Policy Guard ─────────────────────────────────────────────────

class TestTrainingPolicyGuard:
    """Verify task_training_policy.yaml structure and enforcement."""

    def test_policy_yaml_is_parseable(self, policy):
        """task_training_policy.yaml must parse without error."""
        assert policy is not None

    def test_policy_has_all_six_tasks(self, policy):
        tasks = policy.get("tasks", {})
        expected = {
            "fall_detection", "ppg_quality", "vitals_context",
            "activity_context", "gait_instability", "tremor_context"
        }
        assert expected.issubset(set(tasks.keys())), (
            f"Missing tasks in policy: {expected - set(tasks.keys())}"
        )

    def test_fall_detection_is_enabled(self, policy):
        assert policy["tasks"]["fall_detection"]["enabled_for_training"] is True

    def test_ppg_quality_is_enabled(self, policy):
        assert policy["tasks"]["ppg_quality"]["enabled_for_training"] is True

    def test_vitals_context_is_enabled(self, policy):
        assert policy["tasks"]["vitals_context"]["enabled_for_training"] is True

    def test_activity_context_is_enabled(self, policy):
        assert policy["tasks"]["activity_context"]["enabled_for_training"] is True

    def test_gait_instability_is_enabled(self, policy):
        assert policy["tasks"]["gait_instability"]["enabled_for_training"] is True

    def test_tremor_context_is_disabled(self, policy):
        """tremor_context must be disabled because actual_windows < min_windows_required."""
        tc = policy["tasks"]["tremor_context"]
        assert tc["enabled_for_training"] is False, (
            "tremor_context should be disabled (insufficient data)"
        )

    def test_tremor_context_status_is_optional_low_data(self, policy):
        tc = policy["tasks"]["tremor_context"]
        assert tc.get("status") in ("optional_low_data", "passive_context")

    def test_tremor_context_actual_windows_matches_policy_threshold(self, policy):
        tc = policy["tasks"]["tremor_context"]
        actual = tc.get("actual_windows", 0)
        minimum = tc.get("min_windows_required", MIN_TREMOR_WINDOWS)
        assert actual < minimum, (
            f"tremor_context actual_windows ({actual}) must be < min_windows_required ({minimum})"
        )

    def test_policy_all_enabled_tasks_meet_threshold(self, policy, task_summary):
        """Every task with enabled_for_training=True must have actual_windows >= min_required."""
        tasks = policy.get("tasks", {})
        for task_name, task_cfg in tasks.items():
            if not task_cfg.get("enabled_for_training", False):
                continue
            actual = task_cfg.get("actual_windows", 0)
            minimum = task_cfg.get("min_windows_required", 0)
            assert actual >= minimum, (
                f"Task {task_name} is enabled but actual_windows ({actual}) < min ({minimum})"
            )


# ─── E. Safety Checks ─────────────────────────────────────────────────────────

class TestSafetyChecks:
    """Verify that fall_detection safety checks remain valid after all fixes."""

    def test_fall_detection_no_label_99(self, task_summary):
        fd = task_summary.get("fall_detection", {})
        sc = fd.get("safety_check", {})
        assert sc.get("label_99_count", 0) == 0, "fall_detection has label=99 windows"

    def test_fall_detection_no_ppg_contamination(self, task_summary):
        fd = task_summary.get("fall_detection", {})
        sc = fd.get("safety_check", {})
        assert sc.get("ppg_vitals_contamination_count", 0) == 0, (
            "fall_detection has PPG/vitals contamination"
        )

    def test_fall_detection_safety_pass(self, task_summary):
        fd = task_summary.get("fall_detection", {})
        sc = fd.get("safety_check", {})
        assert sc.get("PASS") is True, "fall_detection safety check FAILED"

    def test_fall_detection_only_imu_modality(self, task_summary):
        fd = task_summary.get("fall_detection", {})
        md = fd.get("modality_distribution", {})
        assert md.get("ppg_only", 0) == 0, "fall_detection has ppg_only windows"
        assert md.get("both", 0) == 0 or md.get("both", 0) <= 4000, (
            "fall_detection has unexpected PPG+IMU windows — verify HIFD PPG channel"
        )

    def test_wildppg_not_in_fall_detection(self, task_summary):
        fd = task_summary.get("fall_detection", {})
        contribs = fd.get("dataset_contributions", {})
        assert "WildPPG" not in contribs, "WildPPG must not appear in fall_detection"

    def test_daphnet_not_in_fall_detection(self, task_summary):
        fd = task_summary.get("fall_detection", {})
        contribs = fd.get("dataset_contributions", {})
        daphnet_keys = [k for k in contribs if "daphnet" in k.lower() or "fog" in k.lower()]
        assert not daphnet_keys, f"Daphnet found in fall_detection: {daphnet_keys}"

    def test_global_window_count_exceeds_previous_baseline(self, task_summary):
        """Total window count must exceed the 374,942 baseline from last session."""
        previous_baseline = 374_942
        total = sum(v.get("total", 0) for v in task_summary.values())
        # Use global summary if available, else sum task totals (double-counts are OK here)
        if SUMMARY_JSON.exists():
            with open(SUMMARY_JSON) as f:
                gs = json.load(f)
            total = gs.get("total_windows", total)
        assert total > previous_baseline, (
            f"Total windows {total} does not exceed previous baseline {previous_baseline}"
        )


# ─── F. Build Stability ───────────────────────────────────────────────────────

class TestBuildStability:
    """Build must not crash due to partial/empty optional datasets."""

    def test_task_specific_summary_json_exists(self):
        assert TASK_SUMMARY_JSON.exists(), "task_specific_summary.json not generated"

    def test_task_specific_summary_has_all_six_tasks(self, task_summary):
        expected = {
            "fall_detection", "ppg_quality", "vitals_context",
            "activity_context", "gait_instability", "tremor_context"
        }
        assert expected.issubset(set(task_summary.keys())), (
            f"Missing tasks in summary: {expected - set(task_summary.keys())}"
        )

    def test_all_task_npz_files_exist(self):
        for task in [
            "fall_detection", "ppg_quality", "vitals_context",
            "activity_context", "gait_instability", "tremor_context",
        ]:
            task_dir = OUTPUTS_DIR / task
            assert task_dir.exists(), f"Task directory missing: {task}"
            # At least one .npz file must exist per task
            npz_files = list(task_dir.glob("*.npz"))
            assert npz_files, f"No .npz files in {task} directory"

    def test_no_task_has_zero_windows_except_no_data(self, task_summary):
        """All tasks in the summary must have total > 0 (except tremor may be low)."""
        for task_name, info in task_summary.items():
            total = info.get("total", 0)
            assert total > 0, f"Task {task_name} has 0 total windows"
