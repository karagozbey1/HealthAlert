from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader_registry import load_dataset_by_name
from src.data.splitting import subject_aware_split
from src.data.windowing import build_standard_windows

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("healthalert.build_activity_v2_pure_adl")

EXPECTED_PYTHON = PROJECT_ROOT.parent / ".venv311" / "Scripts" / "python.exe"
DATASETS_CFG = PROJECT_ROOT / "config" / "datasets.yaml"
OUT_DATASET_DIR = PROJECT_ROOT / "outputs" / "windowed_dataset" / "activity_v2_pure_adl"
OUT_REPORT_DIR = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "activity_v2"

TARGET_LABELS = ["walking", "sitting", "standing", "lying"]
TARGET_LABEL_TO_ID = {label: idx for idx, label in enumerate(TARGET_LABELS)}
PURE_ADL_DATASETS = ["uci_har", "mobiact", "pamap2", "unimib_shar", "umafall", "sisfall"]
MOBIACT_PURE_LABEL_MAP = {
    "WAL": "walking",
    "STD": "standing",
    "SCH": "sitting",
    "LYI": "lying",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Activity v2 pure ADL dataset")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--split_attempts", type=int, default=200)
    parser.add_argument("--output_dir", type=str, default=str(OUT_DATASET_DIR))
    parser.add_argument("--report_dir", type=str, default=str(OUT_REPORT_DIR))
    return parser.parse_args()


def _ensure_expected_python() -> None:
    current = Path(sys.executable).resolve()
    expected = EXPECTED_PYTHON.resolve()
    if current != expected:
        raise RuntimeError(
            f"Use the project interpreter only. expected={expected} current={current}"
        )


def _norm_name(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_").strip()


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


def _load_dataset_configs() -> Dict[str, Dict[str, Any]]:
    raw_cfg = yaml.safe_load(DATASETS_CFG.read_text(encoding="utf-8"))
    datasets = raw_cfg.get("datasets", {})
    resolved: Dict[str, Dict[str, Any]] = {}
    for key, cfg in datasets.items():
        entry = dict(cfg)
        local_path = entry.get("local_path")
        if local_path:
            entry["local_path"] = str((PROJECT_ROOT / local_path).resolve())
        resolved[_norm_name(key)] = entry
    return resolved


def _record_primary_label(record: Any) -> Optional[str]:
    labels = getattr(record, "labels", None)
    if labels is None or len(labels) == 0:
        return None
    return str(labels[0])


def _derive_pure_label(record: Any) -> Optional[str]:
    dataset_name = _norm_name(getattr(record, "dataset_name", "unknown"))
    primary_label = _record_primary_label(record)

    if dataset_name == "uci_har":
        return primary_label if primary_label in TARGET_LABELS else None

    if dataset_name == "mobiact":
        metadata = getattr(record, "metadata", {}) or {}
        pure_label = metadata.get("pure_adl_label")
        if pure_label in TARGET_LABELS:
            return str(pure_label)
        activity_code = str(metadata.get("activity_code", "")).upper()
        return MOBIACT_PURE_LABEL_MAP.get(activity_code)

    if dataset_name == "pamap2":
        return primary_label if primary_label in TARGET_LABELS else None

    return None


def _build_windowable_record(record: Any, pure_label: str) -> Dict[str, Any]:
    imu_samples = getattr(record, "imu_samples", None)
    labels = getattr(record, "labels", None)
    n_samples = int(len(labels)) if labels is not None else int(len(imu_samples))
    return {
        "dataset_name": getattr(record, "dataset_name", "unknown"),
        "subject_id": str(getattr(record, "subject_id", "unknown")),
        "recording_id": str(getattr(record, "recording_id", "unknown")),
        "sampling_rate_hz": float(getattr(record, "sampling_rate_hz", 50.0)),
        "imu_samples": imu_samples,
        "labels": np.full(n_samples, pure_label, dtype=object),
        "valid_tasks": ["activity_context", "adl_detection"],
        "metadata": getattr(record, "metadata", {}) or {},
    }


def _audit_dataset(
    dataset_key: str,
    dataset_cfg: Dict[str, Any],
    load_result: Any,
) -> Dict[str, Any]:
    records = list(load_result.records or [])
    primary_labels = Counter()
    pure_labels = Counter()
    subject_ids = set()
    activity_codes = Counter()

    for record in records:
        label = _record_primary_label(record)
        if label is not None:
            primary_labels.update([label])
        pure_label = _derive_pure_label(record)
        if pure_label is not None:
            pure_labels.update([pure_label])
        subject_id = str(getattr(record, "subject_id", "unknown"))
        if subject_id not in {"", "unknown", "None"}:
            subject_ids.add(subject_id)
        metadata = getattr(record, "metadata", {}) or {}
        activity_code = metadata.get("activity_code")
        if activity_code:
            activity_codes.update([str(activity_code)])

    missing_target_labels = [label for label in TARGET_LABELS if pure_labels.get(label, 0) == 0]
    local_path = Path(str(dataset_cfg.get("local_path", "")))
    path_exists = local_path.exists() if str(local_path) else False

    notes: List[str] = []
    feasible_now = bool(records) and not missing_target_labels
    if dataset_key == "uci_har":
        notes.append("Provides all four target labels with preserved subject IDs.")
    elif dataset_key == "mobiact":
        if path_exists and records:
            notes.append("Pure ADL is recovered from activity_code/pure_adl_label metadata.")
        else:
            notes.append("Could provide pure ADL via activity_code metadata, but current raw data is missing in repo.")
    elif dataset_key == "pamap2":
        if path_exists and records:
            notes.append("Parser recovers lying/sitting/standing/walking segments from Protocol files.")
        else:
            notes.append("Parser is wired, but PAMAP2 raw files are not present in the repo.")
    elif dataset_key == "unimib_shar":
        notes.append("ADL windows are collapsed to normal; subclasses are not preserved.")
    elif dataset_key == "umafall":
        notes.append("ADL is exposed only as normal; sitting/standing/lying subclasses are absent.")
    elif dataset_key == "sisfall":
        notes.append("Current repo copy is instability/normal oriented, not clean ADL context.")

    return {
        "dataset": dataset_key,
        "display_name": dataset_cfg.get("name", dataset_key),
        "status": load_result.status,
        "raw_path": str(local_path),
        "raw_path_exists": path_exists,
        "n_records": len(records),
        "n_unique_subjects": len(subject_ids),
        "supports_subject_split": len(subject_ids) >= 3,
        "top_primary_labels": dict(primary_labels.most_common(10)),
        "top_activity_codes": dict(activity_codes.most_common(10)),
        "pure_label_support": dict(pure_labels),
        "pure_label_missing": missing_target_labels,
        "feasible_for_pure_adl_now": feasible_now,
        "errors": list(load_result.errors or [])[:10],
        "notes": notes,
    }


def _find_complete_split(
    windows: List[Dict[str, Any]],
    required_labels: Iterable[str],
    seed: int,
    max_attempts: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    required = list(required_labels)
    best: Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]] = None
    best_missing: Optional[int] = None
    best_seed = seed

    for offset in range(max_attempts):
        split_seed = seed + offset
        train, val, test = subject_aware_split(windows, seed=split_seed)
        split_sets = {"train": train, "val": val, "test": test}
        missing = 0
        coverage: Dict[str, List[str]] = {}
        all_present = True
        for split_name, split_windows in split_sets.items():
            present = {str(window["label"]) for window in split_windows}
            missing_labels = [label for label in required if label not in present]
            coverage[split_name] = sorted(present)
            missing += len(missing_labels)
            if missing_labels:
                all_present = False

        if best is None or best_missing is None or missing < best_missing:
            best = (train, val, test)
            best_missing = missing
            best_seed = split_seed

        if all_present:
            return train, val, test, {
                "seed": split_seed,
                "all_splits_have_all_labels": True,
                "missing_label_count": 0,
                "split_label_coverage": coverage,
            }

    assert best is not None
    train, val, test = best
    split_sets = {"train": train, "val": val, "test": test}
    coverage = {
        name: sorted({str(window["label"]) for window in split_windows})
        for name, split_windows in split_sets.items()
    }
    return train, val, test, {
        "seed": best_seed,
        "all_splits_have_all_labels": False,
        "missing_label_count": int(best_missing or 0),
        "split_label_coverage": coverage,
    }


def _summarize_windows(windows: List[Dict[str, Any]]) -> Dict[str, Any]:
    label_counts = Counter(str(window["label"]) for window in windows)
    source_counts = Counter(str(window["dataset_name"]) for window in windows)
    subject_counts = Counter(str(window["subject_id"]) for window in windows)
    return {
        "n_windows": len(windows),
        "label_counts": dict(label_counts),
        "source_counts": dict(source_counts),
        "n_unique_subjects": len(subject_counts),
    }


def _build_metadata(window: Dict[str, Any], label_id: int) -> str:
    payload = {
        "dataset_name": window["dataset_name"],
        "subject_id": window["subject_id"],
        "recording_id": window["recording_id"],
        "window_id": window["window_id"],
        "label": window["label"],
        "label_id": label_id,
        "quality_score": window.get("quality_score"),
        "resampled": window.get("resampled", False),
    }
    return json.dumps(payload, ensure_ascii=True)


def _export_split(split_name: str, windows: List[Dict[str, Any]], out_dir: Path) -> Dict[str, Any]:
    split_path = out_dir / f"{split_name}.npz"
    imu = np.stack([window["imu"].astype(np.float32) for window in windows], axis=0)
    labels = np.array([TARGET_LABEL_TO_ID[str(window["label"])] for window in windows], dtype=np.int64)
    metadata = np.array([_build_metadata(window, int(label_id)) for window, label_id in zip(windows, labels)], dtype=object)
    np.savez_compressed(
        split_path,
        imu=imu,
        labels=labels,
        metadata=metadata,
        label_names=np.array(TARGET_LABELS, dtype=object),
    )
    return {
        "path": str(split_path),
        **_summarize_windows(windows),
    }


def _render_audit_markdown(audit: Dict[str, Any]) -> str:
    lines = [
        "# Activity v2 Pure ADL Dataset Audit",
        "",
        f"Decision: {audit['decision']}",
        "",
        "## Key Findings",
    ]
    for item in audit["key_findings"]:
        lines.append(f"- {item}")

    lines.extend(["", "## Dataset Feasibility"])
    for entry in audit["datasets"]:
        lines.extend(
            [
                "",
                f"### {entry['display_name']}",
                f"- status: {entry['status']}",
                f"- raw_path_exists: {entry['raw_path_exists']}",
                f"- n_records: {entry['n_records']}",
                f"- n_unique_subjects: {entry['n_unique_subjects']}",
                f"- pure_label_support: {json.dumps(entry['pure_label_support'], ensure_ascii=True)}",
                f"- pure_label_missing: {json.dumps(entry['pure_label_missing'], ensure_ascii=True)}",
            ]
        )
        for note in entry["notes"]:
            lines.append(f"- note: {note}")
        for error in entry["errors"]:
            lines.append(f"- error: {error}")

    lines.extend(
        [
            "",
            "## PAMAP2",
            f"- present_in_config: {audit['pamap2']['present_in_config']}",
            f"- raw_path_exists: {audit['pamap2']['raw_path_exists']}",
            f"- feasibility: {audit['pamap2']['feasibility_note']}",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_support_markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Activity v2 Support Recount",
        "",
        f"Ready for training: {summary['ready_for_training']}",
        f"Split seed: {summary['split_info']['seed']}",
        "",
        "## Split Coverage",
    ]
    for split_name, labels in summary["split_info"]["split_label_coverage"].items():
        lines.append(f"- {split_name}: {', '.join(labels)}")

    lines.extend(["", "## Export Summary"])
    for split_name in ("train", "val", "test"):
        split = summary[split_name]
        lines.extend(
            [
                f"### {split_name}",
                f"- windows: {split['n_windows']}",
                f"- unique_subjects: {split['n_unique_subjects']}",
                f"- label_counts: {json.dumps(split['label_counts'], ensure_ascii=True)}",
                f"- source_counts: {json.dumps(split['source_counts'], ensure_ascii=True)}",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    _ensure_expected_python()

    output_dir = Path(args.output_dir)
    report_dir = Path(args.report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    dataset_cfgs = _load_dataset_configs()

    audit_entries: List[Dict[str, Any]] = []
    usable_windows: List[Dict[str, Any]] = []
    builder_source_summary: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for dataset_key in PURE_ADL_DATASETS:
        dataset_cfg = dataset_cfgs.get(dataset_key)
        if dataset_cfg is None:
            audit_entries.append(
                {
                    "dataset": dataset_key,
                    "display_name": dataset_key,
                    "status": "missing_config",
                    "raw_path": "",
                    "raw_path_exists": False,
                    "n_records": 0,
                    "n_unique_subjects": 0,
                    "supports_subject_split": False,
                    "top_primary_labels": {},
                    "top_activity_codes": {},
                    "pure_label_support": {},
                    "pure_label_missing": list(TARGET_LABELS),
                    "feasible_for_pure_adl_now": False,
                    "errors": ["Dataset entry not found in config/datasets.yaml"],
                    "notes": [],
                }
            )
            continue

        load_result = load_dataset_by_name(dataset_cfg)
        audit_entries.append(_audit_dataset(dataset_key, dataset_cfg, load_result))

        for record in load_result.records or []:
            pure_label = _derive_pure_label(record)
            if pure_label is None:
                continue

            record_dict = _build_windowable_record(record, pure_label)
            windows = build_standard_windows(record_dict, config=dataset_cfg)
            for window in windows:
                if not window.get("training_candidate", False):
                    continue
                if not window.get("has_imu", False):
                    continue
                if str(window["label"]) not in TARGET_LABELS:
                    continue
                usable_windows.append(window)
                builder_source_summary[str(window["dataset_name"])][str(window["label"])] += 1

    pamap2_cfg = dataset_cfgs.get("pamap2")
    pamap2_path = Path(str(pamap2_cfg.get("local_path", ""))) if pamap2_cfg else None
    if pamap2_cfg is None:
        pamap2_note = "No PAMAP2 config or loader scaffold in repo yet."
    elif not (pamap2_path and pamap2_path.exists()):
        pamap2_note = "PAMAP2 scaffold exists, but raw data is not present in repo. Activity v2 remains UCI-HAR-only until data is added."
    else:
        pamap2_note = "PAMAP2 raw path exists and is integrated into the pure ADL builder."
    pamap2_info = {
        "present_in_config": pamap2_cfg is not None,
        "raw_path_exists": bool(pamap2_path and pamap2_path.exists()),
        "feasibility_note": pamap2_note,
    }

    usable_sources = sorted(builder_source_summary.keys())
    mobiact_entry = next((item for item in audit_entries if item["dataset"] == "mobiact"), None)
    if mobiact_entry is None:
        mobiact_note = "MobiAct audit entry is missing."
    elif mobiact_entry["raw_path_exists"] and mobiact_entry["n_records"] > 0:
        mobiact_note = "MobiAct raw CSV files are integrated into pure ADL build when available."
    else:
        mobiact_note = "MobiAct loader is integrated for pure ADL, but the raw folder is empty in this repo snapshot."

    key_findings = [
        "Current activity_context export is contaminated by generic normal/instability sources and is not suitable for pure ADL training.",
        f"Usable pure ADL sources available now: {', '.join(usable_sources) if usable_sources else 'none'}.",
        "UCI-HAR preserves walking/sitting/standing/lying labels end-to-end and remains the active training source in the current repo snapshot.",
        mobiact_note,
        pamap2_note,
    ]

    audit_payload = {
        "decision": "READY_FOR_ACTIVITY_V2_DATASET_BUILD" if usable_windows else "BLOCKED_NO_PURE_ADL_WINDOWS",
        "target_labels": TARGET_LABELS,
        "datasets": audit_entries,
        "key_findings": key_findings,
        "pamap2": pamap2_info,
    }

    audit_json_path = report_dir / "activity_v2_dataset_audit.json"
    audit_md_path = report_dir / "activity_v2_dataset_audit.md"
    audit_json_path.write_text(json.dumps(audit_payload, indent=2, default=_json_default), encoding="utf-8")
    audit_md_path.write_text(_render_audit_markdown(audit_payload), encoding="utf-8")

    if not usable_windows:
        log.warning("No usable pure ADL windows were found.")
        return

    train_windows, val_windows, test_windows, split_info = _find_complete_split(
        usable_windows,
        required_labels=TARGET_LABELS,
        seed=args.seed,
        max_attempts=args.split_attempts,
    )

    export_summary = {
        "target_labels": TARGET_LABELS,
        "usable_sources": usable_sources,
        "builder_source_summary": {k: dict(v) for k, v in builder_source_summary.items()},
        "split_info": split_info,
        "ready_for_training": bool(split_info["all_splits_have_all_labels"]),
        "train": _export_split("train", train_windows, output_dir),
        "val": _export_split("val", val_windows, output_dir),
        "test": _export_split("test", test_windows, output_dir),
    }

    summary_json_path = output_dir / "summary.json"
    support_json_path = report_dir / "activity_v2_support_recount.json"
    support_md_path = report_dir / "activity_v2_support_recount.md"
    summary_json_path.write_text(json.dumps(export_summary, indent=2, default=_json_default), encoding="utf-8")
    support_json_path.write_text(json.dumps(export_summary, indent=2, default=_json_default), encoding="utf-8")
    support_md_path.write_text(_render_support_markdown(export_summary), encoding="utf-8")

    log.info("Activity v2 audit written to %s", audit_md_path)
    log.info("Activity v2 support recount written to %s", support_md_path)
    log.info("Activity v2 dataset export written to %s", output_dir)


if __name__ == "__main__":
    main()