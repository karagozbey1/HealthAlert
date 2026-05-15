"""
validate_manual_dataset_layout.py
──────────────────────────────────
HealthAlert: Manual Dataset Layout Validation Script

Reads datasets.yaml + manual_dataset_manifest.yaml, checks each raw dataset dir,
and produces a JSON status report plus a Markdown summary.

NEVER crashes on missing datasets — all errors are reported in output files.

Usage:
    python scripts/validate_manual_dataset_layout.py [--output-json PATH] [--output-md PATH]

Exit codes:
    0 = all checked (some may be missing/empty — see report for details)
    1 = fatal error reading config files
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


# ──────────────────────────── constants ─────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATASETS_YAML = CONFIG_DIR / "datasets.yaml"
MANIFEST_YAML = CONFIG_DIR / "manual_dataset_manifest.yaml"
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "reports"
DOCS_DIR = PROJECT_ROOT.parent / "docs" / "dataset_manual_downloads"

DEFAULT_JSON_OUTPUT = OUTPUTS_DIR / "manual_dataset_layout_status.json"
DEFAULT_MD_OUTPUT = DOCS_DIR / "manual_dataset_layout_status.md"

# File extensions that indicate vision-only content (rejected)
VISION_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff",
                     ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv"}
DEPTH_PATTERNS = ["depth", "kinect", "rgb", "frame", "skeleton"]

# Valid status values
STATUS_READY = "ready"
STATUS_EMPTY = "empty"
STATUS_MISSING = "missing"
STATUS_PARTIAL = "partial"
STATUS_UNSUPPORTED_VISION_ONLY = "unsupported_vision_only"
STATUS_NEEDS_LOADER_UPDATE = "needs_loader_update"
STATUS_UNKNOWN_FORMAT = "unknown_format"


# ──────────────────────────── helpers ───────────────────────────────────────

def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def list_all_files(directory: Path) -> list[Path]:
    """Recursively list all files under directory. Returns empty list if dir missing."""
    if not directory.exists():
        return []
    return [p for p in directory.rglob("*") if p.is_file()]


def has_vision_content(files: list[Path]) -> bool:
    """Return True if any file is an image/video (vision-only indicator)."""
    for f in files:
        ext = f.suffix.lower()
        if ext in VISION_EXTENSIONS:
            return True
        # Check path components for depth/kinect keywords
        parts_lower = " ".join(p.lower() for p in f.parts)
        if any(kw in parts_lower for kw in DEPTH_PATTERNS):
            return True
    return False


def get_accepted_extensions(dataset_cfg: dict) -> set[str]:
    raw = dataset_cfg.get("accepted_extensions", [])
    return {ext.lower() for ext in raw} if raw else set()


def get_rejected_extensions(dataset_cfg: dict) -> set[str]:
    raw = dataset_cfg.get("rejected_extensions", [])
    return {ext.lower() for ext in raw} if raw else set()


def check_dataset(slug: str, dataset_cfg: dict, project_root: Path) -> dict:
    """
    Check a single dataset directory and return a status dict.
    Never raises — all errors are captured in result.
    """
    result: dict = {
        "slug": slug,
        "status": STATUS_MISSING,
        "path_checked": None,
        "n_files": 0,
        "accepted_files": 0,
        "rejected_files": 0,
        "vision_files": 0,
        "warnings": [],
        "errors": [],
        "details": {}
    }

    raw_path_str = dataset_cfg.get("local_path", "")
    if not raw_path_str:
        result["errors"].append("No local_path configured in datasets.yaml")
        result["status"] = STATUS_MISSING
        return result

    # Resolve local_path: handle OmegaConf-style interpolations → actual data/raw paths
    raw_path_str = raw_path_str.replace("${paths.hifd_dir}", "data/raw/hifd")
    raw_path_str = raw_path_str.replace("${paths.weda_fall_dir}", "data/raw/weda_fall")
    raw_path_str = raw_path_str.replace("${paths.but_ppg_dir}", "data/raw/but_ppg")
    # Replace any remaining ${...} interpolations as unknown
    import re as _re
    raw_path_str = _re.sub(r"\$\{[^}]+\}", "", raw_path_str)

    local_path = Path(raw_path_str)
    if not local_path.is_absolute():
        local_path = project_root / raw_path_str

    result["path_checked"] = str(local_path)

    if not local_path.exists():
        result["status"] = STATUS_MISSING
        result["errors"].append(f"Directory not found: {local_path}")
        return result

    all_files = list_all_files(local_path)
    result["n_files"] = len(all_files)

    if not all_files:
        result["status"] = STATUS_EMPTY
        result["warnings"].append("Directory exists but contains no files")
        return result

    # Check for vision-only content (reject)
    accepted_exts = get_accepted_extensions(dataset_cfg)
    rejected_exts = get_rejected_extensions(dataset_cfg)

    vision_files = [f for f in all_files if f.suffix.lower() in VISION_EXTENSIONS]
    rejected_files = [f for f in all_files if f.suffix.lower() in rejected_exts] if rejected_exts else []

    result["vision_files"] = len(vision_files)
    result["rejected_files"] = len(rejected_files)

    # FallAllD special check: vision-only = unsupported
    if slug in ("fallalld", "fallalld_sensor_only"):
        sensor_files = [f for f in all_files
                        if f.suffix.lower() in {".csv", ".txt", ".dat"}]
        if vision_files and not sensor_files:
            result["status"] = STATUS_UNSUPPORTED_VISION_ONLY
            result["errors"].append(
                f"Only image/video files found — falldataset.com RGB/depth version detected. "
                f"This is NOT the sensor-only subset. Vision files: {len(vision_files)}"
            )
            return result
        if vision_files:
            result["warnings"].append(
                f"{len(vision_files)} image/video files detected alongside sensor files. "
                f"Loader will ignore vision files."
            )

    # Check accepted extensions if configured
    if accepted_exts:
        accepted_files = [f for f in all_files if f.suffix.lower() in accepted_exts]
        result["accepted_files"] = len(accepted_files)
        if not accepted_files:
            # Check if there are files with unknown extensions
            found_exts = {f.suffix.lower() for f in all_files if f.suffix}
            readme_only = all(f.name.upper().startswith("README") for f in all_files)
            if readme_only:
                result["status"] = STATUS_EMPTY
                result["warnings"].append(
                    "Only README file(s) present — dataset not yet downloaded."
                )
            else:
                result["status"] = STATUS_UNKNOWN_FORMAT
                result["warnings"].append(
                    f"Found extensions {found_exts!r} but expected {accepted_exts!r}"
                )
            return result
    else:
        # No accepted_extensions configured — count non-readme files
        data_files = [f for f in all_files if not f.name.upper().startswith("README")]
        result["accepted_files"] = len(data_files)
        if not data_files:
            result["status"] = STATUS_EMPTY
            result["warnings"].append("Only README file(s) present — dataset not yet downloaded.")
            return result

    # Determine ready vs partial
    loader_status = dataset_cfg.get("loader_status", "unknown")
    if loader_status in ("active",):
        result["status"] = STATUS_READY
    elif loader_status in ("scaffold", "needs_update"):
        result["status"] = STATUS_NEEDS_LOADER_UPDATE
        result["warnings"].append(
            f"Loader status is '{loader_status}' — dataset files present but loader not fully implemented."
        )
    else:
        result["status"] = STATUS_READY

    result["details"]["loader_status"] = loader_status
    result["details"]["tasks"] = dataset_cfg.get("tasks", [])
    result["details"]["not_for"] = dataset_cfg.get("not_for", [])

    return result


def validate_all(project_root: Path) -> dict:
    """Run validation on all datasets. Returns full report dict."""
    try:
        datasets_data = load_yaml(DATASETS_YAML)
    except Exception as e:
        print(f"[FATAL] Cannot read datasets.yaml: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        manifest_data = load_yaml(MANIFEST_YAML)
    except Exception as e:
        print(f"[WARNING] Cannot read manual_dataset_manifest.yaml: {e}", file=sys.stderr)
        manifest_data = {}

    datasets_cfg = datasets_data.get("datasets", {})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "total_datasets": len(datasets_cfg),
        "summary": {
            "ready": 0,
            "empty": 0,
            "missing": 0,
            "partial": 0,
            "unsupported_vision_only": 0,
            "needs_loader_update": 0,
            "unknown_format": 0,
        },
        "datasets": {}
    }

    for slug, cfg in datasets_cfg.items():
        result = check_dataset(slug, cfg, project_root)
        report["datasets"][slug] = result
        status = result["status"]
        if status in report["summary"]:
            report["summary"][status] += 1
        print(f"  [{status.upper():28s}] {slug}")

    return report, manifest_data


def write_json(report: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n[OK] JSON report written: {output_path}")


def write_markdown(report: dict, manifest_data: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# HealthAlert Manual Dataset Layout Status",
        f"\n_Generated: {report['generated_at']}_\n",
        "## Summary",
        "",
        "| Status | Count |",
        "|--------|-------|",
    ]
    for status, count in report["summary"].items():
        lines.append(f"| {status} | {count} |")

    lines += [
        "",
        "## Dataset Details",
        "",
        "| Dataset | Status | Files | Warnings |",
        "|---------|--------|-------|----------|",
    ]
    for slug, info in report["datasets"].items():
        status = info["status"]
        n_files = info["n_files"]
        warnings = "; ".join(info.get("warnings", []))[:120]
        lines.append(f"| {slug} | {status} | {n_files} | {warnings} |")

    # Task assignments
    lines += ["", "## Task Assignments", ""]
    task_map: dict[str, list] = {}
    for slug, info in report["datasets"].items():
        tasks = info.get("details", {}).get("tasks", [])
        for t in tasks:
            task_map.setdefault(t, []).append(f"{slug} ({info['status']})")

    for task, entries in sorted(task_map.items()):
        lines.append(f"**{task}:** " + ", ".join(entries))
        lines.append("")

    # Manifest priority
    if manifest_data:
        lines += ["", "## Download Priority Order", ""]
        for priority_key in ("priority_1", "priority_2", "priority_3"):
            p_entries = manifest_data.get(priority_key, [])
            if p_entries:
                num = priority_key.replace("priority_", "")
                lines.append(f"### Priority {num}")
                lines.append("")
                for entry in p_entries:
                    slug = entry.get("slug", "")
                    ds_info = report["datasets"].get(slug, {})
                    current_status = ds_info.get("status", "unknown")
                    url = entry.get("download_url") or entry.get("mirror_url", "")
                    lines.append(f"- **{slug}** — `{current_status}` — {url}")
                lines.append("")

    lines += [
        "## Validation Commands",
        "",
        "```bash",
        "# Re-run validation",
        "python scripts/validate_manual_dataset_layout.py",
        "",
        "# After adding datasets, rebuild the windowed dataset",
        "python scripts/build_multi_source_windowed_dataset.py",
        "",
        "# Run all tests",
        "python -m pytest healthalert_final_ai/tests/ -v --tb=short",
        "```",
        "",
        "_Bu rapor otomatik üretilmiştir. Değiştirmeyin._",
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] Markdown report written: {output_path}")


# ──────────────────────────── main ──────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate manual dataset directory layout")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_OUTPUT,
                        help="Path for JSON output report")
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD_OUTPUT,
                        help="Path for Markdown output report")
    args = parser.parse_args()

    print("=" * 60)
    print("HealthAlert -- Manual Dataset Layout Validation")
    print("=" * 60)

    project_root = PROJECT_ROOT
    print(f"Project root: {project_root}\n")

    report, manifest_data = validate_all(project_root)

    print("\n-- Summary ---------------------------------------------------")
    for status, count in report["summary"].items():
        print(f"  {status:32s}: {count}")
    print(f"  {'TOTAL':32s}: {report['total_datasets']}")

    write_json(report, args.output_json)
    write_markdown(report, manifest_data, args.output_md)

    print("\n[DONE] Validation complete — check reports for details.")


if __name__ == "__main__":
    main()
