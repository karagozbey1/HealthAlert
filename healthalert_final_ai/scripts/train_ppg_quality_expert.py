"""Train HealthAlert PPG Quality Expert on prepared public NPZ windows.

This trainer intentionally does not use live ESP32/MAX30102 data.  It consumes
only outputs/windowed_dataset/ppg_quality/{train,val,test}.npz unless --smoke is
explicitly requested.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
import yaml
from torch.utils.data import DataLoader, TensorDataset

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.healthalert.models.ppg_quality_expert import (  # noqa: E402
    PPG_QUALITY_CLASSES,
    build_ppg_quality_expert,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("healthalert.train_ppg_quality_expert")

ROUTING_CFG = PROJECT_ROOT / "config" / "hybrid_task_routing.yaml"
WINDOWED_NPZ_DIR = PROJECT_ROOT / "outputs" / "windowed_dataset" / "ppg_quality"
OUT_DIR = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "ppg_quality_expert"

# Raw labels present in the current prepared ppg_quality NPZ.
# 0/10/11 are controlled lab/activity PPG windows and are used as reliable PPG.
# 20 and 21 are direct quality labels. 99 is unknown and is excluded.
RAW_LABEL_NAMES = {
    0: "normal",
    10: "walking",
    11: "sitting",
    20: "good_quality",
    21: "bad_quality",
    99: "unknown",
}
LABEL_REMAP = {
    0: 0,
    10: 0,
    11: 0,
    20: 0,
    21: 1,
    99: -1,
}
TRAIN_CLASS_NAMES = ["good_quality", "bad_quality"]
TRAIN_CLASS_IDS = [0, 1]
NUM_MODEL_CLASSES = len(PPG_QUALITY_CLASSES)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train PPG Quality Expert")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--batch_size", type=int, default=256)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--device", type=str, default="auto")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--patience", type=int, default=10)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--out_dir", type=str, default=None)
    return p.parse_args()


def _norm_src(name: str) -> str:
    return str(name).lower().replace("-", "_").replace(" ", "_").strip()


def load_routing() -> Tuple[set, set]:
    with open(ROUTING_CFG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    task = cfg.get("ppg_quality", {})
    allowed = {_norm_src(s) for s in task.get("allowed_datasets", [])}
    forbidden = {_norm_src(s) for s in task.get("forbidden_datasets", [])}
    return allowed, forbidden


def _parse_meta(meta_item: object) -> Dict:
    try:
        return json.loads(str(meta_item)) if not isinstance(meta_item, dict) else meta_item
    except Exception:
        return {}


def _source_array(metadata: np.ndarray) -> np.ndarray:
    out = np.empty(len(metadata), dtype=object)
    for i, m in enumerate(metadata):
        d = _parse_meta(m)
        out[i] = d.get("dataset_name", "unknown")
    return out


def _make_synthetic(n: int, seed: int = 42) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict]:
    rng = np.random.RandomState(seed)
    X = rng.randn(n, 1, 200).astype(np.float32)
    y = rng.choice([0, 1], size=n, p=[0.75, 0.25]).astype(np.int64)
    src = np.array(["synthetic"] * n, dtype=object)
    info = {
        "n_total_in_npz": n,
        "n_removed_bad_source": 0,
        "n_removed_bad_label": 0,
        "n_unknown_excluded": 0,
        "n_final": n,
        "raw_label_distribution": {"good_quality": int((y == 0).sum()), "bad_quality": int((y == 1).sum())},
        "class_distribution": {"good_quality": int((y == 0).sum()), "bad_quality": int((y == 1).sum())},
        "source_distribution": {"synthetic": n},
        "npz_keys": ["synthetic"],
        "ppg_shape": [n, 200, 1],
        "imu_shape": None,
        "features_shape": None,
        "labels_shape": [n],
        "metadata_present": True,
        "missing_ppg_count": 0,
        "duplicate_window_ids": 0,
    }
    return X, y, src, info


def load_ppg_npz(split: str, allowed: set, forbidden: set, smoke: bool = False) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict]:
    npz_path = WINDOWED_NPZ_DIR / f"{split}.npz"
    if not npz_path.exists():
        raise FileNotFoundError(f"[{split}] NPZ not found: {npz_path}")
    raw = np.load(str(npz_path), allow_pickle=True)
    keys = list(raw.files)
    if "ppg" not in keys or "labels" not in keys or "metadata" not in keys:
        raise KeyError(f"[{split}] expected keys ppg, labels, metadata; found {keys}")

    ppg = raw["ppg"].astype(np.float32)
    labels_raw = raw["labels"].flatten().astype(np.int64)
    metadata = raw["metadata"]
    sources = _source_array(metadata)
    n_total = len(labels_raw)

    if ppg.ndim == 2:
        ppg = ppg[:, :, None]
    if ppg.ndim != 3:
        raise ValueError(f"[{split}] ppg must be (N, T, C), got {ppg.shape}")
    X_raw = ppg.transpose(0, 2, 1)

    src_norm = np.array([_norm_src(s) for s in sources])
    keep_source = np.array([(s in allowed) and (s not in forbidden) for s in src_norm], dtype=bool)
    n_removed_bad_source = int((~keep_source).sum())

    X_raw = X_raw[keep_source]
    labels_raw = labels_raw[keep_source]
    sources = sources[keep_source]
    metadata_kept = metadata[keep_source]

    mapped = np.array([LABEL_REMAP.get(int(lbl), -1) for lbl in labels_raw], dtype=np.int64)
    keep_label = mapped >= 0
    n_removed_bad_label = int((~keep_label).sum())
    n_unknown_excluded = int(((labels_raw == 99) & (~keep_label)).sum())

    X_raw = X_raw[keep_label]
    y = mapped[keep_label]
    sources = sources[keep_label]
    metadata_kept = metadata_kept[keep_label]
    labels_kept = labels_raw[keep_label]

    finite_ppg = np.isfinite(X_raw).all(axis=(1, 2))
    non_empty_ppg = np.any(np.abs(X_raw) > 1e-12, axis=(1, 2))
    keep_ppg = finite_ppg & non_empty_ppg
    missing_ppg_count = int((~keep_ppg).sum())
    X_raw = X_raw[keep_ppg]
    y = y[keep_ppg]
    sources = sources[keep_ppg]
    metadata_kept = metadata_kept[keep_ppg]
    labels_kept = labels_kept[keep_ppg]

    if smoke:
        rng = np.random.RandomState(42)
        idx = rng.permutation(len(y))[:min(2000, len(y))]
        X_raw, y, sources = X_raw[idx], y[idx], sources[idx]
        metadata_kept, labels_kept = metadata_kept[idx], labels_kept[idx]

    class_dist = {TRAIN_CLASS_NAMES[i]: int((y == i).sum()) for i in TRAIN_CLASS_IDS}
    raw_counts = {}
    for lbl in labels_raw:
        raw_counts[RAW_LABEL_NAMES.get(int(lbl), f"label_{int(lbl)}")] = raw_counts.get(RAW_LABEL_NAMES.get(int(lbl), f"label_{int(lbl)}"), 0) + 1
    source_dist = {}
    for src in sources:
        source_dist[str(src)] = source_dist.get(str(src), 0) + 1

    window_ids = []
    subject_keys = []
    sampling_rates = {}
    label_names = {}
    for m, raw_lbl in zip(metadata_kept, labels_kept):
        d = _parse_meta(m)
        window_ids.append(str(d.get("window_id", "")))
        subject_keys.append((str(d.get("dataset_name", "")), str(d.get("subject_id", ""))))
        sr = str(d.get("sampling_rate_hz", d.get("sampling_rate", "unknown")))
        sampling_rates[sr] = sampling_rates.get(sr, 0) + 1
        name = str(d.get("label", RAW_LABEL_NAMES.get(int(raw_lbl), f"label_{int(raw_lbl)}")))
        label_names[name] = label_names.get(name, 0) + 1

    info = {
        "npz_path": str(npz_path),
        "npz_exists": True,
        "npz_keys": keys,
        "features_shape": list(raw["features"].shape) if "features" in keys else None,
        "labels_shape": list(raw["labels"].shape),
        "imu_shape": list(raw["imu"].shape) if "imu" in keys else None,
        "ppg_shape": list(raw["ppg"].shape),
        "metadata_present": "metadata" in keys,
        "n_total_in_npz": n_total,
        "n_removed_bad_source": n_removed_bad_source,
        "n_removed_bad_label": n_removed_bad_label,
        "n_unknown_excluded": n_unknown_excluded,
        "n_missing_ppg_removed": missing_ppg_count,
        "n_final": int(len(y)),
        "raw_label_distribution": raw_counts,
        "metadata_label_distribution_after_filter": label_names,
        "class_distribution": class_dist,
        "source_distribution": source_dist,
        "sampling_rate_distribution": sampling_rates,
        "duplicate_window_ids": int(len(window_ids) - len(set(window_ids))),
        "unique_subject_count": int(len(set(subject_keys))),
        "imu_required": False,
        "ppg_required": True,
    }
    return X_raw.astype(np.float32), y.astype(np.int64), sources, info


def compute_norm_stats(X: np.ndarray) -> Dict:
    mean = X.mean(axis=(0, 2))
    std = np.maximum(X.std(axis=(0, 2)), 1e-6)
    median = np.median(X, axis=(0, 2))
    q25 = np.percentile(X, 25, axis=(0, 2))
    q75 = np.percentile(X, 75, axis=(0, 2))
    return {
        "method": "per-channel z-score",
        "computed_from": "train split only",
        "mean_per_channel": mean.tolist(),
        "std_per_channel": std.tolist(),
        "median_per_channel": median.tolist(),
        "iqr_per_channel": (q75 - q25).tolist(),
        "n_channels": int(X.shape[1]),
        "window_length": int(X.shape[2]),
    }


def apply_norm(X: np.ndarray, stats: Dict) -> np.ndarray:
    mean = np.array(stats["mean_per_channel"], dtype=np.float32)
    std = np.array(stats["std_per_channel"], dtype=np.float32)
    return ((X - mean[None, :, None]) / std[None, :, None]).astype(np.float32)


def compute_class_weights(y: np.ndarray) -> torch.Tensor:
    counts = np.bincount(y, minlength=NUM_MODEL_CLASSES).astype(np.float64)
    supported = counts[:2]
    inv_sqrt = 1.0 / np.sqrt(np.maximum(supported, 1.0))
    inv_sqrt = inv_sqrt / inv_sqrt.mean()
    inv_sqrt = np.clip(inv_sqrt, 0.5, 3.0)
    weights = np.ones(NUM_MODEL_CLASSES, dtype=np.float32)
    weights[:2] = inv_sqrt.astype(np.float32)
    return torch.tensor(weights, dtype=torch.float32)


def checkpoint_valid(logits: np.ndarray, targets: np.ndarray, val_loss: float) -> Tuple[bool, str]:
    if not np.isfinite(val_loss):
        return False, "validation loss is not finite"
    if not np.isfinite(logits).all():
        return False, "logits contain NaN/Inf"
    preds = np.argmax(logits[:, :2], axis=1)
    n_pred = len(np.unique(preds))
    if n_pred < 2:
        return False, "single-class collapse"
    pred_counts = np.bincount(preds, minlength=2)
    if pred_counts.max() / max(pred_counts.sum(), 1) > 0.98:
        return False, "majority-class prediction crush"
    return True, "ok"


def run_eval(model: nn.Module, X: np.ndarray, y: np.ndarray, sources: np.ndarray, device: torch.device, batch_size: int) -> Dict:
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_recall_fscore_support,
        precision_score,
        recall_score,
    )

    model.eval()
    logits_all: List[np.ndarray] = []
    loader = DataLoader(TensorDataset(torch.from_numpy(X)), batch_size=batch_size, shuffle=False)
    with torch.no_grad():
        for (xb,) in loader:
            out = model(xb.to(device))
            logits_all.append(out["logits"].cpu().numpy())
    logits = np.concatenate(logits_all, axis=0)
    preds = np.argmax(logits[:, :2], axis=1)
    probs = torch.softmax(torch.from_numpy(logits), dim=-1).numpy()

    cm = confusion_matrix(y, preds, labels=[0, 1]).tolist()
    prec, rec, f1, sup = precision_recall_fscore_support(y, preds, labels=[0, 1], zero_division=0)
    per_class = {
        TRAIN_CLASS_NAMES[i]: {
            "precision": float(prec[i]),
            "recall": float(rec[i]),
            "f1": float(f1[i]),
            "support": int(sup[i]),
        }
        for i in range(2)
    }
    pred_dist = {TRAIN_CLASS_NAMES[i]: int((preds == i).sum()) for i in range(2)}

    src_breakdown = {}
    for src in np.unique(sources):
        mask = sources == src
        ys, ps = y[mask], preds[mask]
        if len(ys) == 0:
            continue
        _, rec_s, _, sup_s = precision_recall_fscore_support(ys, ps, labels=[0, 1], zero_division=0)
        src_breakdown[str(src)] = {
            "n": int(mask.sum()),
            "accuracy": round(float(accuracy_score(ys, ps)), 4),
            "macro_f1": round(float(f1_score(ys, ps, average="macro", zero_division=0)), 4),
            "class_dist": {TRAIN_CLASS_NAMES[i]: int((ys == i).sum()) for i in range(2) if int((ys == i).sum()) > 0},
            "available_class_recall": {TRAIN_CLASS_NAMES[i]: round(float(rec_s[i]), 4) for i in range(2) if int(sup_s[i]) > 0},
        }

    return {
        "accuracy": round(float(accuracy_score(y, preds)), 4),
        "macro_f1": round(float(f1_score(y, preds, average="macro", zero_division=0)), 4),
        "weighted_f1": round(float(f1_score(y, preds, average="weighted", zero_division=0)), 4),
        "macro_precision": round(float(precision_score(y, preds, average="macro", zero_division=0)), 4),
        "macro_recall": round(float(recall_score(y, preds, average="macro", zero_division=0)), 4),
        "per_class": per_class,
        "confusion_matrix": cm,
        "prediction_distribution": pred_dist,
        "source_breakdown": src_breakdown,
        "logits": logits,
        "preds": preds,
        "quality_score_mean": float(probs[:, 0].mean()),
    }


def build_dataset_audit(audits: Dict[str, Dict], split_overlap: Dict, out_dir: Path) -> None:
    total_counts = {split: info["n_final"] for split, info in audits.items()}
    audit = {
        "task": "ppg_quality",
        "prepared_public_npz_only": True,
        "live_esp32_max30102_training_used": False,
        "label_mapping": {str(k): v for k, v in LABEL_REMAP.items()},
        "final_classes": TRAIN_CLASS_NAMES,
        "unsupported_or_excluded": {
            "unknown_99": "excluded from supervised training/evaluation",
            "motion_artifact": "no reliable supervised class in current NPZ",
        },
        "splits": audits,
        "split_overlap": split_overlap,
    }
    with open(out_dir / "ppg_quality_dataset_audit.json", "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2)

    lines = [
        "# PPG Quality Dataset Audit",
        "",
        "## Summary",
        "",
        "- Prepared public NPZ used: YES",
        "- Live ESP32/MAX30102 training data used: NO",
        "- Synthetic fallback used: NO",
        "- PPG required: YES",
        "- IMU required: NO, optional context only",
        "- Unknown label 99: excluded",
        "- Motion artifact supervised label: not available in current NPZ",
        "",
        "## NPZ Files",
        "",
        "| Split | Exists | Used samples | NPZ keys | PPG shape | IMU shape | Labels shape |",
        "|---|---|---:|---|---|---|---|",
    ]
    for split, info in audits.items():
        lines.append(
            f"| {split} | {info['npz_exists']} | {info['n_final']:,} | {', '.join(info['npz_keys'])} | "
            f"{info['ppg_shape']} | {info['imu_shape']} | {info['labels_shape']} |"
        )
    lines += [
        "",
        "## Label Mapping",
        "",
        "| Raw label | Label name | Final class index | Training action |",
        "|---:|---|---:|---|",
    ]
    for raw, mapped in LABEL_REMAP.items():
        action = "exclude" if mapped < 0 else "train"
        final = "-" if mapped < 0 else f"{mapped} ({TRAIN_CLASS_NAMES[mapped]})"
        lines.append(f"| {raw} | {RAW_LABEL_NAMES.get(raw, 'unknown')} | {final} | {action} |")
    lines += [
        "",
        "## Split Counts",
        "",
        "| Split | Total NPZ | Bad source removed | Label/unknown excluded | Missing PPG removed | Final used |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for split, info in audits.items():
        lines.append(
            f"| {split} | {info['n_total_in_npz']:,} | {info['n_removed_bad_source']:,} | "
            f"{info['n_removed_bad_label']:,} | {info['n_missing_ppg_removed']:,} | {info['n_final']:,} |"
        )
    for split, info in audits.items():
        lines += [
            "",
            f"## {split.title()} Class Distribution",
            "",
            "| Class | Count | Percent |",
            "|---|---:|---:|",
        ]
        n = max(info["n_final"], 1)
        for cls in TRAIN_CLASS_NAMES:
            cnt = int(info["class_distribution"].get(cls, 0))
            lines.append(f"| {cls} | {cnt:,} | {100.0 * cnt / n:.2f}% |")
        lines += [
            "",
            f"## {split.title()} Source Distribution",
            "",
            "| Source | Count |",
            "|---|---:|",
        ]
        for src, cnt in sorted(info["source_distribution"].items()):
            lines.append(f"| {src} | {cnt:,} |")
        lines += [
            "",
            f"- Sampling rate metadata: {info['sampling_rate_distribution']}",
            f"- Duplicate window IDs within split: {info['duplicate_window_ids']}",
            f"- Unique subjects: {info['unique_subject_count']}",
        ]
    lines += [
        "",
        "## Leakage / Duplicate Check",
        "",
        f"- Train/val window overlap: {split_overlap['train_val_window_overlap']}",
        f"- Train/test window overlap: {split_overlap['train_test_window_overlap']}",
        f"- Val/test window overlap: {split_overlap['val_test_window_overlap']}",
        "",
        f"Audit JSON: `{out_dir / 'ppg_quality_dataset_audit.json'}`",
    ]
    with open(out_dir / "ppg_quality_dataset_audit.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def build_report(
    env_info: Dict,
    audits: Dict[str, Dict],
    norm_stats: Dict,
    history: List[Dict],
    test_metrics: Dict,
    model_params: int,
    train_cfg: Dict,
    best_epoch: int,
    best_val_macro_f1: float,
    out_dir: Path,
) -> str:
    pc = test_metrics["per_class"]
    cm = test_metrics["confusion_matrix"]
    pred_dist = test_metrics["prediction_distribution"]
    pred_total = sum(pred_dist.values())
    n_pred_cls = len([v for v in pred_dist.values() if v > 0])
    dominant_class = max(pred_dist.items(), key=lambda kv: kv[1])[0]
    dominant_ratio = max(pred_dist.values()) / max(pred_total, 1)
    collapse = n_pred_cls < 2 or dominant_ratio > 0.98
    good_bad_learned = pc["good_quality"]["recall"] >= 0.70 and pc["bad_quality"]["recall"] >= 0.50
    if test_metrics["macro_f1"] >= 0.75 and not collapse and good_bad_learned and best_epoch > 0:
        decision = "ACCEPT_PPG_QUALITY_EXPERT"
    elif test_metrics["macro_f1"] >= 0.60 and not collapse and best_epoch > 0:
        decision = "PARTIAL_ACCEPT_LIMITED_USE"
    else:
        decision = "REJECT_RETRAIN_REQUIRED"

    lines = [
        "# PPG Quality Expert Report",
        "",
        "## 1. Executive Summary",
        "",
        f"- Final decision: **{decision}**",
        f"- Model accepted: {'YES' if decision == 'ACCEPT_PPG_QUALITY_EXPERT' else 'LIMITED/NO'}",
        f"- PPG quality learned: {'YES' if good_bad_learned else 'PARTIAL'}",
        f"- Collapse detected: {'YES' if collapse else 'NO'}",
        f"- RiskFusionEngine use: {'normal ppg quality gate' if decision == 'ACCEPT_PPG_QUALITY_EXPERT' else 'limited reliability gate only'}",
        "- Next step: wait for user review before Gait or Vitals",
        "",
        "## 2. Environment Confirmation",
        "",
        f"- sys.executable: `{env_info['sys_executable']}`",
        f"- sys.version: `{env_info['sys_version']}`",
        f"- torch.__version__: `{env_info['torch_version']}`",
        f"- working directory: `{env_info['working_directory']}`",
        "",
        "## 3. Data Source Confirmation",
        "",
        "- Prepared public NPZ: YES",
        "- Synthetic: NO",
        "- Live ESP32/MAX30102 training used: NO",
        "- Train NPZ: `outputs/windowed_dataset/ppg_quality/train.npz`",
        "- Val NPZ: `outputs/windowed_dataset/ppg_quality/val.npz`",
        "- Test NPZ: `outputs/windowed_dataset/ppg_quality/test.npz`",
        "",
        "| Split | Samples used | Sources |",
        "|---|---:|---|",
    ]
    for split, info in audits.items():
        lines.append(f"| {split} | {info['n_final']:,} | {', '.join(sorted(info['source_distribution']))} |")
    lines += [
        "",
        "## 4. NPZ Structure",
        "",
        "| Split | Keys | PPG shape | IMU shape | Features shape | Label shape | Metadata |",
        "|---|---|---|---|---|---|---|",
    ]
    for split, info in audits.items():
        lines.append(f"| {split} | {', '.join(info['npz_keys'])} | {info['ppg_shape']} | {info['imu_shape']} | {info['features_shape']} | {info['labels_shape']} | {info['metadata_present']} |")
    lines += [
        "",
        "## 5. Label Mapping",
        "",
        "| Raw label | Label name | Final class index | Action |",
        "|---:|---|---|---|",
    ]
    for raw, mapped in LABEL_REMAP.items():
        final = "excluded" if mapped < 0 else f"{mapped} ({TRAIN_CLASS_NAMES[mapped]})"
        action = "exclude" if mapped < 0 else "train/evaluate"
        lines.append(f"| {raw} | {RAW_LABEL_NAMES.get(raw, 'unknown')} | {final} | {action} |")
    lines += [
        "",
        "Motion artifact has no reliable supervised label in this NPZ, so this run is a binary good/bad reliability gate.",
        "",
        "## 6. Class Distribution",
    ]
    for split, info in audits.items():
        n = max(info["n_final"], 1)
        counts = info["class_distribution"]
        imbalance = max(counts.values()) / max(min([v for v in counts.values() if v > 0]), 1)
        lines += [
            "",
            f"### {split}",
            "",
            f"Imbalance ratio: {imbalance:.2f}",
            "",
            "| Class | Count | Percent |",
            "|---|---:|---:|",
        ]
        for cls in TRAIN_CLASS_NAMES:
            cnt = int(counts.get(cls, 0))
            lines.append(f"| {cls} | {cnt:,} | {100.0 * cnt / n:.2f}% |")
    lines += [
        "",
        "## 7. Source Breakdown",
    ]
    for split, info in audits.items():
        lines += ["", f"### {split}", "", "| Source | Count | Label support |", "|---|---:|---|"]
        for src, cnt in sorted(info["source_distribution"].items()):
            lines.append(f"| {src} | {cnt:,} | see audit JSON label/source details |")
    lines += [
        "",
        "## 8. Input Normalization",
        "",
        f"- Method: {norm_stats['method']}",
        "- Stats from train split only: YES",
        "- Path: `outputs/hybrid_redesign/ppg_quality_expert/ppg_norm_stats.json`",
        "",
        "| Channel | Mean | Std | Median | IQR |",
        "|---:|---:|---:|---:|---:|",
    ]
    for i, (mean, std, med, iqr) in enumerate(zip(norm_stats["mean_per_channel"], norm_stats["std_per_channel"], norm_stats["median_per_channel"], norm_stats["iqr_per_channel"])):
        lines.append(f"| {i} | {float(mean):.6f} | {float(std):.6f} | {float(med):.6f} | {float(iqr):.6f} |")
    lines += [
        "",
        "## 9. Model Architecture",
        "",
        "- Model class: PPGQualityExpertCNN",
        "- Input shape: `(batch, 1, 200)`",
        f"- Output classes: {', '.join(PPG_QUALITY_CLASSES)}",
        f"- Trained/evaluated classes: {', '.join(TRAIN_CLASS_NAMES)}",
        f"- Parameter count: {model_params:,}",
        f"- Loss: {train_cfg['loss']}",
        f"- Optimizer: {train_cfg['optimizer']}",
        f"- LR: {train_cfg['lr']}",
        f"- Scheduler: {train_cfg['scheduler']}",
        "- Checkpoint metric: validation macro_f1",
        "",
        "## 10. Training Dynamics",
        "",
        "| Epoch | Train loss | Val loss | Val accuracy | Val macro_f1 | n_pred_cls | Checkpoint valid | Best saved |",
        "|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for h in history:
        lines.append(
            f"| {h['epoch']} | {h['train_loss']:.5f} | {h['val_loss']:.5f} | {h['val_accuracy']:.4f} | "
            f"{h['val_macro_f1']:.5f} | {h['n_pred_classes']} | {'YES' if h['checkpoint_valid'] else 'NO'} | {'YES' if h['best_checkpoint_saved'] else 'NO'} |"
        )
    lines += [
        "",
        "## 11. Final Test Metrics",
        "",
        f"- Accuracy: {test_metrics['accuracy']:.4f}",
        f"- Macro F1: {test_metrics['macro_f1']:.4f}",
        f"- Weighted F1: {test_metrics['weighted_f1']:.4f}",
        f"- Macro precision: {test_metrics['macro_precision']:.4f}",
        f"- Macro recall: {test_metrics['macro_recall']:.4f}",
        "",
        "## 12. Per-Class Metrics",
        "",
        "| Class | Precision | Recall | F1 | Support |",
        "|---|---:|---:|---:|---:|",
    ]
    for cls in TRAIN_CLASS_NAMES:
        vals = pc[cls]
        lines.append(f"| {cls} | {vals['precision']:.4f} | {vals['recall']:.4f} | {vals['f1']:.4f} | {vals['support']:,} |")
    lines += [
        "",
        "## 13. Confusion Matrix",
        "",
        "| Actual / Pred | good_quality | bad_quality |",
        "|---|---:|---:|",
        f"| good_quality | {cm[0][0]} | {cm[0][1]} |",
        f"| bad_quality | {cm[1][0]} | {cm[1][1]} |",
        "",
        f"- bad_quality confused as good_quality: {cm[1][0]}",
        f"- good_quality confused as bad_quality: {cm[0][1]}",
        "- motion_artifact: no supervised class in this NPZ",
        "- unknown/no_data: label 99 excluded from supervised training/evaluation",
        "",
        "## 14. Prediction Distribution",
        "",
        "| Class | Predicted count | Predicted percent |",
        "|---|---:|---:|",
    ]
    for cls in TRAIN_CLASS_NAMES:
        cnt = int(pred_dist.get(cls, 0))
        lines.append(f"| {cls} | {cnt:,} | {100.0 * cnt / max(pred_total, 1):.2f}% |")
    lines += [
        "",
        "## 15. Source-Level Evaluation",
        "",
        "| Source | Samples | Accuracy | Macro F1 | Available class recall |",
        "|---|---:|---:|---:|---|",
    ]
    for src, info in sorted(test_metrics["source_breakdown"].items()):
        recalls = ", ".join(f"{k}:{v:.3f}" for k, v in info.get("available_class_recall", {}).items())
        lines.append(f"| {src} | {info['n']:,} | {info['accuracy']:.4f} | {info['macro_f1']:.4f} | {recalls} |")
    lines += [
        "",
        "## 16. Collapse / Dominance Check",
        "",
        f"- n_pred_cls: {n_pred_cls}",
        f"- Dominant predicted class: {dominant_class}",
        f"- Dominant ratio: {dominant_ratio:.4f}",
        f"- Single-class collapse: {'YES' if n_pred_cls < 2 else 'NO'}",
        f"- Majority-class crush: {'YES' if dominant_ratio > 0.98 else 'NO'}",
        "",
        "## 17. Checkpoint Validity",
        "",
        f"- best_model.pt valid: {'YES' if best_epoch > 0 else 'NO'}",
        f"- Best epoch: {best_epoch}",
        f"- Best val macro_f1: {best_val_macro_f1:.5f}",
        "- last_model.pt path: `outputs/hybrid_redesign/ppg_quality_expert/last_model.pt`",
        "- best_model.pt path: `outputs/hybrid_redesign/ppg_quality_expert/best_model.pt`",
        "",
        "## 18. Risk Fusion Integration Note",
        "",
        "- good_quality: vitals contribution normal",
        "- bad_quality: vitals contribution reduced and confidence lowered",
        "- motion_artifact: not separately learned in this run; treat low quality as reduced vitals confidence",
        "- missing PPG: vitals contribution 0 and reason `ppg_missing` should be added",
        "",
        "## 19. Final Decision",
        "",
        f"**{decision}**",
        "",
        "## 20. Recommendation",
        "",
        f"- Gait Instability Expert can start: {'YES, after user review' if decision != 'REJECT_RETRAIN_REQUIRED' else 'NO'}",
        f"- Vitals Context Expert can start: {'YES, after user review' if decision == 'ACCEPT_PPG_QUALITY_EXPERT' else 'NO or wait'}",
        "- Consider binary PPG model: already trained as binary good/bad reliability gate over a 4-logit runtime-compatible head",
        "- Label mapping issue: motion_artifact is not supervised; unknown 99 is excluded",
        "- Extra preprocessing: future iteration may add heuristic motion-artifact labels using IMU/PPG quality features",
    ]
    return "\n".join(lines)


def split_window_ids(split: str) -> set:
    path = WINDOWED_NPZ_DIR / f"{split}.npz"
    raw = np.load(str(path), allow_pickle=True)
    ids = set()
    for m in raw["metadata"]:
        ids.add(str(_parse_meta(m).get("window_id", "")))
    return ids


def clean_output_dir(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "best_model.pt",
        "last_model.pt",
        "metrics.json",
        "training_history.json",
        "confusion_matrix.json",
        "prediction_distribution.json",
        "per_class_metrics.json",
        "source_breakdown.json",
        "ppg_norm_stats.json",
        "ppg_quality_dataset_audit.md",
        "ppg_quality_dataset_audit.json",
        "ppg_quality_expert_report.md",
    ]:
        path = out_dir / name
        if path.exists():
            path.unlink()


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR
    clean_output_dir(out_dir)

    env_info = {
        "sys_executable": sys.executable,
        "sys_version": sys.version.replace("\n", " "),
        "torch_version": torch.__version__,
        "working_directory": str(Path.cwd()),
    }
    log.info("=== PYTHON ENVIRONMENT CONFIRMATION ===")
    for k, v in env_info.items():
        log.info("%s: %s", k, v)
    expected_exe = str(PROJECT_ROOT.parent / ".venv311" / "Scripts" / "python.exe")
    if Path(sys.executable).resolve() != Path(expected_exe).resolve():
        raise RuntimeError(f"Wrong Python executable: {sys.executable}; expected {expected_exe}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else torch.device(args.device)
    allowed, forbidden = load_routing()
    log.info("Allowed datasets for ppg_quality: %s", sorted(allowed))
    log.info("Forbidden datasets: %s", sorted(forbidden))

    if args.smoke:
        log.warning("SMOKE MODE - using synthetic data")
        X_tr, y_tr, src_tr, audit_tr = _make_synthetic(1600, args.seed)
        X_v, y_v, src_v, audit_v = _make_synthetic(400, args.seed + 1)
        X_te, y_te, src_te, audit_te = _make_synthetic(400, args.seed + 2)
        overlap = {"train_val_window_overlap": 0, "train_test_window_overlap": 0, "val_test_window_overlap": 0}
    else:
        log.info("Loading prepared ppg_quality NPZ files...")
        X_tr, y_tr, src_tr, audit_tr = load_ppg_npz("train", allowed, forbidden)
        X_v, y_v, src_v, audit_v = load_ppg_npz("val", allowed, forbidden)
        X_te, y_te, src_te, audit_te = load_ppg_npz("test", allowed, forbidden)
        ids_tr, ids_v, ids_te = split_window_ids("train"), split_window_ids("val"), split_window_ids("test")
        overlap = {
            "train_val_window_overlap": len(ids_tr & ids_v),
            "train_test_window_overlap": len(ids_tr & ids_te),
            "val_test_window_overlap": len(ids_v & ids_te),
        }

    audits = {"train": audit_tr, "val": audit_v, "test": audit_te}
    build_dataset_audit(audits, overlap, out_dir)
    log.info("Dataset audit saved to %s", out_dir / "ppg_quality_dataset_audit.md")
    for split, info in audits.items():
        log.info(
            "[%s] total=%s used=%s classes=%s sources=%s unknown_excluded=%s missing_ppg_removed=%s",
            split,
            info["n_total_in_npz"],
            info["n_final"],
            info["class_distribution"],
            info["source_distribution"],
            info["n_unknown_excluded"],
            info["n_missing_ppg_removed"],
        )
    log.info("Split overlap: %s", overlap)

    norm_stats = compute_norm_stats(X_tr)
    X_tr = apply_norm(X_tr, norm_stats)
    X_v = apply_norm(X_v, norm_stats)
    X_te = apply_norm(X_te, norm_stats)
    with open(out_dir / "ppg_norm_stats.json", "w", encoding="utf-8") as f:
        json.dump(norm_stats, f, indent=2)
    log.info("Saved ppg_norm_stats.json")

    model = build_ppg_quality_expert({"ppg_channels": X_tr.shape[1], "window_length": X_tr.shape[2], "num_classes": NUM_MODEL_CLASSES}).to(device)
    model_params = sum(p.numel() for p in model.parameters())
    log.info("Model: PPGQualityExpertCNN params=%s", f"{model_params:,}")

    class_weights = compute_class_weights(y_tr).to(device)
    log.info("Class weights: %s", {PPG_QUALITY_CLASSES[i]: round(float(class_weights[i]), 4) for i in range(NUM_MODEL_CLASSES)})
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)

    train_loader = DataLoader(TensorDataset(torch.from_numpy(X_tr), torch.from_numpy(y_tr)), batch_size=args.batch_size, shuffle=True, drop_last=False)
    val_loader = DataLoader(TensorDataset(torch.from_numpy(X_v), torch.from_numpy(y_v)), batch_size=args.batch_size, shuffle=False, drop_last=False)

    history: List[Dict] = []
    best_val_macro_f1 = -1.0
    best_epoch = 0
    patience_counter = 0
    t0 = time.time()
    log.info("PPGQualityTrainer epochs=%s batch_size=%s device=%s", args.epochs, args.batch_size, device)

    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            out = model(xb)
            loss = criterion(out["logits"], yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += float(loss.item())
        scheduler.step()
        train_loss /= max(len(train_loader), 1)

        model.eval()
        val_loss = 0.0
        logits_all: List[np.ndarray] = []
        targets_all: List[np.ndarray] = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                out = model(xb)
                val_loss += float(criterion(out["logits"], yb).item())
                logits_all.append(out["logits"].cpu().numpy())
                targets_all.append(yb.cpu().numpy())
        val_loss /= max(len(val_loader), 1)
        logits_np = np.concatenate(logits_all, axis=0)
        targets_np = np.concatenate(targets_all, axis=0)
        preds_np = np.argmax(logits_np[:, :2], axis=1)

        from sklearn.metrics import accuracy_score, f1_score

        val_macro_f1 = float(f1_score(targets_np, preds_np, average="macro", zero_division=0))
        val_weighted_f1 = float(f1_score(targets_np, preds_np, average="weighted", zero_division=0))
        val_accuracy = float(accuracy_score(targets_np, preds_np))
        n_pred_classes = int(len(np.unique(preds_np)))
        ckpt_valid, ckpt_reason = checkpoint_valid(logits_np, targets_np, val_loss)
        improved = ckpt_valid and val_macro_f1 > best_val_macro_f1

        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "val_macro_f1": val_macro_f1,
                "ppg_quality_classes": PPG_QUALITY_CLASSES,
                "trained_classes": TRAIN_CLASS_NAMES,
                "label_remap": LABEL_REMAP,
            },
            out_dir / "last_model.pt",
        )
        if improved:
            best_val_macro_f1 = val_macro_f1
            best_epoch = epoch
            patience_counter = 0
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "val_macro_f1": val_macro_f1,
                    "ppg_quality_classes": PPG_QUALITY_CLASSES,
                    "trained_classes": TRAIN_CLASS_NAMES,
                    "label_remap": LABEL_REMAP,
                },
                out_dir / "best_model.pt",
            )
            tag = "[BEST]"
        else:
            patience_counter += 1
            tag = f"[ok, patience={patience_counter}/{args.patience}]"
            if not ckpt_valid:
                tag = f"[SKIP:{ckpt_reason}]"

        row = {
            "epoch": epoch,
            "train_loss": round(train_loss, 5),
            "val_loss": round(val_loss, 5),
            "val_accuracy": round(val_accuracy, 4),
            "val_macro_f1": round(val_macro_f1, 5),
            "val_weighted_f1": round(val_weighted_f1, 5),
            "n_pred_classes": n_pred_classes,
            "checkpoint_valid": ckpt_valid,
            "checkpoint_reason": ckpt_reason,
            "best_checkpoint_saved": bool(improved),
        }
        history.append(row)
        with open(out_dir / "training_history.json", "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        log.info(
            "Epoch %03d/%d | train_loss=%.4f val_loss=%.4f | macro_f1=%.4f acc=%.4f | n_pred_cls=%d | %s",
            epoch,
            args.epochs,
            train_loss,
            val_loss,
            val_macro_f1,
            val_accuracy,
            n_pred_classes,
            tag,
        )
        if patience_counter >= args.patience and not args.smoke:
            log.info("Early stopping triggered at epoch %d", epoch)
            break

    log.info("Training complete in %.1fs", time.time() - t0)
    best_path = out_dir / "best_model.pt"
    if best_path.exists():
        ckpt = torch.load(str(best_path), map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model_state_dict"])
        log.info("Loaded best_model.pt epoch=%s for test evaluation", best_epoch)
    else:
        log.warning("No valid best_model.pt saved; evaluating last model")

    test_metrics = run_eval(model, X_te, y_te, src_te, device, args.batch_size)
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "accuracy": test_metrics["accuracy"],
                "macro_f1": test_metrics["macro_f1"],
                "weighted_f1": test_metrics["weighted_f1"],
                "macro_precision": test_metrics["macro_precision"],
                "macro_recall": test_metrics["macro_recall"],
                "best_epoch": best_epoch,
                "best_val_macro_f1": round(best_val_macro_f1, 5),
                "ppg_quality_classes": PPG_QUALITY_CLASSES,
                "trained_classes": TRAIN_CLASS_NAMES,
                "label_remap": {str(k): v for k, v in LABEL_REMAP.items()},
            },
            f,
            indent=2,
        )
    with open(out_dir / "confusion_matrix.json", "w", encoding="utf-8") as f:
        json.dump({"labels": TRAIN_CLASS_NAMES, "matrix": test_metrics["confusion_matrix"]}, f, indent=2)
    with open(out_dir / "prediction_distribution.json", "w", encoding="utf-8") as f:
        json.dump(test_metrics["prediction_distribution"], f, indent=2)
    with open(out_dir / "per_class_metrics.json", "w", encoding="utf-8") as f:
        json.dump(test_metrics["per_class"], f, indent=2)
    with open(out_dir / "source_breakdown.json", "w", encoding="utf-8") as f:
        json.dump(test_metrics["source_breakdown"], f, indent=2)

    train_cfg = {
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "optimizer": "AdamW(weight_decay=1e-4)",
        "scheduler": f"CosineAnnealingLR(T_max={args.epochs}, eta_min=1e-5)",
        "loss": "CrossEntropyLoss(mild sqrt inverse class weights)",
        "patience": args.patience,
        "device": str(device),
    }
    report = build_report(env_info, audits, norm_stats, history, test_metrics, model_params, train_cfg, best_epoch, best_val_macro_f1, out_dir)
    with open(out_dir / "ppg_quality_expert_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    log.info("=== PPG Quality Expert Training Complete ===")
    log.info("accuracy=%s macro_f1=%s weighted_f1=%s", test_metrics["accuracy"], test_metrics["macro_f1"], test_metrics["weighted_f1"])
    log.info("best_epoch=%s best_val_macro_f1=%.5f", best_epoch, best_val_macro_f1)
    for cls, vals in test_metrics["per_class"].items():
        log.info("%s precision=%.4f recall=%.4f f1=%.4f support=%s", cls, vals["precision"], vals["recall"], vals["f1"], vals["support"])
    log.info("Output dir: %s", out_dir)


if __name__ == "__main__":
    main()
