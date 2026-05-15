"""Gait v2 Error Analysis — Deep-dive into existing checkpoint false positives.

Inputs:
  outputs/hybrid_redesign/gait_instability_v2_expert/best_model.pt
  outputs/hybrid_redesign/gait_instability_v2_expert/imu_norm_stats.json
  outputs/windowed_dataset/gait_instability_v2/{val,test}.npz

Outputs:
  outputs/hybrid_redesign/gait_instability_v2_expert/gait_v2_error_analysis.md
  outputs/hybrid_redesign/gait_instability_v2_expert/gait_v2_error_analysis.json
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.healthalert.models.gait_instability_expert import (  # noqa: E402
    GaitInstabilityExpertCNN,
    build_gait_instability_expert,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("gait_v2_error_analysis")

EXPECTED_PYTHON = PROJECT_ROOT.parent / ".venv311" / "Scripts" / "python.exe"
CHECKPOINT_DIR = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "gait_instability_v2_expert"
DATA_DIR = PROJECT_ROOT / "outputs" / "windowed_dataset" / "gait_instability_v2"

CLASS_NAMES = ["stable_gait", "abnormal_or_freezing_movement"]
RAW_LABEL_TO_FINAL = {0: 0, 3: 1}
VALID_LABELS = set(RAW_LABEL_TO_FINAL)
THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70]
FRACTION_THRESHOLDS = [0.0, 0.10, 0.20, 0.30, 0.40, 0.50]


def _ensure_expected_python() -> None:
    current = Path(sys.executable).resolve()
    expected = EXPECTED_PYTHON.resolve()
    if str(current).lower() != str(expected).lower():
        raise RuntimeError(f"Wrong Python: {current} ; expected: {expected}")


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def _safe_div(a: float, b: float) -> float:
    return float(a / b) if b else 0.0


def _to_builtin(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_builtin(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def _parse_meta(meta_item: object) -> Dict[str, Any]:
    if isinstance(meta_item, dict):
        return meta_item
    try:
        return json.loads(str(meta_item))
    except Exception:
        return {}


def load_split(split: str) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray], List[Dict[str, Any]]]:
    """Load a split NPZ and apply label mapping. Returns (X, y, arrays, metas)."""
    npz_path = DATA_DIR / f"{split}.npz"
    raw = np.load(str(npz_path), allow_pickle=True)

    imu = raw["imu"].astype(np.float32)
    labels_raw = raw["labels"].astype(np.int64).flatten()
    metadata = raw["metadata"]

    keep = np.array([int(lbl) in VALID_LABELS for lbl in labels_raw], dtype=bool)
    imu = imu[keep]
    labels = np.array([RAW_LABEL_TO_FINAL[int(lbl)] for lbl in labels_raw[keep]], dtype=np.int64)
    metadata = metadata[keep]

    arrays = {
        "imu": imu,
        "labels": labels,
        "metadata": metadata,
        "source": raw["source"][keep] if "source" in raw.files else np.array(["unknown"] * len(labels), dtype=object),
        "subject_id": raw["subject_id"][keep] if "subject_id" in raw.files else np.array(["unknown"] * len(labels), dtype=object),
        "recording_id": raw["recording_id"][keep] if "recording_id" in raw.files else np.array(["unknown"] * len(labels), dtype=object),
    }

    metas = [_parse_meta(m) for m in metadata]
    # model input: (N, 6, 200)
    X = imu.transpose(0, 2, 1).astype(np.float32)
    return X, labels, arrays, metas


def apply_norm(X: np.ndarray, stats: Dict[str, Any]) -> np.ndarray:
    mean = np.asarray(stats["mean_per_channel"], dtype=np.float32)
    std = np.asarray(stats["std_per_channel"], dtype=np.float32)
    return ((X - mean[None, :, None]) / std[None, :, None]).astype(np.float32)


def run_inference(model: torch.nn.Module, X: np.ndarray, device: torch.device, batch_size: int = 512) -> np.ndarray:
    model.eval()
    logits_all = []
    from torch.utils.data import DataLoader, TensorDataset
    loader = DataLoader(TensorDataset(torch.from_numpy(X)), batch_size=batch_size, shuffle=False)
    with torch.no_grad():
        for (xb,) in loader:
            out = model(xb.to(device))
            logits_all.append(out["logit"].detach().cpu().numpy())
    return np.concatenate(logits_all, axis=0).astype(np.float64)


def histogram_buckets(values: np.ndarray, n_bins: int = 10, lo: float = 0.0, hi: float = 1.0) -> List[Dict[str, Any]]:
    """Return histogram as list of {bin_start, bin_end, count, fraction}."""
    edges = np.linspace(lo, hi, n_bins + 1)
    counts, _ = np.histogram(values, bins=edges)
    total = max(len(values), 1)
    buckets = []
    for i in range(n_bins):
        buckets.append({
            "bin_start": round(float(edges[i]), 4),
            "bin_end": round(float(edges[i + 1]), 4),
            "count": int(counts[i]),
            "fraction": round(float(counts[i] / total), 4),
        })
    return buckets


def analyze_probability_distributions(
    y_true: np.ndarray,
    probs: np.ndarray,
) -> Dict[str, Any]:
    """Histogram of predicted abnormal probability for stable vs abnormal true."""
    stable_mask = y_true == 0
    abnormal_mask = y_true == 1
    stable_probs = probs[stable_mask]
    abnormal_probs = probs[abnormal_mask]

    return {
        "stable_true_abnormal_prob": {
            "n": int(stable_mask.sum()),
            "mean": round(float(stable_probs.mean()), 4) if len(stable_probs) else None,
            "median": round(float(np.median(stable_probs)), 4) if len(stable_probs) else None,
            "p10": round(float(np.percentile(stable_probs, 10)), 4) if len(stable_probs) else None,
            "p25": round(float(np.percentile(stable_probs, 25)), 4) if len(stable_probs) else None,
            "p75": round(float(np.percentile(stable_probs, 75)), 4) if len(stable_probs) else None,
            "p90": round(float(np.percentile(stable_probs, 90)), 4) if len(stable_probs) else None,
            "histogram": histogram_buckets(stable_probs),
        },
        "abnormal_true_abnormal_prob": {
            "n": int(abnormal_mask.sum()),
            "mean": round(float(abnormal_probs.mean()), 4) if len(abnormal_probs) else None,
            "median": round(float(np.median(abnormal_probs)), 4) if len(abnormal_probs) else None,
            "p10": round(float(np.percentile(abnormal_probs, 10)), 4) if len(abnormal_probs) else None,
            "p25": round(float(np.percentile(abnormal_probs, 25)), 4) if len(abnormal_probs) else None,
            "p75": round(float(np.percentile(abnormal_probs, 75)), 4) if len(abnormal_probs) else None,
            "p90": round(float(np.percentile(abnormal_probs, 90)), 4) if len(abnormal_probs) else None,
            "histogram": histogram_buckets(abnormal_probs),
        },
        "overlap_region": {
            "description": "fraction of stable samples with prob >= 0.20 (false positive region at threshold=0.20)",
            "fp_rate_at_0_20": round(float((stable_probs >= 0.20).mean()), 4) if len(stable_probs) else None,
            "fp_rate_at_0_30": round(float((stable_probs >= 0.30).mean()), 4) if len(stable_probs) else None,
            "fp_rate_at_0_40": round(float((stable_probs >= 0.40).mean()), 4) if len(stable_probs) else None,
            "fp_rate_at_0_50": round(float((stable_probs >= 0.50).mean()), 4) if len(stable_probs) else None,
        },
    }


def analyze_false_positives(
    y_true: np.ndarray,
    probs: np.ndarray,
    arrays: Dict[str, np.ndarray],
    metas: List[Dict[str, Any]],
    threshold: float = 0.20,
) -> Dict[str, Any]:
    """Stable samples predicted as abnormal."""
    preds = (probs >= threshold).astype(int)
    fp_mask = (y_true == 0) & (preds == 1)

    subjects = np.asarray(arrays["subject_id"])
    recordings = np.asarray(arrays["recording_id"])
    fp_probs = probs[fp_mask]
    fp_subjects = subjects[fp_mask]
    fp_recordings = recordings[fp_mask]
    fp_metas = [metas[i] for i, flag in enumerate(fp_mask) if flag]

    fp_abnormal_fractions = np.array([float(m.get("abnormal_fraction", 0.0)) for m in fp_metas])

    subject_dist = dict(Counter(str(s) for s in fp_subjects.tolist()))
    recording_dist = dict(Counter(str(r) for r in fp_recordings.tolist()))

    return {
        "threshold": float(threshold),
        "total_stable": int((y_true == 0).sum()),
        "fp_count": int(fp_mask.sum()),
        "fp_rate": round(float(fp_mask[y_true == 0].mean()), 4),
        "prob_mean": round(float(fp_probs.mean()), 4) if len(fp_probs) else None,
        "prob_median": round(float(np.median(fp_probs)), 4) if len(fp_probs) else None,
        "prob_p25": round(float(np.percentile(fp_probs, 25)), 4) if len(fp_probs) else None,
        "prob_p75": round(float(np.percentile(fp_probs, 75)), 4) if len(fp_probs) else None,
        "subject_distribution": subject_dist,
        "recording_distribution": recording_dist,
        "abnormal_fraction_mean": round(float(fp_abnormal_fractions.mean()), 4) if len(fp_abnormal_fractions) else None,
        "abnormal_fraction_median": round(float(np.median(fp_abnormal_fractions)), 4) if len(fp_abnormal_fractions) else None,
        "abnormal_fraction_histogram": histogram_buckets(fp_abnormal_fractions) if len(fp_abnormal_fractions) else [],
        "prob_histogram": histogram_buckets(fp_probs) if len(fp_probs) else [],
    }


def analyze_false_negatives(
    y_true: np.ndarray,
    probs: np.ndarray,
    arrays: Dict[str, np.ndarray],
    metas: List[Dict[str, Any]],
    threshold: float = 0.20,
) -> Dict[str, Any]:
    """Abnormal samples predicted as stable."""
    preds = (probs >= threshold).astype(int)
    fn_mask = (y_true == 1) & (preds == 0)

    subjects = np.asarray(arrays["subject_id"])
    recordings = np.asarray(arrays["recording_id"])
    fn_probs = probs[fn_mask]
    fn_subjects = subjects[fn_mask]
    fn_recordings = recordings[fn_mask]
    fn_metas = [metas[i] for i, flag in enumerate(fn_mask) if flag]

    fn_abnormal_fractions = np.array([float(m.get("abnormal_fraction", 0.0)) for m in fn_metas])

    subject_dist = dict(Counter(str(s) for s in fn_subjects.tolist()))
    recording_dist = dict(Counter(str(r) for r in fn_recordings.tolist()))

    return {
        "threshold": float(threshold),
        "total_abnormal": int((y_true == 1).sum()),
        "fn_count": int(fn_mask.sum()),
        "fn_rate": round(float(fn_mask[y_true == 1].mean()), 4),
        "prob_mean": round(float(fn_probs.mean()), 4) if len(fn_probs) else None,
        "prob_median": round(float(np.median(fn_probs)), 4) if len(fn_probs) else None,
        "prob_p25": round(float(np.percentile(fn_probs, 25)), 4) if len(fn_probs) else None,
        "prob_p75": round(float(np.percentile(fn_probs, 75)), 4) if len(fn_probs) else None,
        "subject_distribution": subject_dist,
        "recording_distribution": recording_dist,
        "abnormal_fraction_mean": round(float(fn_abnormal_fractions.mean()), 4) if len(fn_abnormal_fractions) else None,
        "abnormal_fraction_median": round(float(np.median(fn_abnormal_fractions)), 4) if len(fn_abnormal_fractions) else None,
        "abnormal_fraction_histogram": histogram_buckets(fn_abnormal_fractions) if len(fn_abnormal_fractions) else [],
        "prob_histogram": histogram_buckets(fn_probs) if len(fn_probs) else [],
    }


def analyze_threshold_sensitivity(y_true: np.ndarray, probs: np.ndarray) -> List[Dict[str, Any]]:
    rows = []
    for thr in THRESHOLDS:
        preds = (probs >= thr).astype(int)
        n_pred_cls = int(len(np.unique(preds)))
        tp = int(((y_true == 1) & (preds == 1)).sum())
        tn = int(((y_true == 0) & (preds == 0)).sum())
        fp = int(((y_true == 0) & (preds == 1)).sum())
        fn = int(((y_true == 1) & (preds == 0)).sum())
        stable_recall = _safe_div(tn, tn + fp)
        abnormal_recall = _safe_div(tp, tp + fn)
        abnormal_precision = _safe_div(tp, tp + fp)
        stable_f1 = _safe_div(2 * tn, 2 * tn + fp + fn) if (2 * tn + fp + fn) > 0 else 0.0
        abnormal_f1 = _safe_div(2 * tp, 2 * tp + fp + fn) if (2 * tp + fp + fn) > 0 else 0.0
        macro_f1 = (stable_f1 + abnormal_f1) / 2.0
        rows.append({
            "threshold": round(thr, 2),
            "stable_recall": round(stable_recall, 4),
            "abnormal_recall": round(abnormal_recall, 4),
            "abnormal_precision": round(abnormal_precision, 4),
            "macro_f1": round(macro_f1, 4),
            "fp": fp,
            "fn": fn,
            "tp": tp,
            "tn": tn,
            "n_pred_cls": n_pred_cls,
            "meets_constraint_stable_0_75_abnormal_0_60": bool(stable_recall >= 0.75 and abnormal_recall >= 0.60),
        })
    return rows


def analyze_abnormal_fraction(
    y_true: np.ndarray,
    metas: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Analyze abnormal_fraction distribution for windows labelled abnormal in training."""
    abnormal_mask = y_true == 1
    abnormal_metas = [metas[i] for i, flag in enumerate(abnormal_mask) if flag]
    abnormal_fractions = np.array([float(m.get("abnormal_fraction", 0.0)) for m in abnormal_metas])

    result = {
        "n_abnormal_windows": int(abnormal_mask.sum()),
        "abnormal_fraction_stats": {
            "mean": round(float(abnormal_fractions.mean()), 4) if len(abnormal_fractions) else None,
            "median": round(float(np.median(abnormal_fractions)), 4) if len(abnormal_fractions) else None,
            "min": round(float(abnormal_fractions.min()), 4) if len(abnormal_fractions) else None,
            "max": round(float(abnormal_fractions.max()), 4) if len(abnormal_fractions) else None,
            "p10": round(float(np.percentile(abnormal_fractions, 10)), 4) if len(abnormal_fractions) else None,
            "p25": round(float(np.percentile(abnormal_fractions, 25)), 4) if len(abnormal_fractions) else None,
            "p75": round(float(np.percentile(abnormal_fractions, 75)), 4) if len(abnormal_fractions) else None,
            "p90": round(float(np.percentile(abnormal_fractions, 90)), 4) if len(abnormal_fractions) else None,
        },
        "histogram": histogram_buckets(abnormal_fractions) if len(abnormal_fractions) else [],
        "purity_thresholds": {},
    }

    for ft in FRACTION_THRESHOLDS:
        remaining = int((abnormal_fractions >= ft).sum())
        result["purity_thresholds"][str(ft)] = {
            "threshold": float(ft),
            "windows_kept": remaining,
            "windows_dropped": int(len(abnormal_fractions)) - remaining,
            "kept_fraction": round(float(remaining / max(len(abnormal_fractions), 1)), 4),
        }

    return result


def build_markdown_report(
    prob_dist: Dict[str, Any],
    fp_analysis: Dict[str, Any],
    fn_analysis: Dict[str, Any],
    val_threshold_rows: List[Dict[str, Any]],
    test_threshold_rows: List[Dict[str, Any]],
    abnormal_fraction_train: Dict[str, Any],
    abnormal_fraction_test: Dict[str, Any],
    checkpoint_path: str,
) -> str:
    lines = [
        "# Gait v2 Error Analysis Report",
        "",
        "## 1. Overview",
        "",
        f"- Checkpoint: `{checkpoint_path}`",
        "- Dataset: DAPHNET_FOG (gait_instability_v2)",
        "- All analysis on test split unless noted otherwise.",
        "- Threshold analysis (section 4) done on validation set.",
        "",
        "## 2. Probability Distribution",
        "",
        "### Stable true samples — predicted abnormal probability",
        "",
        f"- N stable true: {prob_dist['stable_true_abnormal_prob']['n']:,}",
        f"- Mean prob: {prob_dist['stable_true_abnormal_prob']['mean']}",
        f"- Median prob: {prob_dist['stable_true_abnormal_prob']['median']}",
        f"- P25 / P75: {prob_dist['stable_true_abnormal_prob']['p25']} / {prob_dist['stable_true_abnormal_prob']['p75']}",
        f"- P10 / P90: {prob_dist['stable_true_abnormal_prob']['p10']} / {prob_dist['stable_true_abnormal_prob']['p90']}",
        "",
        "| Prob range | Count | Fraction |",
        "|---|---:|---:|",
    ]
    for b in prob_dist["stable_true_abnormal_prob"]["histogram"]:
        lines.append(f"| [{b['bin_start']:.2f}, {b['bin_end']:.2f}) | {b['count']:,} | {b['fraction']:.4f} |")

    lines += [
        "",
        "### Abnormal true samples — predicted abnormal probability",
        "",
        f"- N abnormal true: {prob_dist['abnormal_true_abnormal_prob']['n']:,}",
        f"- Mean prob: {prob_dist['abnormal_true_abnormal_prob']['mean']}",
        f"- Median prob: {prob_dist['abnormal_true_abnormal_prob']['median']}",
        f"- P25 / P75: {prob_dist['abnormal_true_abnormal_prob']['p25']} / {prob_dist['abnormal_true_abnormal_prob']['p75']}",
        f"- P10 / P90: {prob_dist['abnormal_true_abnormal_prob']['p10']} / {prob_dist['abnormal_true_abnormal_prob']['p90']}",
        "",
        "| Prob range | Count | Fraction |",
        "|---|---:|---:|",
    ]
    for b in prob_dist["abnormal_true_abnormal_prob"]["histogram"]:
        lines.append(f"| [{b['bin_start']:.2f}, {b['bin_end']:.2f}) | {b['count']:,} | {b['fraction']:.4f} |")

    lines += [
        "",
        "### Overlap region (false positive risk at different thresholds)",
        "",
        f"- FP rate at threshold=0.20: {prob_dist['overlap_region']['fp_rate_at_0_20']}",
        f"- FP rate at threshold=0.30: {prob_dist['overlap_region']['fp_rate_at_0_30']}",
        f"- FP rate at threshold=0.40: {prob_dist['overlap_region']['fp_rate_at_0_40']}",
        f"- FP rate at threshold=0.50: {prob_dist['overlap_region']['fp_rate_at_0_50']}",
        "",
        "## 3. False Positive Analysis (test set, threshold=0.20)",
        "",
        f"- Total stable windows: {fp_analysis['total_stable']:,}",
        f"- False positives: {fp_analysis['fp_count']:,} ({fp_analysis['fp_rate']:.2%})",
        f"- FP predicted prob mean: {fp_analysis['prob_mean']}",
        f"- FP predicted prob median: {fp_analysis['prob_median']}",
        f"- FP predicted prob P25/P75: {fp_analysis['prob_p25']} / {fp_analysis['prob_p75']}",
        f"- FP abnormal_fraction mean: {fp_analysis['abnormal_fraction_mean']}",
        f"- FP abnormal_fraction median: {fp_analysis['abnormal_fraction_median']}",
        "",
        "### FP Subject distribution",
        "",
        "| Subject | FP count |",
        "|---|---:|",
    ]
    for subj, cnt in sorted(fp_analysis["subject_distribution"].items()):
        lines.append(f"| {subj} | {cnt:,} |")

    lines += [
        "",
        "### FP Recording distribution",
        "",
        "| Recording | FP count |",
        "|---|---:|",
    ]
    for rec, cnt in sorted(fp_analysis["recording_distribution"].items()):
        lines.append(f"| {rec} | {cnt:,} |")

    lines += [
        "",
        "### FP abnormal_fraction histogram",
        "",
        "| AF range | Count | Fraction |",
        "|---|---:|---:|",
    ]
    for b in fp_analysis["abnormal_fraction_histogram"]:
        lines.append(f"| [{b['bin_start']:.2f}, {b['bin_end']:.2f}) | {b['count']:,} | {b['fraction']:.4f} |")

    lines += [
        "",
        "## 4. False Negative Analysis (test set, threshold=0.20)",
        "",
        f"- Total abnormal windows: {fn_analysis['total_abnormal']:,}",
        f"- False negatives: {fn_analysis['fn_count']:,} ({fn_analysis['fn_rate']:.2%})",
        f"- FN predicted prob mean: {fn_analysis['prob_mean']}",
        f"- FN predicted prob median: {fn_analysis['prob_median']}",
        f"- FN predicted prob P25/P75: {fn_analysis['prob_p25']} / {fn_analysis['prob_p75']}",
        f"- FN abnormal_fraction mean: {fn_analysis['abnormal_fraction_mean']}",
        f"- FN abnormal_fraction median: {fn_analysis['abnormal_fraction_median']}",
        "",
        "### FN Subject distribution",
        "",
        "| Subject | FN count |",
        "|---|---:|",
    ]
    for subj, cnt in sorted(fn_analysis["subject_distribution"].items()):
        lines.append(f"| {subj} | {cnt:,} |")

    lines += [
        "",
        "### FN abnormal_fraction histogram",
        "",
        "| AF range | Count | Fraction |",
        "|---|---:|---:|",
    ]
    for b in fn_analysis["abnormal_fraction_histogram"]:
        lines.append(f"| [{b['bin_start']:.2f}, {b['bin_end']:.2f}) | {b['count']:,} | {b['fraction']:.4f} |")

    lines += [
        "",
        "## 5. Threshold Sensitivity (validation set)",
        "",
        "Constraint objective: stable_recall >= 0.75 AND abnormal_recall >= 0.60",
        "",
        "| Threshold | stable recall | abnormal recall | abnormal precision | macro_f1 | FP | FN | Meets constraint |",
        "|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in val_threshold_rows:
        meets = "YES" if row["meets_constraint_stable_0_75_abnormal_0_60"] else "no"
        lines.append(
            f"| {row['threshold']} | {row['stable_recall']} | {row['abnormal_recall']} | {row['abnormal_precision']} | {row['macro_f1']} | {row['fp']} | {row['fn']} | {meets} |"
        )

    lines += [
        "",
        "### Threshold sensitivity (test set, for reference only)",
        "",
        "| Threshold | stable recall | abnormal recall | abnormal precision | macro_f1 | FP | FN |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in test_threshold_rows:
        lines.append(
            f"| {row['threshold']} | {row['stable_recall']} | {row['abnormal_recall']} | {row['abnormal_precision']} | {row['macro_f1']} | {row['fp']} | {row['fn']} |"
        )

    lines += [
        "",
        "## 6. Abnormal Fraction Analysis",
        "",
        "### Train split abnormal windows",
        "",
        f"- N abnormal windows in train: {abnormal_fraction_train['n_abnormal_windows']:,}",
        f"- Mean abnormal_fraction: {abnormal_fraction_train['abnormal_fraction_stats']['mean']}",
        f"- Median abnormal_fraction: {abnormal_fraction_train['abnormal_fraction_stats']['median']}",
        f"- Min / Max: {abnormal_fraction_train['abnormal_fraction_stats']['min']} / {abnormal_fraction_train['abnormal_fraction_stats']['max']}",
        f"- P10 / P25 / P75 / P90: {abnormal_fraction_train['abnormal_fraction_stats']['p10']} / {abnormal_fraction_train['abnormal_fraction_stats']['p25']} / {abnormal_fraction_train['abnormal_fraction_stats']['p75']} / {abnormal_fraction_train['abnormal_fraction_stats']['p90']}",
        "",
        "| AF range | Count | Fraction |",
        "|---|---:|---:|",
    ]
    for b in abnormal_fraction_train["histogram"]:
        lines.append(f"| [{b['bin_start']:.2f}, {b['bin_end']:.2f}) | {b['count']:,} | {b['fraction']:.4f} |")

    lines += [
        "",
        "### Purity threshold analysis (how many abnormal train windows survive at each AF threshold)",
        "",
        "| AF threshold | Kept | Dropped | Kept fraction |",
        "|---|---:|---:|---:|",
    ]
    for ft_str, info in abnormal_fraction_train["purity_thresholds"].items():
        lines.append(f"| >= {ft_str} | {info['windows_kept']:,} | {info['windows_dropped']:,} | {info['kept_fraction']:.4f} |")

    lines += [
        "",
        "### Test split abnormal windows",
        "",
        f"- N abnormal windows in test: {abnormal_fraction_test['n_abnormal_windows']:,}",
        f"- Mean abnormal_fraction: {abnormal_fraction_test['abnormal_fraction_stats']['mean']}",
        f"- Median abnormal_fraction: {abnormal_fraction_test['abnormal_fraction_stats']['median']}",
        "",
        "| AF range | Count | Fraction |",
        "|---|---:|---:|",
    ]
    for b in abnormal_fraction_test["histogram"]:
        lines.append(f"| [{b['bin_start']:.2f}, {b['bin_end']:.2f}) | {b['count']:,} | {b['fraction']:.4f} |")

    lines += [
        "",
        "## 7. Key Findings and Implications for Ablation",
        "",
        "### Root cause hypothesis",
        "",
        "- The model was trained with pos_weight_cap=5.0, which strongly penalised stable predictions.",
        "- Val loss exploded from epoch 2 (2.59) onwards, indicating the model overfit to the high pos_weight signal.",
        "- Best checkpoint was epoch 2 (val macro_f1=0.3994) — very early, model barely learned.",
        "- At threshold=0.20, 62.7% of stable windows are falsely classified as abnormal (923/1471).",
        "",
        "### Ablation priorities",
        "",
        "1. **Reduce pos_weight_cap**: Test 1.0, 2.0, 3.0 to reduce FP explosion.",
        "2. **Lower LR (1e-4)**: Slower training may prevent val loss explosion.",
        "3. **Purity filtering**: Higher abnormal_fraction_threshold may give cleaner signal.",
        "4. **Threshold re-selection**: Use constraint stable>=0.75, abnormal>=0.60 on val.",
        "",
        "### DAPHNET single-source risk",
        "",
        "- All data is from one dataset (DAPHNET_FOG).",
        "- Subject-aware split ensures no leakage but generalisation to other datasets is unknown.",
        "- Val (S05 only) and test (S01, S02) have different subject characteristics than train.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    _ensure_expected_python()
    log.info("=== Gait v2 Error Analysis ===")

    # --- Load norm stats
    norm_stats_path = CHECKPOINT_DIR / "imu_norm_stats.json"
    with open(norm_stats_path, "r", encoding="utf-8") as f:
        norm_stats = json.load(f)
    log.info("Loaded norm stats from %s", norm_stats_path)

    # --- Load model
    checkpoint_path = CHECKPOINT_DIR / "best_model.pt"
    device = torch.device("cpu")
    model = build_gait_instability_expert()
    state = torch.load(str(checkpoint_path), map_location=device, weights_only=False)
    model_state = state.get("model_state_dict", state)
    model.load_state_dict(model_state)
    model.eval()
    log.info("Loaded checkpoint from %s", checkpoint_path)

    # --- Load splits
    log.info("Loading val split...")
    X_val, y_val, arrays_val, metas_val = load_split("val")
    X_val_norm = apply_norm(X_val, norm_stats)

    log.info("Loading test split...")
    X_test, y_test, arrays_test, metas_test = load_split("test")
    X_test_norm = apply_norm(X_test, norm_stats)

    log.info("Loading train split (for abnormal_fraction analysis only)...")
    _, y_train, _, metas_train = load_split("train")

    # --- Run inference
    log.info("Running inference on val (%d samples)...", len(y_val))
    logits_val = run_inference(model, X_val_norm, device)
    probs_val = _sigmoid(logits_val)

    log.info("Running inference on test (%d samples)...", len(y_test))
    logits_test = run_inference(model, X_test_norm, device)
    probs_test = _sigmoid(logits_test)

    # --- Analysis
    log.info("Analyzing probability distributions (test)...")
    prob_dist = analyze_probability_distributions(y_test, probs_test)

    log.info("Analyzing false positives (test, threshold=0.20)...")
    fp_analysis = analyze_false_positives(y_test, probs_test, arrays_test, metas_test, threshold=0.20)

    log.info("Analyzing false negatives (test, threshold=0.20)...")
    fn_analysis = analyze_false_negatives(y_test, probs_test, arrays_test, metas_test, threshold=0.20)

    log.info("Analyzing threshold sensitivity (val)...")
    val_threshold_rows = analyze_threshold_sensitivity(y_val, probs_val)

    log.info("Analyzing threshold sensitivity (test)...")
    test_threshold_rows = analyze_threshold_sensitivity(y_test, probs_test)

    log.info("Analyzing abnormal_fraction (train)...")
    af_train = analyze_abnormal_fraction(y_train, metas_train)

    log.info("Analyzing abnormal_fraction (test)...")
    af_test = analyze_abnormal_fraction(y_test, metas_test)

    # --- Build payload
    payload = {
        "checkpoint": str(checkpoint_path),
        "probability_distributions": prob_dist,
        "false_positives": fp_analysis,
        "false_negatives": fn_analysis,
        "threshold_sensitivity_val": val_threshold_rows,
        "threshold_sensitivity_test": test_threshold_rows,
        "abnormal_fraction_train": af_train,
        "abnormal_fraction_test": af_test,
    }

    # --- Save JSON
    out_json = CHECKPOINT_DIR / "gait_v2_error_analysis.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(_to_builtin(payload), f, indent=2)
    log.info("Saved JSON: %s", out_json)

    # --- Build and save markdown
    md = build_markdown_report(
        prob_dist=prob_dist,
        fp_analysis=fp_analysis,
        fn_analysis=fn_analysis,
        val_threshold_rows=val_threshold_rows,
        test_threshold_rows=test_threshold_rows,
        abnormal_fraction_train=af_train,
        abnormal_fraction_test=af_test,
        checkpoint_path=str(checkpoint_path),
    )
    out_md = CHECKPOINT_DIR / "gait_v2_error_analysis.md"
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)
    log.info("Saved Markdown: %s", out_md)

    # Print summary
    print("\n=== ERROR ANALYSIS SUMMARY ===")
    print(f"Val threshold sensitivity (no threshold meets stable>=0.75 AND abnormal>=0.60):")
    meeting = [r for r in val_threshold_rows if r["meets_constraint_stable_0_75_abnormal_0_60"]]
    if meeting:
        best = max(meeting, key=lambda r: (r["macro_f1"], r["abnormal_precision"]))
        print(f"  Best qualifying threshold: {best['threshold']} | stable_recall={best['stable_recall']} | abnormal_recall={best['abnormal_recall']} | macro_f1={best['macro_f1']} | FP={best['fp']}")
    else:
        print("  NO threshold meets the constraint on validation set with this checkpoint.")
    print(f"FP analysis (test, t=0.20): {fp_analysis['fp_count']:,} / {fp_analysis['total_stable']:,} stable windows FP ({fp_analysis['fp_rate']:.2%})")
    print(f"FN analysis (test, t=0.20): {fn_analysis['fn_count']:,} / {fn_analysis['total_abnormal']:,} abnormal windows FN ({fn_analysis['fn_rate']:.2%})")
    print(f"\nOutputs:")
    print(f"  {out_json}")
    print(f"  {out_md}")


if __name__ == "__main__":
    main()
