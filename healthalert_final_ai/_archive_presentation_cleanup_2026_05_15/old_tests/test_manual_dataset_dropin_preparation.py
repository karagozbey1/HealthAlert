"""
test_manual_dataset_dropin_preparation.py
──────────────────────────────────────────
HealthAlert: Tests for Manual Dataset Drop-in Preparation

Verifies that:
1. All manual raw dataset directories exist
2. Each directory has a README_DROP_HERE.md
3. manual_dataset_manifest.yaml is parseable
4. datasets.yaml contains all new slugs
5. Validation script doesn't crash on empty/missing dirs
6. FallAllD vision-only rejection works correctly
7. loader_registry recognizes new dataset slugs
8. Empty datasets don't break the build pipeline
9. Task-specific output directories exist
10. README_MANUAL_DATASET_SETUP.md exists
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# ─────────────────────────────── paths ──────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
CONFIG_DIR = PROJECT_ROOT / "config"
DATASETS_YAML = CONFIG_DIR / "datasets.yaml"
MANIFEST_YAML = CONFIG_DIR / "manual_dataset_manifest.yaml"
DOCS_DIR = PROJECT_ROOT.parent / "docs" / "dataset_manual_downloads"
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "windowed_dataset"

MANUAL_DATASET_SLUGS = [
    "sisfall",
    "unimib_shar",
    "ppg_dalia",
    "bits2_geriatric_fall_hr",
    "wesad",
    "umafall",
    "upfall",
    "daphnet_fog",
    "pads_smartwatch_pd",
    "hand_tremor_mpu9250",
    "wildppg",
    "fallalld_sensor_only",
]

NEW_SLUGS = [
    "bits2_geriatric_fall_hr",
    "daphnet_fog",
    "pads_smartwatch_pd",
    "hand_tremor_mpu9250",
    "fallalld_sensor_only",
]

TASK_SUBDIRS = [
    "fall_detection",
    "ppg_quality",
    "vitals_context",
    "activity_context",
    "gait_instability",
    "tremor_context",
]


# ─────────────────────── Test 1: raw dirs exist ──────────────────────────────

def test_all_manual_raw_dirs_exist():
    """All manual dataset raw directories must exist (even if empty)."""
    missing = [slug for slug in MANUAL_DATASET_SLUGS
               if not (DATA_RAW / slug).exists()]
    assert not missing, f"Missing raw dirs: {missing}"


# ─────────────────── Test 2: README_DROP_HERE.md in each dir ─────────────────

def test_each_raw_dir_has_readme():
    """Each manual dataset directory must contain README_DROP_HERE.md."""
    missing_readme = []
    for slug in MANUAL_DATASET_SLUGS:
        readme = DATA_RAW / slug / "README_DROP_HERE.md"
        if not readme.exists():
            missing_readme.append(slug)
    assert not missing_readme, f"Missing README_DROP_HERE.md in: {missing_readme}"


# ───────────────── Test 3: manifest yaml is parseable ────────────────────────

def test_manifest_yaml_parseable():
    """manual_dataset_manifest.yaml must be valid YAML with priority groups."""
    assert MANIFEST_YAML.exists(), f"Manifest not found: {MANIFEST_YAML}"
    with open(MANIFEST_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), "manifest YAML root must be a dict"
    assert "priority_1" in data, "manifest must have priority_1 group"
    assert "priority_2" in data, "manifest must have priority_2 group"
    # Each priority group must be a list
    for group in ("priority_1", "priority_2", "priority_3"):
        if group in data:
            assert isinstance(data[group], list), f"{group} must be a list"


# ────────────────── Test 4: datasets.yaml has new slugs ──────────────────────

def test_datasets_yaml_contains_new_slugs():
    """datasets.yaml must contain all 5 new dataset slug entries."""
    assert DATASETS_YAML.exists(), f"datasets.yaml not found: {DATASETS_YAML}"
    with open(DATASETS_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    datasets = data.get("datasets", {})
    missing = [slug for slug in NEW_SLUGS if slug not in datasets]
    assert not missing, f"datasets.yaml missing slugs: {missing}"


# ────────────── Test 5: validate script doesn't crash on empty dirs ───────────

def test_validate_script_does_not_crash():
    """validate_manual_dataset_layout.py should complete with exit code 0."""
    script = PROJECT_ROOT / "scripts" / "validate_manual_dataset_layout.py"
    assert script.exists(), f"Validation script not found: {script}"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"Validation script exited with code {result.returncode}\n"
        f"STDOUT:\n{result.stdout[-2000:]}\n"
        f"STDERR:\n{result.stderr[-1000:]}"
    )


# ───────────── Test 6: FallAllD vision-only rejection ────────────────────────

def test_fallalld_sensor_loader_rejects_vision_only(tmp_path):
    """FallAllD loader must return unsupported_vision_only when only image files present."""
    # Create a temp dir with fake image files
    fake_dir = tmp_path / "fallalld_vision_only"
    fake_dir.mkdir()
    (fake_dir / "depth_frame_001.jpg").write_bytes(b"fake_image_data")
    (fake_dir / "rgb_000.png").write_bytes(b"fake_rgb_data")

    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from data.loaders.fallalld_sensor_loader import load_dataset

    result = load_dataset(str(fake_dir), {})
    assert result.status == "unsupported_vision_only", (
        f"Expected 'unsupported_vision_only', got '{result.status}'"
    )


# ─────────────── Test 7: loader_registry recognizes new slugs ────────────────

@pytest.mark.parametrize("name_key,expected_status", [
    ("BITS2_GERIATRIC_FALL_HR", "missing"),
    ("DAPHNET_FOG", "missing"),
    ("PADS_SMARTWATCH_PD", "missing"),
    ("HAND_TREMOR_MPU9250", "missing"),
    ("FALLALLD_SENSOR_ONLY", "missing"),
])
def test_loader_registry_recognizes_new_slugs(name_key, expected_status):
    """loader_registry must dispatch new slugs (return missing for non-existent paths)."""
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from data.loader_registry import load_dataset_by_name

    cfg = {
        "name": name_key,
        "local_path": "/nonexistent/path/for/testing/12345",
    }
    result = load_dataset_by_name(cfg)
    assert result.status == expected_status, (
        f"For {name_key}: expected status='{expected_status}', got '{result.status}'"
    )


# ──────────── Test 8: empty dataset doesn't break build ──────────────────────

def test_empty_dataset_dir_returns_empty_or_missing(tmp_path):
    """An empty dataset directory should return status=empty or missing, not raise."""
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from data.loaders.bits2_loader import load_dataset

    empty_dir = tmp_path / "bits2_empty"
    empty_dir.mkdir()

    result = load_dataset(str(empty_dir), {})
    assert result.status in ("empty", "missing", "needs_loader_update"), (
        f"Expected empty/missing, got '{result.status}'"
    )


# ───────────── Test 9: task-specific output dirs exist ───────────────────────

def test_task_specific_output_dirs_exist():
    """Task-specific windowed output directories must exist."""
    missing = []
    for task in TASK_SUBDIRS:
        task_dir = OUTPUTS_DIR / task
        if not task_dir.exists():
            missing.append(str(task_dir))
    assert not missing, f"Missing task output dirs:\n" + "\n".join(missing)


# ────────────── Test 10: README_MANUAL_DATASET_SETUP.md exists ────────────────

def test_readme_manual_dataset_setup_exists():
    """docs/dataset_manual_downloads/README_MANUAL_DATASET_SETUP.md must exist."""
    readme = DOCS_DIR / "README_MANUAL_DATASET_SETUP.md"
    assert readme.exists(), f"Manual setup README not found: {readme}"
    content = readme.read_text(encoding="utf-8")
    assert "Öncelik" in content, "README should contain priority sections"
    assert "falldataset.com" in content, "README should warn about falldataset.com"
