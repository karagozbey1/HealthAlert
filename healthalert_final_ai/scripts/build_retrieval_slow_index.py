from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_AI_ROOT = os.path.dirname(_SCRIPT_DIR)
_HA_ROOT = os.path.dirname(_AI_ROOT)
_DATA_ROOT = os.environ.get("HEALTHALERT_DATA_ROOT", os.path.join(_HA_ROOT, "Data"))
_OUTPUT_ROOT = os.environ.get("HEALTHALERT_OUTPUT_ROOT", os.path.join(_HA_ROOT, "outputs"))
_SLOW_INDEX_DIR = os.path.join(_OUTPUT_ROOT, "retrieval_slow")

if _AI_ROOT not in sys.path:
    sys.path.insert(0, _AI_ROOT)

from src.data.loaders.hifd_loader import load_all_subjects as hifd_load_all
from src.data.loaders.weda_fall_loader import load_all_trials as weda_load_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("healthalert.build_retrieval_slow")

ORIGINAL_SR = 50
TARGET_SR = 1
DOWNSAMPLE_FACTOR = ORIGINAL_SR // TARGET_SR

SLOW_WINDOW = 30
SLOW_STRIDE = 10
MIN_SLOW_WINDOW = 10


# Ham etiket değerini yavaş indeks için kullanılan sınıf adına çevirir.
def _map_label_group(label: int) -> str:
    return {0: "normal", 1: "fall", 2: "near_fall"}.get(label, "normal")


# Etiket grubunu yavaş indeks tarafındaki risk seviyesine dönüştürür.
def _map_risk_level(label_group: str) -> str:
    return {"fall": "critical", "near_fall": "warning"}.get(label_group, "low")


# 50 Hz veriyi 1 Hz özet bloklarına indirger.
def downsample_to_1hz(
    data_arr: np.ndarray,
    factor: int = DOWNSAMPLE_FACTOR,
) -> np.ndarray:
    n = len(data_arr)
    n_bins = n // factor
    if n_bins == 0:
        return np.empty((0, data_arr.shape[1]), dtype=np.float32)
    trimmed = data_arr[: n_bins * factor]
    reshaped = trimmed.reshape(n_bins, factor, data_arr.shape[1])
    return reshaped.mean(axis=1).astype(np.float32)


# 1 Hz penceresi için zaman alanında anlamlı kalan özet özellikleri çıkarır.
def extract_slow_features(
    accel_1hz: Optional[np.ndarray],
    gyro_1hz: Optional[np.ndarray],
    hr_1hz: Optional[np.ndarray] = None,
    spo2_1hz: Optional[np.ndarray] = None,
    quality_1hz: Optional[np.ndarray] = None,
) -> np.ndarray:
    feats: List[float] = []

    if accel_1hz is not None and len(accel_1hz) > 0:
        accel_mag = np.linalg.norm(accel_1hz, axis=1)
        feats += [
            float(np.mean(accel_mag)),
            float(np.std(accel_mag)),
            float(np.max(accel_mag)),
            float(np.min(accel_mag)),
            float(np.max(accel_mag) - np.min(accel_mag)),
        ]
        energy = float(np.mean((accel_mag - 1.0) ** 2))
        feats.append(energy)
        if accel_1hz.shape[1] > 2 and len(accel_1hz) > 1:
            jerk = float(np.mean(np.abs(np.diff(accel_1hz[:, 2]))))
            feats.append(jerk)
        else:
            feats.append(0.0)
    else:
        feats += [0.0] * 7

    if gyro_1hz is not None and len(gyro_1hz) > 0:
        gyro_mag = np.linalg.norm(gyro_1hz, axis=1)
        feats += [
            float(np.mean(gyro_mag)),
            float(np.std(gyro_mag)),
            float(np.max(gyro_mag)),
            float(np.min(gyro_mag)),
            float(np.max(gyro_mag) - np.min(gyro_mag)),
        ]
    else:
        feats += [0.0] * 5

    if hr_1hz is not None and len(hr_1hz) > 0:
        valid_hr = hr_1hz[hr_1hz > 0]
        if len(valid_hr) > 0:
            feats += [
                float(np.mean(valid_hr)),
                float(np.std(valid_hr)),
                float(np.min(valid_hr)),
                float(np.max(valid_hr)),
            ]
        else:
            feats += [72.0, 0.0, 72.0, 72.0]
    else:
        feats += [0.0] * 4

    if spo2_1hz is not None and len(spo2_1hz) > 0:
        valid_spo2 = spo2_1hz[(spo2_1hz > 0) & (spo2_1hz <= 100)]
        if len(valid_spo2) > 0:
            feats += [
                float(np.mean(valid_spo2)),
                float(np.std(valid_spo2)),
                float(np.min(valid_spo2)),
                float(np.max(valid_spo2)),
            ]
        else:
            feats += [98.0, 0.0, 98.0, 98.0]
    else:
        feats += [0.0] * 4

    if quality_1hz is not None and len(quality_1hz) > 0:
        feats.append(float(np.mean(quality_1hz)))
    else:
        feats.append(1.0)

    arr = np.array(feats, dtype=np.float32)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


# Yavaş özellik vektörünün beklenen boyutunu döndürür.
def get_slow_feature_dim() -> int:
    return 21


# 1 Hz özet veriyi çakışmalı pencerelere ayırır.
def extract_slow_windows(
    data_1hz: np.ndarray,
    window_size: int = SLOW_WINDOW,
    stride: int = SLOW_STRIDE,
    min_window: int = MIN_SLOW_WINDOW,
) -> List[Tuple[int, np.ndarray]]:
    n = len(data_1hz)
    if n < min_window:
        return []
    windows = []
    start = 0
    while start < n:
        end = start + window_size
        chunk = data_1hz[start:end]
        if len(chunk) >= min_window:
            windows.append((start, chunk))
        if end >= n:
            break
        start += stride
    return windows


# HIFD kayıtlarını 1 Hz pencere ve özellik matrisine dönüştürür.
def process_hifd_slow(
    hifd_dir: str,
    max_subjects: Optional[int] = None,
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    logger.info("HIFD slow: loading subjects from %s", hifd_dir)
    subjects = hifd_load_all(hifd_dir, max_subjects=max_subjects)
    logger.info("HIFD slow: %d trials loaded", len(subjects))

    feature_rows: List[np.ndarray] = []
    metadata: List[Dict[str, Any]] = []

    for record in subjects:
        df = record["data"]
        label = record["label"]
        subject_id = record.get("subject_id", "hifd_?")
        scenario = record.get("scenario", "unknown")
        label_group = _map_label_group(label)

        accel_cols = [c for c in ["ax", "ay", "az"] if c in df.columns]
        gyro_cols = [c for c in ["droll", "dpitch", "dyaw"] if c in df.columns]
        hr_col = "heart" if "heart" in df.columns else None

        if not accel_cols:
            continue

        arr = df[accel_cols].to_numpy(dtype=np.float32)
        gyro_arr = df[gyro_cols].to_numpy(dtype=np.float32) if gyro_cols else None
        hr_arr = df[hr_col].to_numpy(dtype=np.float32) if hr_col else None

        accel_1hz = downsample_to_1hz(arr)
        gyro_1hz = downsample_to_1hz(gyro_arr) if gyro_arr is not None else None
        hr_1hz = None
        if hr_arr is not None:
            hr_1hz = downsample_to_1hz(hr_arr.reshape(-1, 1)).flatten()

        windows = extract_slow_windows(accel_1hz)
        for win_start, win_accel in windows:
            win_end = win_start + len(win_accel)

            win_gyro = gyro_1hz[win_start:win_end] if gyro_1hz is not None else None
            win_hr = hr_1hz[win_start:win_end] if hr_1hz is not None else None

            fv = extract_slow_features(win_accel, win_gyro, win_hr)
            feature_rows.append(fv)
            metadata.append({
                "dataset": "HIFD",
                "subject_id": f"hifd_{subject_id}" if not str(subject_id).startswith("hifd_") else str(subject_id),
                "scenario": scenario,
                "label_group": label_group,
                "risk_level_estimate": _map_risk_level(label_group),
                "window_index": len(metadata),
                "slow_index": True,
            })

    if not feature_rows:
        return np.empty((0, get_slow_feature_dim()), dtype=np.float32), []

    return np.vstack(feature_rows).astype(np.float32), metadata


# WEDA_FALL kayıtlarını 1 Hz pencere ve özellik matrisine dönüştürür.
def process_weda_slow(
    weda_dir: str,
    max_trials: Optional[int] = None,
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    logger.info("WEDA_FALL slow: loading trials from %s", weda_dir)
    trials = weda_load_all(weda_dir, frequency="50Hz", max_trials=max_trials)
    logger.info("WEDA_FALL slow: %d trials loaded", len(trials))

    feature_rows: List[np.ndarray] = []
    metadata: List[Dict[str, Any]] = []

    for trial in trials:
        df = trial.get("data")
        if df is None:
            continue
        label = trial.get("label", 0)
        subject_id = trial.get("subject_id", "weda_?")
        scenario = trial.get("scenario", trial.get("trial_id", "unknown"))
        label_group = _map_label_group(int(label))

        accel_cols = [c for c in ["accel_x", "accel_y", "accel_z"] if c in df.columns]
        gyro_cols = [c for c in ["gyro_x", "gyro_y", "gyro_z"] if c in df.columns]

        if not accel_cols:
            continue

        arr = df[accel_cols].to_numpy(dtype=np.float32)
        gyro_arr = df[gyro_cols].to_numpy(dtype=np.float32) if gyro_cols else None

        accel_1hz = downsample_to_1hz(arr)
        gyro_1hz = downsample_to_1hz(gyro_arr) if gyro_arr is not None else None

        windows = extract_slow_windows(accel_1hz)
        for win_start, win_accel in windows:
            win_end = win_start + len(win_accel)
            win_gyro = gyro_1hz[win_start:win_end] if gyro_1hz is not None else None

            fv = extract_slow_features(win_accel, win_gyro)
            feature_rows.append(fv)
            metadata.append({
                "dataset": "WEDA_FALL",
                "subject_id": str(subject_id),
                "scenario": str(scenario),
                "label_group": label_group,
                "risk_level_estimate": _map_risk_level(label_group),
                "window_index": len(metadata),
                "slow_index": True,
            })

    if not feature_rows:
        return np.empty((0, get_slow_feature_dim()), dtype=np.float32), []

    return np.vstack(feature_rows).astype(np.float32), metadata


# Yavaş örneklemeli retrieval indeksini üretip ilgili dosyaları diske yazar.
def build_slow(
    hifd_dir: str,
    weda_dir: str,
    output_dir: str,
    max_subjects: Optional[int] = None,
    max_trials: Optional[int] = None,
    n_neighbors: int = 10,
) -> Dict[str, Any]:
    import joblib
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler

    os.makedirs(output_dir, exist_ok=True)
    t_start = time.perf_counter()

    all_features: List[np.ndarray] = []
    all_metadata: List[Dict[str, Any]] = []

    if os.path.isdir(hifd_dir):
        hifd_feat, hifd_meta = process_hifd_slow(hifd_dir, max_subjects=max_subjects)
        if len(hifd_feat) > 0:
            all_features.append(hifd_feat)
            all_metadata.extend(hifd_meta)
            logger.info("HIFD slow: %d windows", len(hifd_feat))
    else:
        logger.warning("HIFD directory not found: %s", hifd_dir)

    if os.path.isdir(weda_dir):
        weda_feat, weda_meta = process_weda_slow(weda_dir, max_trials=max_trials)
        if len(weda_feat) > 0:
            all_features.append(weda_feat)
            all_metadata.extend(weda_meta)
            logger.info("WEDA_FALL slow: %d windows", len(weda_feat))
    else:
        logger.warning("WEDA_FALL directory not found: %s", weda_dir)

    if not all_features:
        logger.error("No features extracted. Check dataset directories.")
        return {"error": "no_features"}

    X = np.vstack(all_features).astype(np.float32)
    total_windows = len(X)
    feature_dim = X.shape[1]

    from collections import Counter
    label_counts = Counter(m["label_group"] for m in all_metadata)

    scaler = StandardScaler().fit(X)
    X_scaled = scaler.transform(X)
    k = min(n_neighbors, total_windows - 1) if total_windows > 1 else 1
    nn = NearestNeighbors(n_neighbors=k, metric="euclidean", algorithm="ball_tree")
    nn.fit(X_scaled)

    joblib.dump(nn, os.path.join(output_dir, "retrieval_index.joblib"))
    joblib.dump(scaler, os.path.join(output_dir, "retrieval_scaler.joblib"))
    np.save(os.path.join(output_dir, "retrieval_features.npy"), X)
    with open(os.path.join(output_dir, "retrieval_metadata.json"), "w") as f:
        json.dump(all_metadata, f)

    elapsed = round(time.perf_counter() - t_start, 1)
    summary = {
        "total_windows": total_windows,
        "feature_dim": feature_dim,
        "slow_index": True,
        "downsample_factor": DOWNSAMPLE_FACTOR,
        "slow_window_size": SLOW_WINDOW,
        "slow_stride": SLOW_STRIDE,
        "target_sample_rate_hz": TARGET_SR,
        "datasets_included": sorted({m["dataset"] for m in all_metadata}),
        "datasets_skipped": [{"dataset": "BUT_PPG", "reason": "no_imu_data"}],
        "label_distribution": dict(label_counts),
        "build_time_sec": elapsed,
        "n_neighbors": k,
    }
    with open(os.path.join(output_dir, "retrieval_build_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    logger.info("Slow index build complete in %.1f s", elapsed)
    logger.info("  Total 1Hz windows : %d", total_windows)
    logger.info("  Feature dim       : %d", feature_dim)
    logger.info("  Datasets          : %s", summary["datasets_included"])
    logger.info("  Labels            : %s", dict(label_counts))

    return summary


# Komut satırından gelen dizin ve sınır ayarlarını okur.
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build slow-rate (1Hz-aligned) retrieval index for HealthAlert"
    )
    parser.add_argument("--hifd-dir", default=os.path.join(_DATA_ROOT, "HIFD"))
    parser.add_argument("--weda-dir", default=os.path.join(_DATA_ROOT, "WEDA_FALL"))
    parser.add_argument("--output-dir", default=_SLOW_INDEX_DIR)
    parser.add_argument("--max-subjects", type=int, default=None)
    parser.add_argument("--max-trials", type=int, default=None)
    parser.add_argument("--n-neighbors", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = build_slow(
        hifd_dir=args.hifd_dir,
        weda_dir=args.weda_dir,
        output_dir=args.output_dir,
        max_subjects=args.max_subjects,
        max_trials=args.max_trials,
        n_neighbors=args.n_neighbors,
    )
    print(json.dumps(result, indent=2))
