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
_RETRIEVAL_DIR = os.path.join(_OUTPUT_ROOT, "retrieval")

# AI paketini doğrudan içe aktarabilmek için kök dizini yol listesine ekler.
if _AI_ROOT not in sys.path:
    sys.path.insert(0, _AI_ROOT)

from src.data.loaders.hifd_loader import load_all_subjects as hifd_load_all
from src.data.loaders.weda_fall_loader import load_all_trials as weda_load_all
from src.data.feature_engineering.feature_pipeline import (
    extract_all_handcrafted_features,
    get_feature_dim,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("healthalert.build_retrieval")

WINDOW_SIZE: int = 200
STRIDE: int = 50
MIN_WINDOW: int = 50

_LABEL_GROUP_MAP = {0: "normal", 1: "fall", 2: "near_fall"}
_RISK_LEVEL_MAP = {
    "normal": "normal",
    "fall": "critical",
    "near_fall": "warning",
    "unknown": "unknown",
}


# Ham etiket değerini proje içindeki sınıf adına çevirir.
def _map_label_group(label: int) -> str:
    return _LABEL_GROUP_MAP.get(label, "unknown")


# Etiket grubunu tahmini risk seviyesine dönüştürür.
def _map_risk_level(label_group: str) -> str:
    return _RISK_LEVEL_MAP.get(label_group, "unknown")


# Veriyi kaydırmalı pencerelere böler ve yeterli uzunluktaki son parçayı da korur.
def extract_windows(
    data_arr: np.ndarray,
    window_size: int = WINDOW_SIZE,
    stride: int = STRIDE,
    min_window: int = MIN_WINDOW,
) -> List[Tuple[int, np.ndarray]]:
    n = len(data_arr)
    if n < min_window:
        return []

    results: List[Tuple[int, np.ndarray]] = []
    start = 0
    while start + window_size <= n:
        results.append((start, data_arr[start: start + window_size]))
        start += stride

    remaining = n - start
    if remaining >= min_window:
        results.append((start, data_arr[start:]))

    return results


# Verilen aday isimler arasından ilk bulunan sütunu numpy dizisi olarak döndürür.
def _safe_column(df, *names) -> Optional[np.ndarray]:
    for name in names:
        if name in df.columns:
            return df[name].to_numpy(dtype=np.float32)
    return None


# Ham pencere verisinden retrieval için kullanılacak özellik vektörünü üretir.
def extract_feature_from_window(
    window_data: np.ndarray,
    column_names: List[str],
    sr: int = 50,
) -> np.ndarray:
    import pandas as pd

    df = pd.DataFrame(window_data, columns=column_names)

    accel: Optional[np.ndarray] = None
    gyro: Optional[np.ndarray] = None

    accel_cols_hifd = ["ax", "ay", "az"]
    accel_cols_weda = ["accel_x", "accel_y", "accel_z"]
    gyro_cols_hifd = ["droll", "dpitch", "dyaw"]
    gyro_cols_weda = ["gyro_x", "gyro_y", "gyro_z"]

    if all(c in df.columns for c in accel_cols_hifd):
        accel = df[accel_cols_hifd].to_numpy(dtype=np.float32)
        if all(c in df.columns for c in gyro_cols_hifd):
            gyro = df[gyro_cols_hifd].to_numpy(dtype=np.float32)
    elif all(c in df.columns for c in accel_cols_weda):
        accel = df[accel_cols_weda].to_numpy(dtype=np.float32)
        if all(c in df.columns for c in gyro_cols_weda):
            gyro = df[gyro_cols_weda].to_numpy(dtype=np.float32)

    hr_signal: Optional[np.ndarray] = _safe_column(df, "heart", "heart_rate", "hr")
    spo2_signal: Optional[np.ndarray] = _safe_column(df, "spo2", "SpO2")
    ppg_quality_col = _safe_column(df, "ppg_quality", "signal_quality", "quality")
    ppg_quality: Optional[float] = (
        float(np.nanmean(ppg_quality_col)) if ppg_quality_col is not None else None
    )

    feat_vec, _ = extract_all_handcrafted_features(
        accel=accel,
        gyro=gyro,
        hr_signal=hr_signal,
        spo2_signal=spo2_signal,
        ppg_quality=ppg_quality,
        sr=sr,
    )

    feat_vec = np.nan_to_num(feat_vec, nan=0.0, posinf=0.0, neginf=0.0)
    return feat_vec


# HIFD kayıtlarını pencereleyip özellik matrisi ve meta verilerini üretir.
def process_hifd(
    hifd_dir: str,
    max_subjects: Optional[int] = None,
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    logger.info("Loading HIFD from %s ...", hifd_dir)
    records = hifd_load_all(hifd_dir, max_subjects=max_subjects)
    logger.info("HIFD: %d trials loaded", len(records))

    all_features: List[np.ndarray] = []
    all_meta: List[Dict[str, Any]] = []
    global_win_idx = 0

    for rec in records:
        df = rec["data"]
        subject_id: str = rec["subject_id"]
        scenario: str = rec["scenario"]
        label: int = rec["label"]
        source_file: str = rec.get("session_id", f"{subject_id}_{scenario}")

        label_group = _map_label_group(label)
        risk_level = _map_risk_level(label_group)

        has_imu = "ax" in df.columns
        has_hr = "heart" in df.columns
        modalities = "imu_ppg" if (has_imu and has_hr) else ("imu" if has_imu else "unknown")

        col_names = list(df.columns)
        data_arr = df.to_numpy(dtype=np.float32)

        windows = extract_windows(data_arr)
        for start_idx, win_arr in windows:
            fv = extract_feature_from_window(win_arr, col_names, sr=50)
            all_features.append(fv)
            all_meta.append({
                "dataset": "HIFD",
                "subject_id": subject_id,
                "source_file": source_file,
                "scenario": scenario,
                "window_index": global_win_idx,
                "label_raw": int(label),
                "label_group": label_group,
                "risk_level_estimate": risk_level,
                "modalities": modalities,
                "sampling_rate": 50,
                "feature_dim": len(fv),
                "window_start_sample": start_idx,
            })
            global_win_idx += 1

    if not all_features:
        logger.warning("HIFD: no windows extracted")
        return np.empty((0, get_feature_dim())), []

    feature_matrix = np.stack(all_features, axis=0)
    logger.info(
        "HIFD: %d windows extracted, feature_dim=%d",
        len(all_features), feature_matrix.shape[1],
    )
    return feature_matrix, all_meta


# WEDA_FALL kayıtlarını pencereleyip özellik matrisi ve meta verilerini üretir.
def process_weda(
    weda_dir: str,
    max_trials: Optional[int] = None,
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    logger.info("Loading WEDA_FALL from %s ...", weda_dir)
    records = weda_load_all(weda_dir, frequency="50Hz", max_trials=max_trials)
    logger.info("WEDA_FALL: %d trials loaded", len(records))

    all_features: List[np.ndarray] = []
    all_meta: List[Dict[str, Any]] = []
    global_win_idx = 0

    for rec in records:
        df = rec["data"]
        subject_id: str = rec["subject_id"]
        scenario: str = rec["scenario"]
        label: int = rec["label"]
        source_file: str = rec.get("session_id", f"{subject_id}_{scenario}")

        label_group = _map_label_group(label)
        risk_level = _map_risk_level(label_group)
        modalities = "imu"

        col_names = list(df.columns)
        data_arr = df.to_numpy(dtype=np.float32)

        windows = extract_windows(data_arr)
        for start_idx, win_arr in windows:
            fv = extract_feature_from_window(win_arr, col_names, sr=50)
            all_features.append(fv)
            all_meta.append({
                "dataset": "WEDA_FALL",
                "subject_id": subject_id,
                "source_file": source_file,
                "scenario": scenario,
                "window_index": global_win_idx,
                "label_raw": int(label),
                "label_group": label_group,
                "risk_level_estimate": risk_level,
                "modalities": modalities,
                "sampling_rate": 50,
                "feature_dim": len(fv),
                "window_start_sample": start_idx,
            })
            global_win_idx += 1

    if not all_features:
        logger.warning("WEDA_FALL: no windows extracted")
        return np.empty((0, get_feature_dim())), []

    feature_matrix = np.stack(all_features, axis=0)
    logger.info(
        "WEDA_FALL: %d windows extracted, feature_dim=%d",
        len(all_features), feature_matrix.shape[1],
    )
    return feature_matrix, all_meta


# Veri kümelerini birleştirip ölçekler ve retrieval indeksini diske kaydeder.
def build(
    hifd_dir: Optional[str] = None,
    weda_dir: Optional[str] = None,
    output_dir: str = _RETRIEVAL_DIR,
    max_subjects: Optional[int] = None,
    max_trials: Optional[int] = None,
    n_neighbors: int = 10,
) -> Dict[str, Any]:
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler
    import joblib

    t0 = time.time()
    os.makedirs(output_dir, exist_ok=True)

    hifd_dir = hifd_dir or os.path.join(_DATA_ROOT, "HIFD")
    weda_dir = weda_dir or os.path.join(_DATA_ROOT, "WEDA_FALL")

    logger.info("=" * 60)
    logger.info("HealthAlert Part 3 — Build Retrieval Index")
    logger.info("HIFD dir:      %s", hifd_dir)
    logger.info("WEDA_FALL dir: %s", weda_dir)
    logger.info("Output dir:    %s", output_dir)
    logger.info("=" * 60)

    datasets_included: List[str] = []
    datasets_skipped: List[Dict[str, str]] = []

    all_features_list: List[np.ndarray] = []
    all_meta: List[Dict[str, Any]] = []

    if os.path.isdir(hifd_dir):
        feat_hifd, meta_hifd = process_hifd(hifd_dir, max_subjects=max_subjects)
        if len(feat_hifd) > 0:
            all_features_list.append(feat_hifd)
            all_meta.extend(meta_hifd)
            datasets_included.append("HIFD")
        else:
            datasets_skipped.append({"dataset": "HIFD", "reason": "No windows extracted"})
    else:
        reason = f"Directory not found: {hifd_dir}"
        logger.warning("HIFD skipped: %s", reason)
        datasets_skipped.append({"dataset": "HIFD", "reason": reason})

    if os.path.isdir(weda_dir):
        feat_weda, meta_weda = process_weda(weda_dir, max_trials=max_trials)
        if len(feat_weda) > 0:
            all_features_list.append(feat_weda)
            all_meta.extend(meta_weda)
            datasets_included.append("WEDA_FALL")
        else:
            datasets_skipped.append({"dataset": "WEDA_FALL", "reason": "No windows extracted"})
    else:
        reason = f"Directory not found: {weda_dir}"
        logger.warning("WEDA_FALL skipped: %s", reason)
        datasets_skipped.append({"dataset": "WEDA_FALL", "reason": reason})

    datasets_skipped.append({
        "dataset": "BUT_PPG",
        "reason": (
            "Excluded by design: contains only PPG quality annotations without IMU data. "
            "Including it would make all IMU features NaN and produce meaningless "
            "distance metrics in the retrieval index. See Part 3 report §7."
        ),
    })

    if not all_features_list:
        raise RuntimeError("No datasets could be loaded — cannot build index")

    X = np.vstack(all_features_list).astype(np.float32)
    feature_dim = X.shape[1]
    total_windows = X.shape[0]

    logger.info(
        "Combined: %d windows, feature_dim=%d from %s",
        total_windows, feature_dim, datasets_included,
    )

    nan_count = int(np.sum(~np.isfinite(X)))
    if nan_count > 0:
        logger.warning("Found %d NaN/inf values in feature matrix — replacing with 0", nan_count)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    logger.info("Fitting StandardScaler ...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    actual_k = min(n_neighbors, total_windows)
    logger.info("Fitting NearestNeighbors(n_neighbors=%d, metric='euclidean') ...", actual_k)
    nn = NearestNeighbors(n_neighbors=actual_k, metric="euclidean", algorithm="ball_tree")
    nn.fit(X_scaled)

    from collections import Counter
    label_counts = Counter(m["label_group"] for m in all_meta)

    logger.info("Saving index to %s ...", output_dir)

    joblib.dump(nn, os.path.join(output_dir, "retrieval_index.joblib"))
    joblib.dump(scaler, os.path.join(output_dir, "retrieval_scaler.joblib"))
    np.save(os.path.join(output_dir, "retrieval_features.npy"), X.astype(np.float32))

    with open(os.path.join(output_dir, "retrieval_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(all_meta, f, indent=2)

    elapsed = round(time.time() - t0, 2)
    summary: Dict[str, Any] = {
        "build_time_sec": elapsed,
        "total_windows": total_windows,
        "feature_dim": feature_dim,
        "datasets_included": datasets_included,
        "datasets_skipped": datasets_skipped,
        "label_distribution": dict(label_counts),
        "n_neighbors": actual_k,
        "scaler": "StandardScaler",
        "index_algorithm": "NearestNeighbors(ball_tree, euclidean)",
        "window_size": WINDOW_SIZE,
        "stride": STRIDE,
        "sampling_rate_hz": 50,
        "nan_count_in_raw_matrix": nan_count,
        "output_dir": output_dir,
    }

    with open(
        os.path.join(output_dir, "retrieval_build_summary.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(summary, f, indent=2)

    logger.info("=" * 60)
    logger.info("Build complete in %.1f s", elapsed)
    logger.info("  Total windows : %d", total_windows)
    logger.info("  Feature dim   : %d", feature_dim)
    logger.info("  Datasets      : %s", datasets_included)
    logger.info("  Labels        : %s", dict(label_counts))
    logger.info("  Output dir    : %s", output_dir)
    logger.info("=" * 60)

    return summary


# Komut satırından gelen dizin ve sınır ayarlarını okur.
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build retrieval index for HealthAlert Part 3 PoC"
    )
    parser.add_argument(
        "--hifd-dir",
        default=None,
        help="Path to HIFD root (default: auto-detect from project structure)",
    )
    parser.add_argument(
        "--weda-dir",
        default=None,
        help="Path to WEDA_FALL root (default: auto-detect from project structure)",
    )
    parser.add_argument(
        "--output-dir",
        default=_RETRIEVAL_DIR,
        help=f"Output directory (default: {_RETRIEVAL_DIR})",
    )
    parser.add_argument(
        "--max-subjects",
        type=int,
        default=None,
        help="Limit HIFD subjects for fast debug run (default: all)",
    )
    parser.add_argument(
        "--max-trials",
        type=int,
        default=None,
        help="Limit WEDA_FALL trials for fast debug run (default: all)",
    )
    parser.add_argument(
        "--n-neighbors",
        type=int,
        default=10,
        help="NearestNeighbors k (default: 10)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    summary = build(
        hifd_dir=args.hifd_dir,
        weda_dir=args.weda_dir,
        output_dir=args.output_dir,
        max_subjects=args.max_subjects,
        max_trials=args.max_trials,
        n_neighbors=args.n_neighbors,
    )
    print(json.dumps(summary, indent=2))
