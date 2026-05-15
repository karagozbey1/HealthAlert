"""Build multi-source windowed training dataset from all available datasets.

Usage:
    python scripts/build_multi_source_windowed_dataset.py [OPTIONS]

Options:
    --config                   Path to datasets.yaml (default: config/datasets.yaml)
    --window-sec               Window duration in seconds (default: 4)
    --stride-sec               Stride in seconds (default: 2)
    --target-rate              Target sample rate in Hz (default: 50)
    --output-dir               Output directory (default: outputs/windowed_dataset)
    --max-records-per-dataset  Limit records per dataset (for debugging)
    --dry-run                  Parse config and report availability without building
    --include-missing-report   Write missing_datasets_report.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("healthalert.build_dataset")

LABEL_TO_ID = {
    "normal": 0,
    "fall": 1,
    "near_fall": 2,
    "instability": 3,
    "walking": 10,
    "sitting": 11,
    "standing": 12,
    "lying": 13,
    "good_quality": 20,
    "bad_quality": 21,
    "unknown": 99,
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build multi-source windowed training dataset")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config" / "datasets.yaml"))
    parser.add_argument("--window-sec", type=int, default=4)
    parser.add_argument("--stride-sec", type=int, default=2)
    parser.add_argument("--target-rate", type=int, default=50)
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs" / "windowed_dataset"))
    parser.add_argument("--max-records-per-dataset", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-missing-report", action="store_true", default=True)
    return parser.parse_args()


def _resolve_path(local_path: str) -> str:
    """Resolve dataset local_path relative to project root."""
    p = Path(local_path)
    if p.is_absolute():
        return str(p)
    # Workspace root is one level up from PROJECT_ROOT (healthalert_final_ai/)
    workspace_root = PROJECT_ROOT.parent
    candidates = [
        PROJECT_ROOT / local_path,
        workspace_root / local_path,
        workspace_root / "Data" / p.name,
        PROJECT_ROOT / "Data" / p.name,
        PROJECT_ROOT / "data" / "raw" / p.name,
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return str(PROJECT_ROOT / local_path)


def _load_registry(config_path: str) -> Dict[str, Dict]:
    """Load and normalize datasets.yaml."""
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    datasets = raw.get("datasets", {})
    normalized: Dict[str, Dict] = {}
    for key, val in datasets.items():
        entry = dict(val or {})
        entry["_key"] = key
        entry.setdefault("name", key)
        lp = entry.get("local_path", "")
        # Resolve OmegaConf-style interpolation to literal paths
        if "${" in lp:
            name = entry.get("name", key).upper().replace("-", "_")
            lp = f"Data/{name}"
            entry["local_path"] = lp
        entry["local_path_resolved"] = _resolve_path(lp)
        entry["available"] = Path(entry["local_path_resolved"]).exists()
        normalized[key] = entry
    return normalized


def _build_feature_vector(
    window: Dict[str, Any],
    target_samples: int = 200,
    imu_channels: int = 6,
    ppg_channels: int = 1,
) -> np.ndarray:
    """Build a fixed-size feature vector from a window.

    Always produces (target_samples*imu_channels + target_samples*ppg_channels,)
    = (1200 + 200,) = 1400-element vector by default.
    Zero-pads missing modalities.
    """
    def _resample_to(arr: np.ndarray, n_out: int) -> np.ndarray:
        if arr.shape[0] == n_out:
            return arr
        x_old = np.linspace(0, 1, arr.shape[0])
        x_new = np.linspace(0, 1, n_out)
        out = np.stack(
            [np.interp(x_new, x_old, arr[:, c]) for c in range(arr.shape[1])],
            axis=1,
        ).astype(np.float32)
        return out

    # IMU part
    imu = window.get("imu")
    if imu is not None:
        imu_arr = _resample_to(np.asarray(imu, dtype=np.float32).reshape(-1, max(1, imu_channels)), target_samples)
        raw = np.asarray(imu, dtype=np.float32)
        if raw.ndim == 1:
            raw = raw.reshape(-1, 1)
        imu_arr = _resample_to(raw, target_samples)
        # Pad/truncate to imu_channels
        if imu_arr.shape[1] < imu_channels:
            pad = np.zeros((target_samples, imu_channels - imu_arr.shape[1]), dtype=np.float32)
            imu_arr = np.concatenate([imu_arr, pad], axis=1)
        imu_arr = imu_arr[:, :imu_channels]
    else:
        imu_arr = np.zeros((target_samples, imu_channels), dtype=np.float32)

    # PPG part
    ppg = window.get("ppg")
    if ppg is not None:
        raw = np.asarray(ppg, dtype=np.float32)
        if raw.ndim == 1:
            raw = raw.reshape(-1, 1)
        ppg_arr = _resample_to(raw, target_samples)
        if ppg_arr.shape[1] < ppg_channels:
            pad = np.zeros((target_samples, ppg_channels - ppg_arr.shape[1]), dtype=np.float32)
            ppg_arr = np.concatenate([ppg_arr, pad], axis=1)
        ppg_arr = ppg_arr[:, :ppg_channels]
    else:
        ppg_arr = np.zeros((target_samples, ppg_channels), dtype=np.float32)

    return np.concatenate([imu_arr.flatten(), ppg_arr.flatten()])


def _windows_to_npz(
    windows: List[Dict[str, Any]],
    target_samples: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert window list to (features, labels, imu_3d, ppg_3d, metadata_arr)."""
    features_list = []
    labels_list = []
    imu_list = []
    ppg_list = []
    meta_list = []

    for w in windows:
        feat = _build_feature_vector(w, target_samples)

        label_str = w.get("label", "unknown")
        label_id = LABEL_TO_ID.get(str(label_str), 99)

        imu = w.get("imu")
        ppg = w.get("ppg")

        # Canonical shapes: (target_samples, 6) for IMU, (target_samples, 1) for PPG
        if imu is not None:
            imu_arr = np.asarray(imu, dtype=np.float32)
            if imu_arr.shape[0] != target_samples:
                # pad or truncate
                pad = np.zeros((target_samples, imu_arr.shape[1]), dtype=np.float32)
                keep = min(target_samples, imu_arr.shape[0])
                pad[:keep] = imu_arr[:keep]
                imu_arr = pad
            # Pad to 6 columns
            if imu_arr.shape[1] < 6:
                pad_cols = np.zeros((target_samples, 6 - imu_arr.shape[1]), dtype=np.float32)
                imu_arr = np.concatenate([imu_arr, pad_cols], axis=1)
            imu_arr = imu_arr[:, :6]
        else:
            imu_arr = np.zeros((target_samples, 6), dtype=np.float32)

        if ppg is not None:
            ppg_arr = np.asarray(ppg, dtype=np.float32)
            if ppg_arr.shape[0] != target_samples:
                pad = np.zeros((target_samples, ppg_arr.shape[1] if ppg_arr.ndim > 1 else 1), dtype=np.float32)
                keep = min(target_samples, ppg_arr.shape[0])
                pad[:keep] = ppg_arr[:keep].reshape(keep, -1)
                ppg_arr = pad
            ppg_arr = ppg_arr[:, :1]
        else:
            ppg_arr = np.zeros((target_samples, 1), dtype=np.float32)

        meta = {
            "window_id": w.get("window_id", ""),
            "dataset_name": w.get("dataset_name", ""),
            "subject_id": w.get("subject_id", ""),
            "label": label_str,
            "quality_score": w.get("quality_score", 1.0),
            "has_imu": w.get("has_imu", False),
            "has_ppg": w.get("has_ppg", False),
        }

        features_list.append(feat)
        labels_list.append(label_id)
        imu_list.append(imu_arr)
        ppg_list.append(ppg_arr)
        meta_list.append(json.dumps(meta))

    if not features_list:
        empty_feat = np.zeros((0, 0), dtype=np.float32)
        empty_lbl = np.zeros((0,), dtype=np.int64)
        empty_imu = np.zeros((0, target_samples, 6), dtype=np.float32)
        empty_ppg = np.zeros((0, target_samples, 1), dtype=np.float32)
        empty_meta = np.array([], dtype=object)
        return empty_feat, empty_lbl, empty_imu, empty_ppg, empty_meta

    features = np.stack(features_list, axis=0).astype(np.float32)
    labels = np.array(labels_list, dtype=np.int64)
    imu_3d = np.stack(imu_list, axis=0).astype(np.float32)
    ppg_3d = np.stack(ppg_list, axis=0).astype(np.float32)
    metadata_arr = np.array(meta_list, dtype=object)

    return features, labels, imu_3d, ppg_3d, metadata_arr


def build_multi_source_windowed_dataset(
    config_path: str,
    window_sec: int = 4,
    stride_sec: int = 2,
    target_rate: int = 50,
    output_dir: str = "outputs/windowed_dataset",
    max_records_per_dataset: Optional[int] = None,
    dry_run: bool = False,
    include_missing_report: bool = True,
) -> Dict[str, Any]:
    """Main pipeline: load → window → split → export."""
    from src.data.loader_registry import load_dataset_by_name
    from src.data.windowing import build_standard_windows
    from src.data.splitting import subject_aware_split

    target_samples = window_sec * target_rate  # 4 * 50 = 200

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    registry = _load_registry(config_path)

    all_windows: List[Dict[str, Any]] = []
    available_datasets: List[str] = []
    missing_datasets: List[Dict] = []
    load_stats: Dict[str, Dict] = {}

    # ── Load each dataset ─────────────────────────────────────────────────────
    for key, cfg in registry.items():
        ds_name = cfg.get("name", key)
        resolved_path = cfg["local_path_resolved"]
        is_available = cfg["available"]
        access_status = cfg.get("access", {}).get("status", "unknown") if isinstance(cfg.get("access"), dict) else "unknown"

        if not is_available:
            logger.info("MISSING  %s  (path: %s)", ds_name, resolved_path)
            missing_datasets.append({
                "name": ds_name,
                "key": key,
                "path": resolved_path,
                "access_status": access_status,
                "access_url": cfg.get("access", {}).get("url", "") if isinstance(cfg.get("access"), dict) else "",
                "license_note": cfg.get("license_note", ""),
            })
            load_stats[key] = {"status": "missing", "n_records": 0, "n_windows": 0}
            continue

        logger.info("Loading  %s  from %s", ds_name, resolved_path)
        cfg_copy = dict(cfg)
        cfg_copy["local_path"] = resolved_path

        load_result = load_dataset_by_name(cfg_copy)
        load_stats[key] = {
            "status": load_result.status,
            "n_records": load_result.n_records,
            "errors": load_result.errors[:5],
            "n_windows": 0,
        }

        if load_result.status in ("missing", "error") or not load_result.records:
            logger.warning("Dataset %s: %s", ds_name, load_result.status)
            if load_result.errors:
                logger.warning("  Errors: %s", load_result.errors[:3])
            continue

        available_datasets.append(ds_name)

        records = load_result.records
        if max_records_per_dataset:
            records = records[:max_records_per_dataset]

        dataset_windows: List[Dict[str, Any]] = []
        for rec in records:
            try:
                wins = build_standard_windows(
                    rec, config=cfg_copy,
                    window_sec=window_sec, stride_sec=stride_sec,
                    target_rate_hz=target_rate, target_sample_count=target_samples,
                )
                dataset_windows.extend(wins)
            except Exception as exc:
                logger.warning("  build_standard_windows failed for %s/%s: %s", ds_name, rec.recording_id, exc)

        load_stats[key]["n_windows"] = len(dataset_windows)
        logger.info("  → %d records → %d windows", len(records), len(dataset_windows))
        all_windows.extend(dataset_windows)

    logger.info("Total windows from all datasets: %d", len(all_windows))

    if dry_run:
        logger.info("DRY RUN complete. No files written.")
        return {
            "dry_run": True,
            "available_datasets": available_datasets,
            "missing_datasets": missing_datasets,
            "load_stats": load_stats,
            "total_windows": len(all_windows),
        }

    if not all_windows:
        logger.error("BLOCKED_BY_DATASET – no windows available to export.")
        result = {
            "status": "BLOCKED_BY_DATASET",
            "available_datasets": available_datasets,
            "missing_datasets": missing_datasets,
            "load_stats": load_stats,
            "total_windows": 0,
        }
        (out_dir / "dataset_summary.json").write_text(json.dumps(result, indent=2))
        return result

    # ── Filter training candidates ────────────────────────────────────────────
    training_windows = [w for w in all_windows if w.get("training_candidate", True)]
    rejected_windows = [w for w in all_windows if not w.get("training_candidate", True)]
    logger.info("Training candidates: %d / Rejected: %d", len(training_windows), len(rejected_windows))

    # ── Subject-aware split ───────────────────────────────────────────────────
    train_wins, val_wins, test_wins = subject_aware_split(
        training_windows, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15
    )
    logger.info("Split → train=%d val=%d test=%d", len(train_wins), len(val_wins), len(test_wins))

    # ── Export NPZ ────────────────────────────────────────────────────────────
    split_files = {}
    for split_name, split_windows in [("train", train_wins), ("val", val_wins), ("test", test_wins)]:
        feat, lbl, imu, ppg, meta = _windows_to_npz(split_windows, target_samples)
        npz_path = out_dir / f"{split_name}.npz"
        np.savez_compressed(str(npz_path), features=feat, labels=lbl, imu=imu, ppg=ppg, metadata=meta)
        split_files[split_name] = str(npz_path)
        logger.info("Saved %s.npz: features=%s labels=%s", split_name, feat.shape, lbl.shape)

    # ── Distribution reports ──────────────────────────────────────────────────
    label_counts: Counter = Counter()
    modality_counts: Dict[str, int] = {"imu_only": 0, "ppg_only": 0, "both": 0, "neither": 0}
    quality_scores = []

    for w in training_windows:
        label_counts[w.get("label", "unknown")] += 1
        has_imu = w.get("has_imu", False)
        has_ppg = w.get("has_ppg", False)
        if has_imu and has_ppg:
            modality_counts["both"] += 1
        elif has_imu:
            modality_counts["imu_only"] += 1
        elif has_ppg:
            modality_counts["ppg_only"] += 1
        else:
            modality_counts["neither"] += 1
        quality_scores.append(float(w.get("quality_score", 1.0)))

    # Rejection breakdown
    reject_reasons: Counter = Counter()
    for w in rejected_windows:
        for flag in w.get("quality_flags", ["unknown_rejection"]):
            reject_reasons[flag] += 1

    label_dist = dict(label_counts)
    modality_dist = dict(modality_counts)
    quality_report = {
        "total_windows": len(all_windows),
        "training_candidates": len(training_windows),
        "rejected": len(rejected_windows),
        "rejection_reasons": dict(reject_reasons),
        "mean_quality_score": float(np.mean(quality_scores)) if quality_scores else 0.0,
        "min_quality_score": float(np.min(quality_scores)) if quality_scores else 0.0,
        "n_windows_below_0_5": int(sum(1 for q in quality_scores if q < 0.5)),
    }

    summary = {
        "status": "ok",
        "available_datasets": available_datasets,
        "n_available": len(available_datasets),
        "n_missing": len(missing_datasets),
        "total_windows": len(all_windows),
        "training_candidates": len(training_windows),
        "split": {
            "train": len(train_wins),
            "val": len(val_wins),
            "test": len(test_wins),
        },
        "output_files": split_files,
        "load_stats": load_stats,
        "window_sec": window_sec,
        "stride_sec": stride_sec,
        "target_rate_hz": target_rate,
        "target_sample_count": target_samples,
    }

    (out_dir / "dataset_summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "label_distribution.json").write_text(json.dumps(label_dist, indent=2))
    (out_dir / "modality_distribution.json").write_text(json.dumps(modality_dist, indent=2))
    (out_dir / "quality_report.json").write_text(json.dumps(quality_report, indent=2))

    # ── Task-specific exports ─────────────────────────────────────────────────
    task_summary = _export_task_specific_splits(
        train_wins=train_wins,
        val_wins=val_wins,
        test_wins=test_wins,
        out_dir=out_dir,
        target_samples=target_samples,
        load_stats=load_stats,
    )
    summary["task_specific"] = task_summary
    (out_dir / "task_specific_summary.json").write_text(json.dumps(task_summary, indent=2))
    logger.info("Task-specific summary written to %s", out_dir / "task_specific_summary.json")

    # ── Missing dataset report (Markdown) ────────────────────────────────────
    if include_missing_report:
        _write_missing_report(out_dir / "missing_datasets_report.md", missing_datasets, available_datasets)

    logger.info("Dataset build COMPLETE. Output: %s", out_dir)
    return summary


def _export_task_specific_splits(
    train_wins: List[Dict[str, Any]],
    val_wins: List[Dict[str, Any]],
    test_wins: List[Dict[str, Any]],
    out_dir: Path,
    target_samples: int,
    load_stats: Dict[str, Dict],
) -> Dict[str, Any]:
    """Export per-task NPZ files and generate task_specific_summary.json.

    Task routing rules:
    - fall_detection:   window["valid_tasks"] contains "fall_detection"
                        AND label != "unknown" AND label_id != 99
    - ppg_quality:      window["valid_tasks"] contains "ppg_quality"
    - vitals_context:   window["valid_tasks"] contains "vitals_context"
    - activity_context: window["valid_tasks"] contains "activity_context"
    - gait_instability: window["valid_tasks"] contains "gait_instability"
                        OR "freezing_of_gait"
    - tremor_context:   window["valid_tasks"] contains "tremor_context"

    Safety checks (enforced hard):
    - fall_detection export: label_id must never be 99
    - fall_detection export: must not include PPG/vitals-only datasets
    - fall_detection export: must not include gait/tremor-only datasets
    """
    # Datasets that must NEVER contribute to fall_detection
    FALL_DETECTION_EXCLUDED_DATASETS = {
        "BIDMC-PPG-Respiration", "BIDMC", "BUT_PPG",
        "PPG-DaLiA", "WESAD", "WildPPG",
        "Daphnet-FoG", "Hand-Tremor-MPU9250",
        "PADS-Smartwatch-PD", "SisFall",
    }

    TASK_DEFINITIONS = {
        "fall_detection": lambda w: (
            "fall_detection" in (w.get("valid_tasks") or [])
            and w.get("label", "unknown") not in ("unknown",)
            and LABEL_TO_ID.get(w.get("label", "unknown"), 99) != 99
            and w.get("dataset_name", "") not in FALL_DETECTION_EXCLUDED_DATASETS
        ),
        "ppg_quality": lambda w: "ppg_quality" in (w.get("valid_tasks") or []),
        "vitals_context": lambda w: "vitals_context" in (w.get("valid_tasks") or []),
        "activity_context": lambda w: "activity_context" in (w.get("valid_tasks") or []),
        "gait_instability": lambda w: (
            "gait_instability" in (w.get("valid_tasks") or [])
            or "freezing_of_gait" in (w.get("valid_tasks") or [])
        ),
        "tremor_context": lambda w: "tremor_context" in (w.get("valid_tasks") or []),
    }

    task_summary: Dict[str, Any] = {}

    for task_name, filter_fn in TASK_DEFINITIONS.items():
        task_dir = out_dir / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        t_wins = [w for w in train_wins if filter_fn(w)]
        v_wins = [w for w in val_wins if filter_fn(w)]
        te_wins = [w for w in test_wins if filter_fn(w)]

        total = len(t_wins) + len(v_wins) + len(te_wins)

        # Per-dataset contribution
        dataset_contrib: Counter = Counter()
        label_dist: Counter = Counter()
        modality_dist: Dict[str, int] = {"imu_only": 0, "ppg_only": 0, "both": 0, "neither": 0}

        for w in t_wins + v_wins + te_wins:
            dataset_contrib[w.get("dataset_name", "unknown")] += 1
            label_dist[w.get("label", "unknown")] += 1
            has_imu = w.get("has_imu", False)
            has_ppg = w.get("has_ppg", False)
            if has_imu and has_ppg:
                modality_dist["both"] += 1
            elif has_imu:
                modality_dist["imu_only"] += 1
            elif has_ppg:
                modality_dist["ppg_only"] += 1
            else:
                modality_dist["neither"] += 1

        # Safety check for fall_detection
        safety = {}
        if task_name == "fall_detection":
            label_99_count = sum(
                1 for w in t_wins + v_wins + te_wins
                if LABEL_TO_ID.get(w.get("label", "unknown"), 99) == 99
            )
            ppg_vitals_contamination = sum(
                1 for w in t_wins + v_wins + te_wins
                if w.get("dataset_name", "") in FALL_DETECTION_EXCLUDED_DATASETS
            )
            safety["label_99_count"] = label_99_count
            safety["ppg_vitals_contamination_count"] = ppg_vitals_contamination
            safety["PASS"] = (label_99_count == 0 and ppg_vitals_contamination == 0)
            if label_99_count > 0:
                logger.error(
                    "SAFETY VIOLATION: fall_detection has %d windows with label_id=99!",
                    label_99_count,
                )
            if ppg_vitals_contamination > 0:
                logger.error(
                    "SAFETY VIOLATION: fall_detection has %d windows from excluded datasets!",
                    ppg_vitals_contamination,
                )

        # Export NPZ files (skip if no windows — don't write empty files)
        export_files: Dict[str, str] = {}
        for split_name, split_wins in [("train", t_wins), ("val", v_wins), ("test", te_wins)]:
            if split_wins:
                feat, lbl, imu, ppg, meta = _windows_to_npz(split_wins, target_samples)
                npz_path = task_dir / f"{split_name}.npz"
                np.savez_compressed(str(npz_path), features=feat, labels=lbl, imu=imu, ppg=ppg, metadata=meta)
                export_files[split_name] = str(npz_path)

        task_info: Dict[str, Any] = {
            "total": total,
            "train": len(t_wins),
            "val": len(v_wins),
            "test": len(te_wins),
            "dataset_contributions": dict(dataset_contrib),
            "label_distribution": dict(label_dist),
            "modality_distribution": modality_dist,
            "export_files": export_files,
        }
        if safety:
            task_info["safety_check"] = safety

        task_summary[task_name] = task_info
        (task_dir / "summary.json").write_text(json.dumps(task_info, indent=2))
        logger.info(
            "Task %-20s: total=%d  train=%d  val=%d  test=%d",
            task_name, total, len(t_wins), len(v_wins), len(te_wins),
        )

    return task_summary


def _write_missing_report(path: Path, missing: List[Dict], available: List[str]) -> None:
    lines = [
        "# HealthAlert – Missing Datasets Report",
        "",
        f"**Available datasets:** {', '.join(available) if available else 'none'}",
        "",
        f"**Missing/not-yet-downloaded datasets ({len(missing)}):**",
        "",
        "| Dataset | Access Type | Download URL | License |",
        "|---------|-------------|--------------|---------|",
    ]
    for d in missing:
        lines.append(
            f"| {d['name']} | {d['access_status']} | {d['access_url']} | {d['license_note']} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- Datasets marked `manual_required` must be downloaded manually and placed under `data/raw/<dataset_name>/`.",
        "- Datasets marked `request_required` need institutional access request (e.g. MobiAct via TEICRETE).",
        "- PhysioNet datasets can be fetched with: `wget -r -N -c -np <url>`",
        "",
        "*This report was auto-generated by `build_multi_source_windowed_dataset.py`.*",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    args = _parse_args()
    result = build_multi_source_windowed_dataset(
        config_path=args.config,
        window_sec=args.window_sec,
        stride_sec=args.stride_sec,
        target_rate=args.target_rate,
        output_dir=args.output_dir,
        max_records_per_dataset=args.max_records_per_dataset,
        dry_run=args.dry_run,
        include_missing_report=args.include_missing_report,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "load_stats"}, indent=2))
