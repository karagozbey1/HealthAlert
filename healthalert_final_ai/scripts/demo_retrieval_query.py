from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_AI_ROOT = os.path.dirname(_SCRIPT_DIR)
_HA_ROOT = os.path.dirname(_AI_ROOT)
_DATA_ROOT = os.environ.get("HEALTHALERT_DATA_ROOT", os.path.join(_HA_ROOT, "Data"))
_OUTPUT_ROOT = os.environ.get("HEALTHALERT_OUTPUT_ROOT", os.path.join(_HA_ROOT, "outputs"))
_RETRIEVAL_DIR = os.path.join(_OUTPUT_ROOT, "retrieval")

if _AI_ROOT not in sys.path:
    sys.path.insert(0, _AI_ROOT)

from src.inference.retrieval_engine import RetrievalEngine
from src.data.feature_engineering.feature_pipeline import (
    extract_all_handcrafted_features,
    get_feature_dim,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("healthalert.demo_retrieval")


# Düşme benzeri ivme ve jiroskop sıçraması içeren sentetik bir pencere üretir.
def _make_synthetic_fall_window(n: int = 200) -> Dict[str, np.ndarray]:
    rng = np.random.default_rng(42)

    fall_t = n // 2
    peak = np.zeros(n)
    peak[fall_t - 5: fall_t + 10] = rng.uniform(3.0, 8.0, 15)

    accel = rng.normal(0.0, 0.05, (n, 3)).astype(np.float32)
    accel[:, 2] += 1.0
    accel[fall_t - 5: fall_t + 10] += peak[fall_t - 5: fall_t + 10, None]

    gyro = rng.normal(0.0, 0.5, (n, 3)).astype(np.float32)
    gyro[fall_t - 3: fall_t + 8] += rng.uniform(2.0, 5.0, (11, 3))

    hr = np.clip(rng.normal(85.0, 5.0, n), 60, 180).astype(np.float32)
    spo2 = np.clip(rng.normal(97.0, 1.0, n), 85, 100).astype(np.float32)

    return {"accel": accel, "gyro": gyro, "hr": hr, "spo2": spo2}


# Daha sakin ve düşük değişkenlikli normal aktivite penceresi üretir.
def _make_synthetic_normal_window(n: int = 200) -> Dict[str, np.ndarray]:
    rng = np.random.default_rng(7)
    accel = rng.normal(0.0, 0.02, (n, 3)).astype(np.float32)
    accel[:, 2] += 1.0
    gyro = rng.normal(0.0, 0.05, (n, 3)).astype(np.float32)
    hr = np.clip(rng.normal(70.0, 3.0, n), 50, 110).astype(np.float32)
    spo2 = np.clip(rng.normal(98.5, 0.5, n), 92, 100).astype(np.float32)
    return {"accel": accel, "gyro": gyro, "hr": hr, "spo2": spo2}


# HIFD içinden örnek bir gerçek pencere seçerek demo sorgusu hazırlar.
def _load_real_hifd_window(
    hifd_dir: str, seed: int = 42
) -> Optional[Dict[str, Any]]:
    try:
        from src.data.loaders.hifd_loader import load_subject
        from pathlib import Path

        hifd_path = Path(hifd_dir)
        subject_dirs = sorted(hifd_path.glob("subject_*"))
        if not subject_dirs:
            return None

        rng = random.Random(seed)
        rng.shuffle(subject_dirs)

        for sd in subject_dirs[:5]:
            try:
                sid = int(sd.name.split("_")[1])
            except (IndexError, ValueError):
                continue
            records = load_subject(hifd_path, sid, scenarios=["fall1", "fall2", "walk"])
            for rec in records:
                df = rec["data"]
                if len(df) < 200:
                    continue
                window_df = df.iloc[:200]
                accel_cols = ["ax", "ay", "az"]
                gyro_cols = ["droll", "dpitch", "dyaw"]
                if not all(c in df.columns for c in accel_cols):
                    continue
                accel = window_df[accel_cols].to_numpy(dtype=np.float32)
                gyro = (
                    window_df[gyro_cols].to_numpy(dtype=np.float32)
                    if all(c in window_df.columns for c in gyro_cols)
                    else None
                )
                hr = (
                    window_df["heart"].to_numpy(dtype=np.float32)
                    if "heart" in window_df.columns
                    else None
                )
                return {
                    "accel": accel,
                    "gyro": gyro,
                    "hr": hr,
                    "spo2": None,
                    "source": f"HIFD subject_{sid:02d} {rec['scenario']}",
                    "label_group": {0: "normal", 1: "fall", 2: "near_fall"}.get(
                        rec["label"], "unknown"
                    ),
                }
    except Exception as exc:
        logger.warning("Could not load HIFD window: %s", exc)
    return None


# İndeksi yükler, sorguyu çalıştırır ve sonucu ekrana ile dosyaya hazırlar.
def run_demo(
    index_dir: str = _RETRIEVAL_DIR,
    top_k: int = 10,
    use_real_data: bool = True,
    seed: int = 42,
    exclude_self: bool = False,
) -> Dict[str, Any]:
    # Demo sorgusunu calistirip sonucu disa aktarilabilir yapida dondurur.
    logger.info("Loading RetrievalEngine from %s ...", index_dir)
    engine = RetrievalEngine()
    loaded = engine.load(index_dir)

    if not loaded:
        logger.error("Failed to load index. Run build_retrieval_index.py first.")
        return {"error": "Index not loaded", "retrieval_available": False}

    feature_dim = engine._feature_dim
    logger.info("Engine ready — feature_dim=%d", feature_dim)

    selected_source: str
    label_group_hint: str = "unknown"
    window_data: Dict[str, Any]

    hifd_dir = os.path.join(_DATA_ROOT, "HIFD")
    real_window = None
    if use_real_data and os.path.isdir(hifd_dir):
        real_window = _load_real_hifd_window(hifd_dir, seed=seed)

    if real_window is not None:
        window_data = real_window
        selected_source = real_window.get("source", "HIFD real window")
        label_group_hint = real_window.get("label_group", "unknown")
        logger.info("Using real HIFD window: %s (label=%s)", selected_source, label_group_hint)
    else:
        window_data = _make_synthetic_fall_window(n=200)
        selected_source = "synthetic_fall_window"
        label_group_hint = "fall"
        logger.info("Using synthetic fall window")

    feat_vec, _ = extract_all_handcrafted_features(
        accel=window_data.get("accel"),
        gyro=window_data.get("gyro"),
        hr_signal=window_data.get("hr"),
        spo2_signal=window_data.get("spo2"),
        ppg_quality=None,
        sr=50,
    )
    feat_vec = np.nan_to_num(feat_vec, nan=0.0, posinf=0.0, neginf=0.0)

    logger.info("Feature vector: shape=%s, dim=%d", feat_vec.shape, len(feat_vec))

    t0 = time.perf_counter()
    result = engine.query(feat_vec, top_k=top_k)
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    result["query_latency_ms"] = latency_ms
    result["selected_source"] = selected_source
    result["label_group_hint"] = label_group_hint
    result["feature_dim"] = int(len(feat_vec))
    result["timestamp"] = datetime.now(tz=timezone.utc).isoformat()
    exclude_self_applied = False
    self_match_present = False
    query_subject = None
    if real_window is not None:
        src = real_window.get("source", "")
        parts = src.split()
        if len(parts) >= 2 and parts[0].upper() == "HIFD":
            try:
                subj_num = int(parts[1].split("_")[1])
                query_subject = f"hifd_{subj_num:02d}"
            except (IndexError, ValueError):
                query_subject = None

    if result.get("retrieval_available"):
        examples = result.get("similar_examples", [])
        for ex in examples:
            if ex.get("distance", 1.0) < 1e-6:
                self_match_present = True
                break
            if (
                query_subject is not None
                and ex.get("subject_id") == query_subject
                and ex.get("dataset") == "HIFD"
            ):
                self_match_present = True
                break

        if exclude_self and self_match_present and query_subject is not None:
            filtered = [
                ex for ex in examples
                if not (
                    ex.get("distance", 1.0) < 1e-6
                    or (
                        ex.get("subject_id") == query_subject
                        and ex.get("dataset") == "HIFD"
                    )
                )
            ]
            result["similar_examples"] = filtered
            exclude_self_applied = True
            logger.info(
                "Self-match exclusion applied: %d → %d examples",
                len(examples),
                len(filtered),
            )

    result["self_match_present"] = self_match_present
    result["exclude_self_applied"] = exclude_self_applied
    if result.get("retrieval_available"):
        explanation = engine.explain(result.get("similar_examples", []))
        result["explanation"] = explanation

    print("\n" + "=" * 60)
    print("HealthAlert Part 3 — Retrieval Demo Query")
    print("=" * 60)
    print(f"  Source      : {selected_source}")
    print(f"  Label hint  : {label_group_hint}")
    print(f"  Feature dim : {len(feat_vec)}")
    print(f"  Top-k       : {top_k}")
    print(f"  Latency     : {latency_ms} ms")
    print()
    if result.get("retrieval_available"):
        print(f"  Support score    : {result['support_score']:.4f}")
        print(f"  Fall-like ratio  : {result['fall_like_ratio']:.4f}")
        print(f"  Near-fall ratio  : {result['near_fall_ratio']:.4f}")
        print(f"  Normal ratio     : {result['normal_ratio']:.4f}")
        print()
        print(f"  Explanation: {result.get('explanation', '')}")
        print()
        print("  Top similar examples:")
        for i, ex in enumerate(result.get("similar_examples", [])[:5], 1):
            print(
                f"    {i}. [{ex['dataset']}] {ex['subject_id']} / {ex['scenario']} "
                f"— {ex['label_group']} (dist={ex['distance']:.4f})"
            )
    else:
        print(f"  Error: {result.get('error')}")
    print("=" * 60 + "\n")

    return result


# Komut satırı seçeneklerini toplayıp demo davranışını belirler.
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Demo retrieval query for HealthAlert Part 3 PoC"
    )
    parser.add_argument(
        "--index-dir",
        default=_RETRIEVAL_DIR,
        help=f"Index directory (default: {_RETRIEVAL_DIR})",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of similar windows to retrieve (default: 10)",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Force synthetic fall window even if HIFD data is available",
    )
    parser.add_argument(
        "--exclude-self",
        action="store_true",
        help="Exclude exact self-match (same subject, distance≈0) from results",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for dataset window selection (default: 42)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = run_demo(
        index_dir=args.index_dir,
        top_k=args.top_k,
        use_real_data=not args.synthetic,
        seed=args.seed,
        exclude_self=args.exclude_self,
    )

    out_path = os.path.join(args.index_dir, "demo_query_result.json")
    os.makedirs(args.index_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    logger.info("Demo result saved to %s", out_path)
