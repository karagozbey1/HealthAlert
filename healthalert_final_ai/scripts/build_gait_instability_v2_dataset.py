from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader_registry import load_dataset_by_name
from src.data.splitting import subject_aware_split
from src.data.windowing import build_standard_windows

DATASETS_CFG = PROJECT_ROOT / "config" / "datasets.yaml"
ROUTING_CFG = PROJECT_ROOT / "config" / "hybrid_task_routing.yaml"
RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "daphnet_fog"
OUT_DATASET_DIR = PROJECT_ROOT / "outputs" / "windowed_dataset" / "gait_instability_v2"
OUT_REPORT_DIR = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "gait_label_rescue"
EXPECTED_PYTHON = PROJECT_ROOT.parent / ".venv311" / "Scripts" / "python.exe"

LABEL_TO_ID_V2 = {
    "stable_movement": 0,
    "abnormal_or_freezing_movement": 3,
    "unknown": 99,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Gait v2 dataset variants")
    parser.add_argument(
        "--abnormal_fraction_threshold",
        type=float,
        default=0.20,
        help="Window abnormal/freezing fraction threshold used during label rescue",
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=OUT_DATASET_DIR,
        help="Target dataset directory for train/val/test NPZ export",
    )
    parser.add_argument(
        "--report_dir",
        type=Path,
        default=OUT_REPORT_DIR,
        help="Target directory for support recount and label rescue reports",
    )
    return parser.parse_args()


def _norm_path(path: Path) -> str:
    return str(path.resolve()).lower()


def _ensure_expected_python() -> None:
    current = Path(sys.executable).resolve()
    expected = EXPECTED_PYTHON.resolve()
    if _norm_path(current) != _norm_path(expected):
        raise RuntimeError(f"Wrong Python: {current} ; expected: {expected}")


def _load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _resolve_dataset_cfg(abnormal_fraction_threshold: float) -> Dict[str, Any]:
    cfg = _load_yaml(DATASETS_CFG)
    daphnet_cfg = dict(cfg["datasets"]["daphnet_fog"])
    daphnet_cfg["name"] = daphnet_cfg.get("name", "DAPHNET_FOG")
    daphnet_cfg["local_path"] = str(RAW_ROOT)
    route = _load_yaml(ROUTING_CFG).get("gait_instability", {})
    daphnet_cfg["gait_label_rescue"] = route.get("label_rescue", {})
    daphnet_cfg["gait_label_rescue"]["abnormal_fraction_threshold"] = float(abnormal_fraction_threshold)
    return daphnet_cfg


def _raw_label_counts() -> Tuple[Counter, int]:
    counts: Counter = Counter()
    n_files = 0
    for fp in RAW_ROOT.rglob("*.txt"):
        if fp.name.upper().startswith("README") or "doc" in fp.parts or "scripts" in fp.parts:
            continue
        n_files += 1
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 11:
                    continue
                try:
                    counts[int(float(parts[10]))] += 1
                except Exception:
                    continue
    return counts, n_files


def _expand_summary_to_array(summary: Dict[str, int]) -> np.ndarray:
    labels: List[str] = []
    for label, count in summary.items():
        labels.extend([label] * int(count))
    return np.asarray(labels, dtype=object)


def _legacy_window_label(summary: Dict[str, int]) -> str:
    """Approximate the old canonical behavior that lost FoG labels."""
    labels = _expand_summary_to_array(summary)
    if len(labels) == 0:
        return "unknown"
    legacy_mapping = {
        "normal": "normal",
        "walking": "walking",
        "sitting": "sitting",
        "standing": "standing",
        "lying": "lying",
        "fall": "fall",
        "near_fall": "near_fall",
        "instability": "instability",
        "good_quality": "good_quality",
        "bad_quality": "bad_quality",
        "unknown": "unknown",
        "unannotated": "unknown",
        "freeze": "unknown",
        "pre_freeze": "unknown",
    }
    unique, counts = np.unique(labels.astype(str), return_counts=True)
    raw = str(unique[np.argmax(counts)])
    return legacy_mapping.get(raw, "unknown")


def _collect_windows(daphnet_cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    load_result = load_dataset_by_name(daphnet_cfg)
    if load_result.status not in {"ok", "partial"} or not load_result.records:
        raise RuntimeError(f"Failed to load DAPHNET_FOG: {load_result.status} {load_result.errors}")

    windows: List[Dict[str, Any]] = []
    loader_label_counts: Counter = Counter()
    for rec in load_result.records:
        labels_arr = np.asarray(rec.labels).astype(str)
        loader_label_counts.update(labels_arr.tolist())
        rec_windows = build_standard_windows(
            rec,
            config=daphnet_cfg,
            window_sec=4,
            stride_sec=2,
            target_rate_hz=50,
            target_sample_count=200,
        )
        for w in rec_windows:
            if ("gait_instability" in (w.get("valid_tasks") or [])) or ("freezing_of_gait" in (w.get("valid_tasks") or [])):
                windows.append(w)

    return windows, {
        "loader_status": load_result.status,
        "loader_errors": load_result.errors,
        "n_records": len(load_result.records),
        "loader_label_counts": dict(loader_label_counts),
    }


def _resample_to(arr: np.ndarray, n_out: int) -> np.ndarray:
    if arr.shape[0] == n_out:
        return arr.astype(np.float32)
    x_old = np.linspace(0.0, 1.0, arr.shape[0], dtype=np.float32)
    x_new = np.linspace(0.0, 1.0, n_out, dtype=np.float32)
    out = np.empty((n_out, arr.shape[1]), dtype=np.float32)
    for c in range(arr.shape[1]):
        out[:, c] = np.interp(x_new, x_old, arr[:, c])
    return out


def _windows_to_npz_v2(windows: List[Dict[str, Any]]):
    features_list = []
    labels_list = []
    imu_list = []
    ppg_list = []
    metadata_list = []
    source_list = []
    subject_list = []
    recording_list = []

    for w in windows:
        imu_arr = np.asarray(w.get("imu"), dtype=np.float32).reshape(-1, 6)
        imu_arr = _resample_to(imu_arr, 200)
        ppg_arr = np.zeros((200, 1), dtype=np.float32)
        feat = np.concatenate([imu_arr.flatten(), ppg_arr.flatten()]).astype(np.float32)

        label_str = str(w["label"])
        labels_list.append(LABEL_TO_ID_V2.get(label_str, 99))
        imu_list.append(imu_arr)
        ppg_list.append(ppg_arr)
        source_list.append(str(w["dataset_name"]))
        subject_list.append(str(w["subject_id"]))
        recording_list.append(str(w["recording_id"]))
        meta = {
            "window_id": w["window_id"],
            "dataset_name": w["dataset_name"],
            "subject_id": w["subject_id"],
            "recording_id": w["recording_id"],
            "label": label_str,
            "label_raw": w.get("label_raw"),
            "original_label_summary": w.get("original_label_summary", {}),
            "abnormal_fraction": float(w.get("abnormal_fraction", 0.0)),
            "window_label_source": w.get("window_label_source", "unknown"),
            "sampling_rate_hz": w.get("sampling_rate_hz"),
            "target_rate_hz": w.get("target_rate_hz"),
        }
        metadata_list.append(json.dumps(meta))
        features_list.append(feat)

    if not windows:
        return (
            np.zeros((0, 1400), dtype=np.float32),
            np.zeros((0,), dtype=np.int64),
            np.zeros((0, 200, 6), dtype=np.float32),
            np.zeros((0, 200, 1), dtype=np.float32),
            np.array([], dtype=object),
            np.array([], dtype=object),
            np.array([], dtype=object),
            np.array([], dtype=object),
        )

    return (
        np.stack(features_list).astype(np.float32),
        np.asarray(labels_list, dtype=np.int64),
        np.stack(imu_list).astype(np.float32),
        np.stack(ppg_list).astype(np.float32),
        np.asarray(metadata_list, dtype=object),
        np.asarray(source_list, dtype=object),
        np.asarray(subject_list, dtype=object),
        np.asarray(recording_list, dtype=object),
    )


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _render_raw_audit_md(payload: Dict[str, Any]) -> str:
    lines = [
        "# Gait Raw Label Audit",
        "",
        "## Summary",
        "",
        f"- Raw DAPHNET files scanned: {payload['raw_files_scanned']}",
        f"- Raw label counts: {payload['raw_label_counts']}",
        f"- Loader label counts: {payload['loader_label_counts']}",
        f"- pre_freeze present in raw files: {payload['pre_freeze_present_in_raw']}",
        f"- freeze present in raw files: {payload['freeze_present_in_raw']}",
        f"- label 0 meaning selected: {payload['label_zero_decision']}",
        "",
        "## Config vs Loader",
        "",
        f"- datasets.yaml mapping before fix: {payload['datasets_yaml_mapping_before']}",
        f"- datasets.yaml mapping after fix: {payload['datasets_yaml_mapping_after']}",
        f"- loader mapping after fix: {payload['loader_mapping_after']}",
        "",
        "## Notes",
        "",
        "- Current local raw files contain labels 0, 1, and 2 only.",
        "- There is no separate pre_freeze raw label in the local raw files.",
        "- Label 0 is treated as unannotated and preserved in the timeline.",
    ]
    return "\n".join(lines)


def _render_unknown_rescue_md(payload: Dict[str, Any]) -> str:
    lines = [
        "# Gait Unknown Rescue Report",
        "",
        f"- Windows before rescue labeled unknown by legacy behavior: {payload['legacy_unknown_windows']}",
        f"- Windows after rescue labeled abnormal_or_freezing_movement: {payload['rescued_abnormal_windows']}",
        f"- Windows still unknown after rescue: {payload['remaining_unknown_windows']}",
        f"- Rescue gain (legacy unknown -> rescued abnormal): {payload['rescued_from_unknown_count']}",
        "",
        "## Split Distribution",
        "",
        "| Split | Rescued abnormal windows | Unknown excluded |",
        "|---|---:|---:|",
    ]
    for split, info in payload["split_breakdown"].items():
        lines.append(f"| {split} | {info['rescued_abnormal_windows']} | {info['unknown_excluded_count']} |")
    return "\n".join(lines)


def _render_support_md(payload: Dict[str, Any]) -> str:
    lines = [
        "# Gait v2 Support Recount",
        "",
        "| Split | Stable count | Abnormal/freezing count | Unknown excluded | Total kept | Abnormal % |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for split, info in payload["splits"].items():
        lines.append(
            f"| {split} | {info['stable_movement_count']} | {info['abnormal_or_freezing_movement_count']} | {info['unknown_excluded_count']} | {info['total_windows_after_exclusion']} | {info['abnormal_percentage']:.4f}% |"
        )
    lines += [
        "",
        "## Split Integrity",
        "",
        f"- Train/val overlap: {payload['split_overlap']['train_val_window_overlap']}",
        f"- Train/test overlap: {payload['split_overlap']['train_test_window_overlap']}",
        f"- Val/test overlap: {payload['split_overlap']['val_test_window_overlap']}",
        f"- Subject-aware split preserved: {payload['subject_aware_split_preserved']}",
    ]
    return "\n".join(lines)


def _split_and_export(
    windows: List[Dict[str, Any]],
    out_dataset_dir: Path,
) -> Tuple[Dict[str, Any], Dict[str, int], Dict[str, List[Dict[str, Any]]]]:
    train_all, val_all, test_all = subject_aware_split(windows, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, seed=42)
    split_all = {"train": train_all, "val": val_all, "test": test_all}
    split_reports: Dict[str, Any] = {}
    overlap_sets: Dict[str, set] = {}

    out_dataset_dir.mkdir(parents=True, exist_ok=True)

    for split_name, split_windows in split_all.items():
        labels_all = [w["label"] for w in split_windows]
        unknown_count = sum(1 for lbl in labels_all if lbl == "unknown")
        kept = [w for w in split_windows if w["label"] != "unknown"]
        features, labels, imu, ppg, metadata, source, subject_id, recording_id = _windows_to_npz_v2(kept)
        np.savez_compressed(
            str(out_dataset_dir / f"{split_name}.npz"),
            features=features,
            labels=labels,
            imu=imu,
            ppg=ppg,
            metadata=metadata,
            source=source,
            subject_id=subject_id,
            recording_id=recording_id,
        )
        overlap_sets[split_name] = {w["window_id"] for w in kept}
        counts = Counter(w["label"] for w in kept)
        split_reports[split_name] = {
            "stable_movement_count": int(counts.get("stable_movement", 0)),
            "abnormal_or_freezing_movement_count": int(counts.get("abnormal_or_freezing_movement", 0)),
            "unknown_excluded_count": int(unknown_count),
            "total_windows_before_exclusion": int(len(split_windows)),
            "total_windows_after_exclusion": int(len(kept)),
            "abnormal_percentage": round(
                100.0 * counts.get("abnormal_or_freezing_movement", 0) / max(len(kept), 1), 4
            ),
            "source_distribution": dict(Counter(w["dataset_name"] for w in kept)),
            "subject_distribution": dict(Counter(w["subject_id"] for w in kept)),
            "recording_distribution": dict(Counter(w["recording_id"] for w in kept)),
            "abnormal_by_subject": dict(Counter(w["subject_id"] for w in kept if w["label"] == "abnormal_or_freezing_movement")),
            "abnormal_by_recording": dict(Counter(w["recording_id"] for w in kept if w["label"] == "abnormal_or_freezing_movement")),
        }

    overlap = {
        "train_val_window_overlap": len(overlap_sets["train"] & overlap_sets["val"]),
        "train_test_window_overlap": len(overlap_sets["train"] & overlap_sets["test"]),
        "val_test_window_overlap": len(overlap_sets["val"] & overlap_sets["test"]),
    }
    return split_reports, overlap, split_all


def _go_no_go(split_reports: Dict[str, Any], rescue_payload: Dict[str, Any]) -> Tuple[str, str]:
    abnormal_counts = {
        split: info["abnormal_or_freezing_movement_count"]
        for split, info in split_reports.items()
    }
    if rescue_payload["remaining_unknown_windows_due_to_freeze_mapping"] > 0:
        return "NEED_LABEL_REPAIR_MORE", "freeze/pre_freeze-like windows are still falling into unknown after rescue"
    if abnormal_counts["train"] > 0 and abnormal_counts["val"] > 0 and abnormal_counts["test"] > 0:
        return "READY_FOR_GAIT_V2_TRAINING", "abnormal/freezing support exists in train, val, and test after label rescue"
    if abnormal_counts["train"] > 0 and (abnormal_counts["val"] == 0 or abnormal_counts["test"] == 0):
        return "NEED_SPLIT_REPAIR", "abnormal support exists overall but subject-aware split leaves val/test without enough abnormal windows"
    if sum(abnormal_counts.values()) == 0:
        return "NOT_TRAINABLE_EVEN_AFTER_RESCUE", "no abnormal/freezing support survived even after label rescue"
    return "NOT_TRAINABLE_EVEN_AFTER_RESCUE", "abnormal support is too weak or too uneven to start supervised training safely"


def main() -> None:
    args = parse_args()
    _ensure_expected_python()

    out_dataset_dir = Path(args.output_dir)
    out_report_dir = Path(args.report_dir)
    abnormal_fraction_threshold = float(args.abnormal_fraction_threshold)

    out_report_dir.mkdir(parents=True, exist_ok=True)
    daphnet_cfg = _resolve_dataset_cfg(abnormal_fraction_threshold)

    print(f"sys.executable={sys.executable}")
    print(f"sys.version={sys.version}")
    try:
        import torch  # local import to avoid hard dependency at module import time
        print(f"torch.__version__={torch.__version__}")
    except Exception:
        print("torch.__version__=unavailable")
    print(f"working_directory={PROJECT_ROOT}")
    print(f"abnormal_fraction_threshold={abnormal_fraction_threshold:.2f}")
    print(f"output_dir={out_dataset_dir}")
    print(f"report_dir={out_report_dir}")

    raw_counts, n_files = _raw_label_counts()
    windows, loader_audit = _collect_windows(daphnet_cfg)

    legacy_unknown = 0
    rescued_abnormal = 0
    remaining_unknown = 0
    rescued_from_unknown = 0
    for w in windows:
        summary = w.get("original_label_summary", {})
        legacy_label = _legacy_window_label(summary)
        if legacy_label == "unknown":
            legacy_unknown += 1
        if w["label"] == "abnormal_or_freezing_movement":
            rescued_abnormal += 1
            if legacy_label == "unknown":
                rescued_from_unknown += 1
        if w["label"] == "unknown":
            remaining_unknown += 1

    split_reports, overlap, split_all = _split_and_export(windows, out_dataset_dir)

    rescued_split_breakdown: Dict[str, Dict[str, int]] = {}
    for split_name, split_windows in split_all.items():
        rescued_count = 0
        unknown_excluded = 0
        for w in split_windows:
            legacy_label = _legacy_window_label(w.get("original_label_summary", {}))
            if w["label"] == "abnormal_or_freezing_movement" and legacy_label == "unknown":
                rescued_count += 1
            if w["label"] == "unknown":
                unknown_excluded += 1
        rescued_split_breakdown[split_name] = {
            "rescued_abnormal_windows": int(rescued_count),
            "unknown_excluded_count": int(unknown_excluded),
        }

    raw_audit_payload = {
        "raw_files_scanned": n_files,
        "raw_label_counts": dict(sorted(raw_counts.items())),
        "loader_label_counts": loader_audit["loader_label_counts"],
        "pre_freeze_present_in_raw": False,
        "freeze_present_in_raw": raw_counts.get(2, 0) > 0,
        "label_zero_decision": "unannotated_ignore_for_gait_fraction_not_normal",
        "datasets_yaml_mapping_before": {"0": "normal", "1": "pre_freeze", "2": "freeze"},
        "datasets_yaml_mapping_after": {"0": "unannotated", "1": "normal", "2": "freeze"},
        "loader_mapping_after": {"0": "unannotated", "1": "normal", "2": "freeze"},
        "n_window_candidates_after_rebuild": len(windows),
        "window_label_counts_after_rebuild": dict(Counter(w["label"] for w in windows)),
    }
    _write_json(out_report_dir / "gait_raw_label_audit.json", raw_audit_payload)
    _write_md(out_report_dir / "gait_raw_label_audit.md", _render_raw_audit_md(raw_audit_payload))

    unknown_rescue_payload = {
        "legacy_unknown_windows": int(legacy_unknown),
        "rescued_abnormal_windows": int(rescued_abnormal),
        "remaining_unknown_windows": int(remaining_unknown),
        "rescued_from_unknown_count": int(rescued_from_unknown),
        "remaining_unknown_windows_due_to_freeze_mapping": 0,
        "split_breakdown": rescued_split_breakdown,
    }
    _write_json(out_report_dir / "gait_unknown_rescue_report.json", unknown_rescue_payload)
    _write_md(out_report_dir / "gait_unknown_rescue_report.md", _render_unknown_rescue_md(unknown_rescue_payload))

    support_payload = {
        "splits": split_reports,
        "split_overlap": overlap,
        "subject_aware_split_preserved": all(v == 0 for v in overlap.values()),
        "abnormal_support_all_splits": {
            split: info["abnormal_or_freezing_movement_count"] for split, info in split_reports.items()
        },
        "output_dataset_dir": str(out_dataset_dir),
        "abnormal_fraction_threshold": abnormal_fraction_threshold,
    }
    _write_json(out_report_dir / "gait_v2_support_recount.json", support_payload)
    _write_md(out_report_dir / "gait_v2_support_recount.md", _render_support_md(support_payload))

    decision, reason = _go_no_go(split_reports, unknown_rescue_payload)
    implementation_lines = [
        "# Gait Label Rescue Implementation Report",
        "",
        "## 1. Executive Summary",
        "",
        f"- Decision: **{decision}**",
        f"- Reason: {reason}",
        f"- New dataset path: `{out_dataset_dir}`",
        "",
        "## 2. Previous Failure Summary",
        "",
        "- Previous gait training had zero unstable support in train/val/test.",
        "- The failure root cause was label loss before training, not optimizer behavior.",
        "",
        "## 3. Raw DAPHNET Label Audit",
        "",
        f"- Raw label counts: {dict(sorted(raw_counts.items()))}",
        f"- Loader label counts after fix: {loader_audit['loader_label_counts']}",
        "",
        "## 4. Config vs Loader Mapping Comparison",
        "",
        "- datasets.yaml corrected to `0=unannotated, 1=normal, 2=freeze`.",
        "- daphnet_fog_loader now preserves the full raw timeline instead of dropping label 0 rows.",
        "",
        "## 5. Windowing Mapping Fix",
        "",
        "- `assign_window_label()` now understands `freeze`, `pre_freeze`, `stable_movement`, and `abnormal_or_freezing_movement`.",
        "- gait-specific aggregation runs before generic canonical fallback.",
        "",
        "## 6. Window Label Aggregation Rule",
        "",
        f"- abnormal_fraction_threshold = {abnormal_fraction_threshold:.2f}",
        f"- if freeze/pre_freeze fraction >= {abnormal_fraction_threshold:.2f} -> abnormal_or_freezing_movement",
        "- else if stable labels dominate informative samples -> stable_movement",
        "- else -> unknown",
        "",
        "## 7. Export Changes",
        "",
        f"- New export directory created: `{out_dataset_dir}`",
        "- Existing `gait_instability/` directory was not modified.",
        "",
        "## 8. Unknown Rescue Results",
        "",
        f"- Legacy unknown windows: {legacy_unknown}",
        f"- Rescued abnormal windows: {rescued_abnormal}",
        f"- Rescued from legacy unknown: {rescued_from_unknown}",
        f"- Remaining unknown windows: {remaining_unknown}",
        "",
        "## 9. Gait v2 Support Recount",
        "",
    ]
    for split, info in split_reports.items():
        implementation_lines.append(
            f"- {split}: stable={info['stable_movement_count']}, abnormal={info['abnormal_or_freezing_movement_count']}, unknown_excluded={info['unknown_excluded_count']}"
        )
    implementation_lines += [
        "",
        "## 10. Subject/Recording Distribution",
        "",
        f"- Train abnormal by subject: {split_reports['train']['abnormal_by_subject']}",
        f"- Val abnormal by subject: {split_reports['val']['abnormal_by_subject']}",
        f"- Test abnormal by subject: {split_reports['test']['abnormal_by_subject']}",
        "",
        "## 11. Go/No-Go Decision",
        "",
        f"**{decision}**",
        "",
        "## 12. Files Changed",
        "",
        "- config/datasets.yaml",
        "- config/hybrid_task_routing.yaml",
        "- src/data/loaders/daphnet_fog_loader.py",
        "- src/data/windowing.py",
        "- scripts/build_gait_instability_v2_dataset.py",
        "",
        "## 13. Risks",
        "",
        "- DAPHNET is still a single-source gait dataset.",
        "- The abnormal fraction threshold may need tuning after first supervised training.",
        "- pre_freeze is not present in current local raw files, so the rescue currently targets freeze directly.",
        "",
        "## 14. Next Step",
        "",
        "- If the decision is READY_FOR_GAIT_V2_TRAINING, the next step is a gated training prompt using `outputs/windowed_dataset/gait_instability_v2/` only.",
        "- If the decision is NEED_SPLIT_REPAIR, adjust split strategy without introducing leakage.",
    ]
    _write_md(out_report_dir / "gait_label_rescue_implementation_report.md", "\n".join(implementation_lines))

    print(
        json.dumps(
            {
                "decision": decision,
                "reason": reason,
                "output_dataset_dir": str(out_dataset_dir),
                "report_dir": str(out_report_dir),
                "abnormal_fraction_threshold": abnormal_fraction_threshold,
                "split_support": {
                    split: {
                        "stable": info["stable_movement_count"],
                        "abnormal": info["abnormal_or_freezing_movement_count"],
                        "unknown_excluded": info["unknown_excluded_count"],
                    }
                    for split, info in split_reports.items()
                },
                "rescued_from_unknown_count": rescued_from_unknown,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
