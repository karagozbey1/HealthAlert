"""
audit_hybrid_dataset_contract.py
─────────────────────────────────────────────────────────────────────────────
Phase 1 — Dataset Contract Audit

Inspects every dataset folder and every task to produce:
  outputs/hybrid_redesign/audit/dataset_contract.json
  outputs/hybrid_redesign/audit/dataset_contract_report.md

Checks performed per dataset × task:
  - dataset folder exists
  - standardized output exists
  - windowed output exists
  - split output exists
  - available modalities
  - window shape (if NPZ/npy files found)
  - label names and distribution (from NPZ or manifest files)
  - train/val/test counts
  - whether subject-level split is possible
  - routing compliance (allowed / forbidden per hybrid_task_routing.yaml)

Usage:
  cd healthalert_final_ai/
  python scripts/audit_hybrid_dataset_contract.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import yaml

# ─── project root on path ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("audit_contract")

# ─── paths ───────────────────────────────────────────────────────────────────
DATA_ROOT = ROOT / "data"
RAW_ROOT = DATA_ROOT / "raw"
STANDARDIZED_ROOT = DATA_ROOT / "standardized"
WINDOWED_ROOT = DATA_ROOT / "windowed"
SPLITS_ROOT = DATA_ROOT / "splits"
WINDOWED_DATASET_ROOT = ROOT / "outputs" / "windowed_dataset"

ROUTING_CFG = ROOT / "config" / "hybrid_task_routing.yaml"
OUT_DIR = ROOT / "outputs" / "hybrid_redesign" / "audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── modality detection heuristics ───────────────────────────────────────────
MODALITY_KEYWORDS: Dict[str, List[str]] = {
    "imu": ["imu", "accel", "gyro", "acc", "gyr", "motion"],
    "acc": ["accel", "acc", "acceleration"],
    "gyro": ["gyro", "gyr", "gyroscope"],
    "ppg": ["ppg", "bvp", "photopleth"],
    "heart": ["heart", "hr", "bvp", "pulse"],
    "vitals": ["vitals", "spo2", "respiratory", "respir", "rr"],
    "handcrafted": ["features", "handcrafted", "hc_"],
    "metadata": ["meta", "subject", "session", "label"],
}


def detect_modalities(folder: Path) -> List[str]:
    """Heuristically detect available modalities from filenames/subfolders."""
    found: set = set()
    if not folder.exists():
        return []
    all_names = [p.name.lower() for p in folder.rglob("*") if p.is_file()]
    for mod, keywords in MODALITY_KEYWORDS.items():
        for name in all_names:
            if any(kw in name for kw in keywords):
                found.add(mod)
                break
    return sorted(found)


def probe_npz(folder: Path) -> Dict[str, Any]:
    """Load first NPZ in folder, return shape/label info."""
    info: Dict[str, Any] = {}
    if not folder.exists():
        return info
    npz_files = list(folder.rglob("*.npz"))
    if not npz_files:
        npy_files = list(folder.rglob("*.npy"))
        if not npy_files:
            return info
        # try reading first npy as windows
        try:
            arr = np.load(str(npy_files[0]))
            info["window_shape"] = list(arr.shape[1:]) if arr.ndim > 1 else list(arr.shape)
        except Exception:
            pass
        return info
    try:
        data = np.load(str(npz_files[0]), allow_pickle=True)
        keys = list(data.keys())
        info["npz_keys"] = keys
        if "X" in data:
            info["window_shape"] = list(data["X"].shape[1:])
            info["n_windows"] = int(data["X"].shape[0])
        elif "windows" in data:
            info["window_shape"] = list(data["windows"].shape[1:])
            info["n_windows"] = int(data["windows"].shape[0])
        if "y" in data:
            labels = data["y"].flatten().astype(int)
            unique, counts = np.unique(labels, return_counts=True)
            info["label_ids"] = unique.tolist()
            info["label_distribution"] = dict(zip(unique.tolist(), counts.tolist()))
        elif "labels" in data:
            labels = data["labels"].flatten().astype(int)
            unique, counts = np.unique(labels, return_counts=True)
            info["label_ids"] = unique.tolist()
            info["label_distribution"] = dict(zip(unique.tolist(), counts.tolist()))
    except Exception as exc:
        info["probe_error"] = str(exc)
    return info


def count_splits(splits_folder: Path) -> Dict[str, int]:
    """Count train/val/test windows in split NPZ files."""
    counts: Dict[str, int] = {}
    if not splits_folder.exists():
        return counts
    for split in ("train", "val", "test"):
        n = 0
        for f in splits_folder.rglob(f"{split}*.npz"):
            try:
                d = np.load(str(f), allow_pickle=True)
                key = "X" if "X" in d else ("windows" if "windows" in d else None)
                if key:
                    n += int(d[key].shape[0])
            except Exception:
                pass
        if n > 0:
            counts[split] = n
    return counts


def check_subject_split_possible(raw_folder: Path) -> bool:
    """Return True if raw folder contains per-subject sub-directories."""
    if not raw_folder.exists():
        return False
    subdirs = [p for p in raw_folder.iterdir() if p.is_dir()]
    return len(subdirs) >= 2


def audit_dataset(name: str, routing: Dict[str, Any]) -> Dict[str, Any]:
    """Full audit record for one dataset."""
    raw_folder = RAW_ROOT / name
    std_folder = STANDARDIZED_ROOT / name
    win_folder = WINDOWED_ROOT / name
    split_folder = SPLITS_ROOT / name

    # Also check outputs/windowed_dataset/ (task-split NPZs)
    task_npz_folder = WINDOWED_DATASET_ROOT / name

    record: Dict[str, Any] = {
        "dataset": name,
        "raw_exists": raw_folder.exists(),
        "standardized_exists": std_folder.exists(),
        "windowed_exists": win_folder.exists() or task_npz_folder.exists(),
        "splits_exist": split_folder.exists() and any(split_folder.rglob("*.npz")),
        "subject_split_possible": check_subject_split_possible(raw_folder),
        "modalities": detect_modalities(raw_folder),
        "task_routing": {},
    }

    # Window shape / label distribution from windowed folder
    win_probe = probe_npz(win_folder) or probe_npz(task_npz_folder)
    record.update(win_probe)

    split_counts = count_splits(split_folder)
    if split_counts:
        record["split_counts"] = split_counts

    # Per-task routing compliance
    for task_name, task_cfg in routing.items():
        allowed = task_cfg.get("allowed_datasets", [])
        forbidden = task_cfg.get("forbidden_datasets", [])
        enabled = task_cfg.get("enabled_for_training", True)
        routing_status = "not_applicable"
        if name in allowed:
            routing_status = "allowed"
        elif name in forbidden:
            routing_status = "forbidden"
        record["task_routing"][task_name] = {
            "status": routing_status,
            "task_enabled": enabled,
        }

    return record


def build_contract(routing: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Audit all known datasets."""
    all_datasets: set = set()
    for task_cfg in routing.values():
        all_datasets.update(task_cfg.get("allowed_datasets", []))
        all_datasets.update(task_cfg.get("forbidden_datasets", []))
    # Also pick up datasets physically present in raw/
    if RAW_ROOT.exists():
        for d in RAW_ROOT.iterdir():
            if d.is_dir():
                all_datasets.add(d.name)

    results = []
    for name in sorted(all_datasets):
        log.info(f"  Auditing dataset: {name}")
        results.append(audit_dataset(name, routing))
    return results


def write_json(contract: List[Dict[str, Any]]) -> Path:
    out_path = OUT_DIR / "dataset_contract.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {"generated_at": datetime.utcnow().isoformat() + "Z", "datasets": contract},
            f,
            indent=2,
        )
    log.info(f"JSON contract written → {out_path}")
    return out_path


def write_markdown(contract: List[Dict[str, Any]], routing: Dict[str, Any]) -> Path:
    lines: List[str] = []
    lines.append("# HealthAlert Hybrid Dataset Contract Report")
    lines.append(f"\n_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n")

    # Summary table
    lines.append("## Dataset Status Overview\n")
    lines.append(
        "| Dataset | raw | std | windowed | splits | modalities | subject-split |"
    )
    lines.append("|---------|-----|-----|----------|--------|------------|---------------|")
    for rec in contract:
        lines.append(
            f"| {rec['dataset']} "
            f"| {'✓' if rec['raw_exists'] else '✗'} "
            f"| {'✓' if rec['standardized_exists'] else '✗'} "
            f"| {'✓' if rec['windowed_exists'] else '✗'} "
            f"| {'✓' if rec['splits_exist'] else '✗'} "
            f"| {', '.join(rec.get('modalities', [])) or '—'} "
            f"| {'✓' if rec['subject_split_possible'] else '✗'} |"
        )

    # Per-task routing table
    lines.append("\n## Task Routing Compliance\n")
    tasks = list(routing.keys())
    header = "| Dataset | " + " | ".join(tasks) + " |"
    sep = "|---------|" + "|".join(["--------"] * len(tasks)) + "|"
    lines.append(header)
    lines.append(sep)
    for rec in contract:
        row = f"| {rec['dataset']} |"
        for t in tasks:
            status = rec["task_routing"].get(t, {}).get("status", "—")
            enabled = rec["task_routing"].get(t, {}).get("task_enabled", True)
            cell = status
            if status == "allowed" and not enabled:
                cell = "allowed (task disabled)"
            row += f" {cell} |"
        lines.append(row)

    # Per-task summary
    lines.append("\n## Per-Task Dataset Summary\n")
    for task_name, task_cfg in routing.items():
        allowed = task_cfg.get("allowed_datasets", [])
        enabled = task_cfg.get("enabled_for_training", True)
        reason = task_cfg.get("reason", "")
        lines.append(f"### {task_name}")
        lines.append(f"- **Enabled for training**: {enabled}")
        if not enabled and reason:
            lines.append(f"- **Reason disabled**: {reason}")
        lines.append(f"- **Primary modality**: {task_cfg.get('primary_modality', '—')}")
        lines.append(f"- **Allowed datasets**: {', '.join(allowed) if allowed else '—'}")
        available = [
            r["dataset"]
            for r in contract
            if r["task_routing"].get(task_name, {}).get("status") == "allowed"
            and r["raw_exists"]
        ]
        missing = [d for d in allowed if d not in [r["dataset"] for r in contract if r["raw_exists"]]]
        lines.append(f"- **Available (raw exists)**: {', '.join(available) if available else 'NONE'}")
        if missing:
            lines.append(f"- **Missing (raw absent)**: {', '.join(missing)}")
        lines.append("")

    # Label distribution section
    lines.append("## Window Shape & Label Distribution (where available)\n")
    for rec in contract:
        if rec.get("window_shape") or rec.get("label_distribution"):
            lines.append(f"### {rec['dataset']}")
            if rec.get("window_shape"):
                lines.append(f"- Window shape: `{rec['window_shape']}`")
            if rec.get("n_windows"):
                lines.append(f"- Total windows: {rec['n_windows']:,}")
            if rec.get("label_distribution"):
                lines.append(f"- Label distribution: `{rec['label_distribution']}`")
            if rec.get("split_counts"):
                lines.append(f"- Split counts: `{rec['split_counts']}`")
            lines.append("")

    # Blocking issues
    lines.append("## Blocking Issues\n")
    blocking: List[str] = []
    for task_name, task_cfg in routing.items():
        if not task_cfg.get("enabled_for_training", True):
            continue
        allowed = task_cfg.get("allowed_datasets", [])
        available = [
            r["dataset"]
            for r in contract
            if r["task_routing"].get(task_name, {}).get("status") == "allowed"
            and r["raw_exists"]
        ]
        if not available:
            blocking.append(
                f"- **{task_name}**: No allowed dataset has raw data present!"
            )

    if blocking:
        lines.extend(blocking)
    else:
        lines.append("No blocking issues detected. All enabled tasks have at least one available dataset.")

    lines.append("\n---\n")
    lines.append("_End of dataset contract report._")

    out_path = OUT_DIR / "dataset_contract_report.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    log.info(f"Markdown report written → {out_path}")
    return out_path


def main() -> None:
    log.info("=== HealthAlert Hybrid Dataset Contract Audit ===")
    log.info(f"ROOT: {ROOT}")

    if not ROUTING_CFG.exists():
        log.error(f"Routing config not found: {ROUTING_CFG}")
        sys.exit(1)

    with open(ROUTING_CFG, encoding="utf-8") as f:
        routing: Dict[str, Any] = yaml.safe_load(f)

    log.info(f"Tasks in routing config: {list(routing.keys())}")
    log.info("Scanning datasets …")
    contract = build_contract(routing)

    json_path = write_json(contract)
    md_path = write_markdown(contract, routing)

    # Print quick summary
    total = len(contract)
    with_raw = sum(1 for r in contract if r["raw_exists"])
    log.info("")
    log.info(f"  Total datasets audited : {total}")
    log.info(f"  Raw folder exists      : {with_raw}/{total}")
    log.info(f"  JSON  → {json_path}")
    log.info(f"  Report→ {md_path}")
    log.info("Audit complete.")


if __name__ == "__main__":
    main()
