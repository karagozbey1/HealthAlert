from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.column_schema import IMU_COLUMNS, standardize_records
from src.data.dataset_registry import load_dataset_metadata_registry, summarize_registry_entries
from src.data.loaders.but_ppg_loader import load_all_records as load_but_ppg_records
from src.data.loaders.hifd_loader import load_all_subjects as load_hifd_records
from src.data.loaders.weda_fall_loader import load_all_trials as load_weda_trials
from src.data.windowing import (
    assign_window_label,
    compute_window_quality,
    normalize_window_shape,
    segment_timeseries_to_windows,
)
from src.utils.io import load_all_configs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build 4-second windowed training dataset")
    parser.add_argument("--config-dir", default=str(PROJECT_ROOT / "config"))
    parser.add_argument("--registry-path", default=str(PROJECT_ROOT / "config" / "datasets.yaml"))
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs" / "windowed_dataset"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-records-per-dataset", type=int, default=None)
    parser.add_argument("--window-sec", type=int, default=4)
    parser.add_argument("--stride-sec", type=int, default=2)
    return parser.parse_args()


def _extract_ppg_series(record: Dict) -> np.ndarray | None:
    waveform = record.get("ppg_waveform")
    if waveform is not None and len(waveform) > 0:
        return np.asarray(waveform, dtype=np.float32).reshape(-1, 1)

    df = record.get("data")
    if df is None or "heart_rate" not in df.columns:
        return None

    values = df[["heart_rate"]].to_numpy(dtype=np.float32)
    if values.size == 0:
        return None
    return values


def _record_to_windows(
    dataset_name: str,
    record: Dict,
    sampling_rate_hz: int,
    window_sec: int,
    stride_sec: int,
) -> List[Dict]:
    df = record.get("data")
    imu_windows: List[Dict] = []
    ppg_windows: List[Dict] = []

    if df is not None and all(col in df.columns for col in IMU_COLUMNS):
        imu_data = df[IMU_COLUMNS].fillna(0.0).to_numpy(dtype=np.float32)
        imu_windows = segment_timeseries_to_windows(
            imu_data,
            sampling_rate_hz=sampling_rate_hz,
            window_sec=window_sec,
            stride_sec=stride_sec,
        )

    ppg_series = _extract_ppg_series(record)
    if ppg_series is not None:
        ppg_windows = segment_timeseries_to_windows(
            ppg_series,
            sampling_rate_hz=sampling_rate_hz,
            window_sec=window_sec,
            stride_sec=stride_sec,
        )

    max_windows = max(len(imu_windows), len(ppg_windows))
    windows: List[Dict] = []
    for idx in range(max_windows):
        imu_window = imu_windows[idx] if idx < len(imu_windows) else None
        ppg_window = ppg_windows[idx] if idx < len(ppg_windows) else None

        quality_source = imu_window or ppg_window
        if quality_source is None:
            continue

        quality = compute_window_quality(quality_source)
        label = assign_window_label(quality_source, record.get("label", "unknown"))
        subject_id = record.get("subject_id")
        session_id = record.get("session_id") or record.get("record_id") or f"{dataset_name}_{idx}"

        normalized_imu = None
        if imu_window is not None:
            normalized_imu = normalize_window_shape(imu_window)

        normalized_ppg = None
        if ppg_window is not None:
            normalized_ppg = normalize_window_shape(ppg_window)

        if normalized_imu is None and normalized_ppg is None:
            continue

        vitals_summary = None
        if df is not None and len(df) > 0:
            hr_values = np.asarray(df.get("heart_rate", np.array([np.nan])), dtype=np.float32)
            spo2_values = np.asarray(df.get("spo2", np.array([np.nan])), dtype=np.float32)
            hr_mean = float(np.nanmean(hr_values)) if np.any(~np.isnan(hr_values)) else 0.0
            spo2_mean = float(np.nanmean(spo2_values)) if np.any(~np.isnan(spo2_values)) else 0.0
            vitals_summary = {
                "heart_rate": hr_mean,
                "spo2": spo2_mean,
            }

        sample_count = (
            normalized_imu.get("normalized_sample_count")
            if normalized_imu is not None
            else normalized_ppg.get("normalized_sample_count")
        )

        windows.append(
            {
                "window_id": f"{dataset_name}:{session_id}:{idx}",
                "dataset_name": dataset_name,
                "subject_id": subject_id,
                "start_time": float(idx * stride_sec),
                "end_time": float((idx * stride_sec) + window_sec),
                "sampling_rate_hz": int(sampling_rate_hz),
                "window_duration_sec": int(window_sec),
                "sample_count": int(sample_count),
                "imu_samples": (
                    normalized_imu["samples"].astype(np.float32)
                    if normalized_imu is not None
                    else np.zeros((200, 6), dtype=np.float32)
                ),
                "ppg_samples": (
                    normalized_ppg["samples"].astype(np.float32)
                    if normalized_ppg is not None
                    else np.zeros((200, 1), dtype=np.float32)
                ),
                "vitals_summary": vitals_summary,
                "label": label,
                "quality_flags": quality["quality_flags"],
                "training_candidate": bool(quality["training_candidate"]),
                "fast_model_candidate": bool((quality_source or {}).get("fast_model_candidate", True)),
            }
        )

    return windows


def _load_dataset_records(dataset_name: str, dataset_entry: Dict, limit: int | None) -> Tuple[List[Dict], str | None]:
    local_path = dataset_entry.get("local_path")
    if not local_path or not Path(local_path).exists():
        return [], f"missing_dataset_path:{local_path}"

    if dataset_name == "HIFD":
        records = load_hifd_records(local_path, max_subjects=limit)
    elif dataset_name == "WEDA_FALL":
        records = load_weda_trials(local_path, max_trials=limit)
    elif dataset_name == "BUT_PPG":
        records = load_but_ppg_records(local_path, max_records=limit, load_waveforms=True)
    else:
        return [], f"unsupported_dataset:{dataset_name}"

    if dataset_name in ("HIFD", "WEDA_FALL", "BUT_PPG"):
        records = standardize_records(records, dataset_name)
    return records, None


def _window_to_feature_vector(window: Dict) -> np.ndarray:
    imu = np.asarray(window["imu_samples"], dtype=np.float32)
    ppg = np.asarray(window["ppg_samples"], dtype=np.float32)
    if ppg.size == 0 or np.all(np.isnan(ppg)):
        ppg_stats = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    else:
        ppg_stats = np.array(
            [
                float(np.nanmean(ppg)),
                float(np.nanstd(ppg)),
                float(np.nanmax(np.abs(ppg))),
            ],
            dtype=np.float32,
        )
    features = [
        np.nanmean(imu, axis=0),
        np.nanstd(imu, axis=0),
        np.nanmax(np.abs(imu), axis=0),
        ppg_stats,
    ]
    vitals = window.get("vitals_summary") or {}
    features.append(
        np.array(
            [
                float(vitals.get("heart_rate") or 0.0),
                float(vitals.get("spo2") or 0.0),
            ],
            dtype=np.float32,
        )
    )
    return np.concatenate(features, axis=0).astype(np.float32)


def _split_windows_by_subject(windows: List[Dict]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    subject_ids = sorted({w.get("subject_id") or w["dataset_name"] for w in windows})
    rng = np.random.RandomState(42)
    rng.shuffle(subject_ids)
    n = len(subject_ids)
    n_train = max(1, int(n * 0.7)) if n else 0
    n_val = max(1, int(n * 0.15)) if n > 2 else 0
    train_subjects = set(subject_ids[:n_train])
    val_subjects = set(subject_ids[n_train:n_train + n_val])
    test_subjects = set(subject_ids[n_train + n_val:])
    if not test_subjects and val_subjects:
        test_subjects.add(val_subjects.pop())

    def pick(subj_set: set[str]) -> List[Dict]:
        return [w for w in windows if (w.get("subject_id") or w["dataset_name"]) in subj_set]

    return pick(train_subjects), pick(val_subjects), pick(test_subjects)


def _write_split(path: Path, windows: List[Dict]) -> Dict[str, int]:
    label_map = {"normal": 0, "fall": 1, "near_fall": 2, "instability": 3, "bad_quality": 4, "unknown": 5}
    features = np.stack([_window_to_feature_vector(w) for w in windows], axis=0) if windows else np.zeros((0, 23), dtype=np.float32)
    labels = np.asarray([label_map.get(w["label"], 5) for w in windows], dtype=np.int64)
    imu = np.stack([w["imu_samples"] for w in windows], axis=0) if windows else np.zeros((0, 200, 6), dtype=np.float32)
    ppg = np.stack([w["ppg_samples"] for w in windows], axis=0) if windows else np.zeros((0, 200, 1), dtype=np.float32)
    metas = np.asarray([
        json.dumps(
            {
                "window_id": w["window_id"],
                "dataset_name": w["dataset_name"],
                "subject_id": w.get("subject_id"),
                "label": w["label"],
                "sample_count": w["sample_count"],
                "training_candidate": w["training_candidate"],
            }
        )
        for w in windows
    ], dtype=object)
    np.savez_compressed(path, features=features, labels=labels, imu=imu, ppg=ppg, metadata=metas)
    return dict(Counter(int(label) for label in labels.tolist()))


def build_windowed_dataset(
    *,
    config_dir: str,
    registry_path: str,
    output_dir: str,
    dry_run: bool,
    max_records_per_dataset: int | None,
    window_sec: int,
    stride_sec: int,
) -> Dict:
    cfg = load_all_configs(config_dir)
    dataset_registry = load_dataset_metadata_registry(registry_path)

    resolved_registry: Dict[str, Dict] = {}
    for key, entry in dataset_registry.items():
        resolved = dict(entry)
        local_path = str(entry.get("local_path", ""))
        local_path = local_path.replace("${paths.hifd_dir}", str(cfg.paths.hifd_dir))
        local_path = local_path.replace("${paths.weda_fall_dir}", str(cfg.paths.weda_fall_dir))
        local_path = local_path.replace("${paths.but_ppg_dir}", str(cfg.paths.but_ppg_dir))
        resolved["local_path"] = local_path
        resolved_registry[key] = resolved

    summary = {
        "window_sec": int(window_sec),
        "stride_sec": int(stride_sec),
        "target_sample_rate_hz": 50,
        "target_sample_count": 200,
        "datasets": [],
        "dataset_registry": summarize_registry_entries(resolved_registry),
        "missing_datasets": [],
    }

    all_windows: List[Dict] = []
    for _, entry in resolved_registry.items():
        dataset_name = entry["dataset_name"]
        records, error = _load_dataset_records(dataset_name, entry, max_records_per_dataset)
        dataset_summary = {
            "dataset_name": dataset_name,
            "available": error is None,
            "record_count": len(records),
            "window_count": 0,
            "error": error,
        }
        if error is not None:
            summary["missing_datasets"].append({"dataset_name": dataset_name, "reason": error})
            summary["datasets"].append(dataset_summary)
            continue

        dataset_windows: List[Dict] = []
        for record in records:
            dataset_windows.extend(
                _record_to_windows(
                    dataset_name,
                    record,
                    sampling_rate_hz=int(entry.get("sampling_rate_hz", 50)),
                    window_sec=window_sec,
                    stride_sec=stride_sec,
                )
            )
        dataset_summary["window_count"] = len(dataset_windows)
        dataset_summary["training_candidate_count"] = sum(1 for w in dataset_windows if w["training_candidate"])
        summary["datasets"].append(dataset_summary)
        all_windows.extend(dataset_windows)

    label_distribution = dict(Counter(w["label"] for w in all_windows))
    summary["total_window_count"] = len(all_windows)
    summary["label_distribution"] = label_distribution

    if dry_run:
        return summary

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    train_windows, val_windows, test_windows = _split_windows_by_subject(all_windows)
    split_summary = {
        "train": _write_split(output_path / "train.npz", train_windows),
        "val": _write_split(output_path / "val.npz", val_windows),
        "test": _write_split(output_path / "test.npz", test_windows),
    }
    summary["split_counts"] = {
        "train": len(train_windows),
        "val": len(val_windows),
        "test": len(test_windows),
    }
    summary["split_label_distribution"] = split_summary

    (output_path / "dataset_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_path / "label_distribution.json").write_text(json.dumps(label_distribution, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    args = _parse_args()
    summary = build_windowed_dataset(
        config_dir=args.config_dir,
        registry_path=args.registry_path,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        max_records_per_dataset=args.max_records_per_dataset,
        window_sec=args.window_sec,
        stride_sec=args.stride_sec,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()