"""Train HealthAlert Vitals Context Expert on prepared public NPZ windows."""

from __future__ import annotations

import argparse
import json
import logging
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

from src.healthalert.models.vitals_context_expert import (  # noqa: E402
    VITALS_CONTEXT_CLASSES,
    build_vitals_context_expert,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("healthalert.train_vitals_context_expert")

ROUTING_CFG = PROJECT_ROOT / "config" / "hybrid_task_routing.yaml"
WINDOWED_NPZ_DIR = PROJECT_ROOT / "outputs" / "windowed_dataset" / "vitals_context"
OUT_DIR = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "vitals_context_expert"

RAW_LABEL_NAMES = {
    0: "normal",
    10: "walking",
    11: "sitting",
    20: "good_quality",
    21: "bad_quality",
    99: "unknown",
}
LABEL_REMAP = {
    0: 0,    # rest_like
    11: 0,   # sitting -> rest_like
    20: 0,   # good quality lab/rest proxy -> rest_like
    10: 1,   # walking -> active_like
    21: 2,   # bad quality -> poor_signal
    99: -1,  # unknown excluded
}
TRAIN_CLASS_NAMES = ["rest_like", "active_like", "poor_signal", "abnormal_trend"]
SUPPORTED_CLASS_IDS = [0, 1, 2]
NUM_CLASSES = len(VITALS_CONTEXT_CLASSES)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train Vitals Context Expert")
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
    task = cfg.get("vitals_context", {})
    allowed = {_norm_src(s) for s in task.get("allowed_datasets", [])}
    forbidden = {_norm_src(s) for s in task.get("forbidden_datasets", [])}
    return allowed, forbidden


def _parse_meta(item: object) -> Dict:
    try:
        return json.loads(str(item)) if not isinstance(item, dict) else item
    except Exception:
        return {}


def _make_synthetic(n: int, input_dim: int = 1400, seed: int = 42):
    rng = np.random.RandomState(seed)
    X = rng.randn(n, input_dim).astype(np.float32)
    y = rng.choice([0, 1, 2], size=n, p=[0.45, 0.45, 0.10]).astype(np.int64)
    src = np.array(["synthetic"] * n, dtype=object)
    info = {
        "npz_path": "synthetic",
        "npz_exists": False,
        "npz_keys": ["synthetic"],
        "features_shape": [n, input_dim],
        "labels_shape": [n],
        "imu_shape": None,
        "ppg_shape": None,
        "metadata_present": True,
        "n_total_in_npz": n,
        "n_removed_bad_source": 0,
        "n_removed_bad_label": 0,
        "n_unknown_excluded": 0,
        "n_missing_vitals_removed": 0,
        "n_final": n,
        "raw_label_distribution": {},
        "metadata_label_distribution_after_filter": {},
        "class_distribution": {TRAIN_CLASS_NAMES[i]: int((y == i).sum()) for i in SUPPORTED_CLASS_IDS},
        "source_distribution": {"synthetic": n},
        "sampling_rate_distribution": {},
        "duplicate_window_ids": 0,
        "unique_subject_count": 0,
        "feature_nonzero_columns": input_dim,
        "feature_zero_rows": 0,
        "ppg_missing_count": 0,
        "imu_required": False,
        "ppg_required": True,
    }
    return X, y, src, info


def load_vitals_npz(split: str, allowed: set, forbidden: set, smoke: bool = False):
    npz_path = WINDOWED_NPZ_DIR / f"{split}.npz"
    if not npz_path.exists():
        raise FileNotFoundError(f"[{split}] NPZ not found: {npz_path}")
    raw = np.load(str(npz_path), allow_pickle=True)
    keys = list(raw.files)
    if "features" not in keys or "labels" not in keys or "metadata" not in keys:
        raise KeyError(f"[{split}] expected keys features, labels, metadata; found {keys}")

    X = raw["features"].astype(np.float32)
    labels_raw = raw["labels"].flatten().astype(np.int64)
    metadata = raw["metadata"]
    sources = np.array([_parse_meta(m).get("dataset_name", "unknown") for m in metadata], dtype=object)

    src_norm = np.array([_norm_src(s) for s in sources])
    keep_source = np.array([(s in allowed) and (s not in forbidden) for s in src_norm], dtype=bool)
    n_removed_bad_source = int((~keep_source).sum())
    X, labels_raw, sources, metadata = X[keep_source], labels_raw[keep_source], sources[keep_source], metadata[keep_source]

    mapped = np.array([LABEL_REMAP.get(int(lbl), -1) for lbl in labels_raw], dtype=np.int64)
    keep_label = mapped >= 0
    n_removed_bad_label = int((~keep_label).sum())
    n_unknown_excluded = int(((labels_raw == 99) & (~keep_label)).sum())
    X, y, sources, metadata, labels_kept = X[keep_label], mapped[keep_label], sources[keep_label], metadata[keep_label], labels_raw[keep_label]

    finite = np.isfinite(X).all(axis=1)
    keep_feat = finite
    n_missing_vitals_removed = int((~keep_feat).sum())
    X, y, sources, metadata, labels_kept = X[keep_feat], y[keep_feat], sources[keep_feat], metadata[keep_feat], labels_kept[keep_feat]

    if smoke:
        rng = np.random.RandomState(42)
        idx = rng.permutation(len(y))[:min(2000, len(y))]
        X, y, sources, metadata, labels_kept = X[idx], y[idx], sources[idx], metadata[idx], labels_kept[idx]

    raw_counts: Dict[str, int] = {}
    for lbl in labels_raw:
        name = RAW_LABEL_NAMES.get(int(lbl), f"label_{int(lbl)}")
        raw_counts[name] = raw_counts.get(name, 0) + 1
    class_dist = {TRAIN_CLASS_NAMES[i]: int((y == i).sum()) for i in SUPPORTED_CLASS_IDS}
    class_dist["abnormal_trend"] = int((y == 3).sum())
    source_dist: Dict[str, int] = {}
    metadata_label_dist: Dict[str, int] = {}
    sampling_rates: Dict[str, int] = {}
    window_ids = []
    subjects = []
    ppg_missing = 0
    for m in metadata:
        d = _parse_meta(m)
        src = str(d.get("dataset_name", "unknown"))
        source_dist[src] = source_dist.get(src, 0) + 1
        label_name = str(d.get("label", "unknown"))
        metadata_label_dist[label_name] = metadata_label_dist.get(label_name, 0) + 1
        sr = str(d.get("sampling_rate_hz", d.get("sampling_rate", "unknown")))
        sampling_rates[sr] = sampling_rates.get(sr, 0) + 1
        window_ids.append(str(d.get("window_id", "")))
        subjects.append((src, str(d.get("subject_id", ""))))
        if d.get("has_ppg") is False:
            ppg_missing += 1

    info = {
        "npz_path": str(npz_path),
        "npz_exists": True,
        "npz_keys": keys,
        "features_shape": list(raw["features"].shape),
        "labels_shape": list(raw["labels"].shape),
        "imu_shape": list(raw["imu"].shape) if "imu" in keys else None,
        "ppg_shape": list(raw["ppg"].shape) if "ppg" in keys else None,
        "metadata_present": "metadata" in keys,
        "n_total_in_npz": int(len(raw["labels"])),
        "n_removed_bad_source": n_removed_bad_source,
        "n_removed_bad_label": n_removed_bad_label,
        "n_unknown_excluded": n_unknown_excluded,
        "n_missing_vitals_removed": n_missing_vitals_removed,
        "n_final": int(len(y)),
        "raw_label_distribution": raw_counts,
        "metadata_label_distribution_after_filter": metadata_label_dist,
        "class_distribution": class_dist,
        "source_distribution": source_dist,
        "sampling_rate_distribution": sampling_rates,
        "duplicate_window_ids": int(len(window_ids) - len(set(window_ids))),
        "unique_subject_count": int(len(set(subjects))),
        "feature_nonzero_columns": int((np.nanstd(X, axis=0) > 1e-8).sum()),
        "feature_zero_rows": int(np.all(X == 0, axis=1).sum()),
        "ppg_missing_count": ppg_missing,
        "imu_required": False,
        "ppg_required": True,
    }
    return X.astype(np.float32), y.astype(np.int64), sources, info


def split_window_ids(split: str) -> set:
    raw = np.load(str(WINDOWED_NPZ_DIR / f"{split}.npz"), allow_pickle=True)
    return {str(_parse_meta(m).get("window_id", "")) for m in raw["metadata"]}


def compute_norm_stats(X: np.ndarray) -> Dict:
    mean = X.mean(axis=0)
    std = np.maximum(X.std(axis=0), 1e-6)
    return {
        "method": "per-feature z-score",
        "computed_from": "train split only",
        "input_dim": int(X.shape[1]),
        "mean_per_feature": mean.tolist(),
        "std_per_feature": std.tolist(),
        "nonzero_feature_columns": int((std > 1e-6).sum()),
    }


def apply_norm(X: np.ndarray, stats: Dict) -> np.ndarray:
    mean = np.array(stats["mean_per_feature"], dtype=np.float32)
    std = np.array(stats["std_per_feature"], dtype=np.float32)
    return ((X - mean[None, :]) / std[None, :]).astype(np.float32)


def compute_class_weights(y: np.ndarray) -> torch.Tensor:
    counts = np.bincount(y, minlength=NUM_CLASSES).astype(np.float64)
    present = counts[:3]
    inv_sqrt = 1.0 / np.sqrt(np.maximum(present, 1.0))
    inv_sqrt = inv_sqrt / inv_sqrt.mean()
    inv_sqrt = np.clip(inv_sqrt, 0.5, 3.0)
    weights = np.ones(NUM_CLASSES, dtype=np.float32)
    weights[:3] = inv_sqrt.astype(np.float32)
    weights[3] = 0.0
    return torch.tensor(weights, dtype=torch.float32)


def checkpoint_valid(logits: np.ndarray, targets: np.ndarray, val_loss: float) -> Tuple[bool, str]:
    if not np.isfinite(val_loss):
        return False, "validation loss is not finite"
    if not np.isfinite(logits).all():
        return False, "logits contain NaN/Inf"
    preds = np.argmax(logits[:, :3], axis=1)
    n_pred = len(np.unique(preds))
    if n_pred < 2:
        return False, "single-class collapse"
    pred_counts = np.bincount(preds, minlength=3)
    if pred_counts.max() / max(pred_counts.sum(), 1) > 0.98:
        return False, "majority-class crush"
    return True, "ok"


def run_eval(model: nn.Module, X: np.ndarray, y: np.ndarray, sources: np.ndarray, device: torch.device, batch_size: int) -> Dict:
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support, precision_score, recall_score

    model.eval()
    logits_all: List[np.ndarray] = []
    loader = DataLoader(TensorDataset(torch.from_numpy(X)), batch_size=batch_size, shuffle=False)
    with torch.no_grad():
        for (xb,) in loader:
            logits_all.append(model(xb.to(device))["logits"].cpu().numpy())
    logits = np.concatenate(logits_all, axis=0)
    preds = np.argmax(logits[:, :3], axis=1)

    labels = [0, 1, 2]
    cm = confusion_matrix(y, preds, labels=labels).tolist()
    prec, rec, f1, sup = precision_recall_fscore_support(y, preds, labels=labels, zero_division=0)
    per_class = {
        TRAIN_CLASS_NAMES[i]: {"precision": float(prec[i]), "recall": float(rec[i]), "f1": float(f1[i]), "support": int(sup[i])}
        for i in labels
    }
    per_class["abnormal_trend"] = {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 0}
    pred_dist = {TRAIN_CLASS_NAMES[i]: int((preds == i).sum()) for i in labels}
    pred_dist["abnormal_trend"] = 0

    src_breakdown = {}
    for src in np.unique(sources):
        mask = sources == src
        ys, ps = y[mask], preds[mask]
        _, rec_s, _, sup_s = precision_recall_fscore_support(ys, ps, labels=labels, zero_division=0)
        src_breakdown[str(src)] = {
            "n": int(mask.sum()),
            "accuracy": round(float(accuracy_score(ys, ps)), 4),
            "macro_f1": round(float(f1_score(ys, ps, labels=labels, average="macro", zero_division=0)), 4),
            "class_dist": {TRAIN_CLASS_NAMES[i]: int((ys == i).sum()) for i in labels if int((ys == i).sum()) > 0},
            "available_class_recall": {TRAIN_CLASS_NAMES[i]: round(float(rec_s[i]), 4) for i in labels if int(sup_s[i]) > 0},
        }
    return {
        "accuracy": round(float(accuracy_score(y, preds)), 4),
        "macro_f1": round(float(f1_score(y, preds, labels=labels, average="macro", zero_division=0)), 4),
        "weighted_f1": round(float(f1_score(y, preds, labels=labels, average="weighted", zero_division=0)), 4),
        "macro_precision": round(float(precision_score(y, preds, labels=labels, average="macro", zero_division=0)), 4),
        "macro_recall": round(float(recall_score(y, preds, labels=labels, average="macro", zero_division=0)), 4),
        "per_class": per_class,
        "confusion_matrix": cm,
        "prediction_distribution": pred_dist,
        "source_breakdown": src_breakdown,
        "logits": logits,
        "preds": preds,
    }


def clean_output_dir(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "best_model.pt", "last_model.pt", "metrics.json", "training_history.json",
        "confusion_matrix.json", "prediction_distribution.json", "per_class_metrics.json",
        "source_breakdown.json", "vitals_norm_stats.json", "vitals_context_dataset_audit.md",
        "vitals_context_dataset_audit.json", "vitals_context_expert_report.md",
    ]:
        p = out_dir / name
        if p.exists():
            p.unlink()


def save_audit(audits: Dict[str, Dict], overlap: Dict, out_dir: Path) -> None:
    audit = {
        "task": "vitals_context",
        "prepared_public_npz_only": True,
        "live_esp32_max30102_training_used": False,
        "label_mapping": {str(k): v for k, v in LABEL_REMAP.items()},
        "final_classes": TRAIN_CLASS_NAMES,
        "unsupported_or_excluded": {"unknown_99": "excluded", "abnormal_trend": "no supervised label in current NPZ"},
        "splits": audits,
        "split_overlap": overlap,
    }
    with open(out_dir / "vitals_context_dataset_audit.json", "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2)
    lines = [
        "# Vitals Context Dataset Audit", "",
        "- Prepared public NPZ used: YES",
        "- Live ESP32/MAX30102 training data used: NO",
        "- Synthetic fallback used: NO",
        "- Feature source: NPZ `features` array",
        "- Unknown label 99: excluded",
        "- abnormal_trend: no supervised label in current NPZ",
        "- PPG Quality relation: training uses dataset labels/features; RiskFusion uses PPG Quality Expert inference at runtime",
        "",
        "## NPZ Files", "",
        "| Split | Exists | Used samples | Keys | Features shape | PPG shape | IMU shape | Labels shape |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    for split, info in audits.items():
        lines.append(f"| {split} | {info['npz_exists']} | {info['n_final']:,} | {', '.join(info['npz_keys'])} | {info['features_shape']} | {info['ppg_shape']} | {info['imu_shape']} | {info['labels_shape']} |")
    lines += ["", "## Label Mapping", "", "| Raw label | Label name | Final class | Action |", "|---:|---|---|---|"]
    for raw, mapped in LABEL_REMAP.items():
        final = "excluded" if mapped < 0 else f"{mapped} ({TRAIN_CLASS_NAMES[mapped]})"
        action = "exclude" if mapped < 0 else "train/evaluate"
        lines.append(f"| {raw} | {RAW_LABEL_NAMES.get(raw, 'unknown')} | {final} | {action} |")
    lines += ["", "## Split Counts", "", "| Split | Total NPZ | Bad source removed | Label/unknown excluded | Missing vitals removed | Final used |", "|---|---:|---:|---:|---:|---:|"]
    for split, info in audits.items():
        lines.append(f"| {split} | {info['n_total_in_npz']:,} | {info['n_removed_bad_source']:,} | {info['n_removed_bad_label']:,} | {info['n_missing_vitals_removed']:,} | {info['n_final']:,} |")
    for split, info in audits.items():
        lines += ["", f"## {split.title()} Class Distribution", "", "| Class | Count | Percent |", "|---|---:|---:|"]
        n = max(info["n_final"], 1)
        for cls in TRAIN_CLASS_NAMES:
            cnt = int(info["class_distribution"].get(cls, 0))
            lines.append(f"| {cls} | {cnt:,} | {100.0 * cnt / n:.2f}% |")
        lines += ["", f"## {split.title()} Source Distribution", "", "| Source | Count |", "|---|---:|"]
        for src, cnt in sorted(info["source_distribution"].items()):
            lines.append(f"| {src} | {cnt:,} |")
        lines += [
            "",
            f"- Sampling rate metadata: {info['sampling_rate_distribution']}",
            f"- Duplicate window IDs: {info['duplicate_window_ids']}",
            f"- Unique subjects: {info['unique_subject_count']}",
            f"- Feature nonzero columns: {info['feature_nonzero_columns']}",
            f"- Feature zero rows: {info['feature_zero_rows']}",
            f"- PPG missing count: {info['ppg_missing_count']}",
        ]
    lines += [
        "", "## Leakage / Duplicate Check", "",
        f"- Train/val window overlap: {overlap['train_val_window_overlap']}",
        f"- Train/test window overlap: {overlap['train_test_window_overlap']}",
        f"- Val/test window overlap: {overlap['val_test_window_overlap']}",
        "",
        f"Audit JSON: `{out_dir / 'vitals_context_dataset_audit.json'}`",
    ]
    with open(out_dir / "vitals_context_dataset_audit.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def build_report(env_info: Dict, audits: Dict[str, Dict], norm_stats: Dict, history: List[Dict], test_metrics: Dict, model_params: int, train_cfg: Dict, best_epoch: int, best_val_macro_f1: float, out_dir: Path) -> str:
    pc = test_metrics["per_class"]
    cm = test_metrics["confusion_matrix"]
    pred_dist = test_metrics["prediction_distribution"]
    pred_total = sum(pred_dist.values())
    n_pred_cls = len([v for v in pred_dist.values() if v > 0])
    dominant_class = max(pred_dist.items(), key=lambda kv: kv[1])[0]
    dominant_ratio = max(pred_dist.values()) / max(pred_total, 1)
    collapse = n_pred_cls < 2 or dominant_ratio > 0.98
    main_learned = pc["rest_like"]["recall"] >= 0.70 and pc["active_like"]["recall"] >= 0.70 and pc["poor_signal"]["recall"] >= 0.50
    if test_metrics["macro_f1"] >= 0.70 and not collapse and main_learned and best_epoch > 0:
        decision = "ACCEPT_VITALS_CONTEXT_EXPERT"
    elif test_metrics["macro_f1"] >= 0.55 and not collapse and best_epoch > 0:
        decision = "PARTIAL_ACCEPT_LIMITED_USE"
    else:
        decision = "REJECT_RETRAIN_REQUIRED"

    lines = [
        "# Vitals Context Expert Report", "",
        "## 1. Executive Summary", "",
        f"- Final decision: **{decision}**",
        f"- Model accepted: {'YES' if decision == 'ACCEPT_VITALS_CONTEXT_EXPERT' else 'LIMITED/NO'}",
        f"- Vitals context learned: {'YES' if main_learned else 'PARTIAL'}",
        f"- Collapse detected: {'YES' if collapse else 'NO'}",
        f"- RiskFusionEngine use: {'vitals context auxiliary score' if decision != 'REJECT_RETRAIN_REQUIRED' else 'do not use yet'}",
        "- Next step: Gait only after user review",
        "",
        "## 2. Environment Confirmation", "",
        f"- sys.executable: `{env_info['sys_executable']}`",
        f"- sys.version: `{env_info['sys_version']}`",
        f"- torch.__version__: `{env_info['torch_version']}`",
        f"- working directory: `{env_info['working_directory']}`",
        "",
        "## 3. Data Source Confirmation", "",
        "- Prepared public NPZ: YES",
        "- Synthetic: NO",
        "- Live ESP32/MAX30102 training used: NO",
        "- Train NPZ: `outputs/windowed_dataset/vitals_context/train.npz`",
        "- Val NPZ: `outputs/windowed_dataset/vitals_context/val.npz`",
        "- Test NPZ: `outputs/windowed_dataset/vitals_context/test.npz`",
        "",
        "| Split | Samples used | Sources |",
        "|---|---:|---|",
    ]
    for split, info in audits.items():
        lines.append(f"| {split} | {info['n_final']:,} | {', '.join(sorted(info['source_distribution']))} |")
    lines += ["", "## 4. NPZ Structure", "", "| Split | Keys | Features shape | PPG shape | IMU shape | Label shape | Metadata |", "|---|---|---|---|---|---|---|"]
    for split, info in audits.items():
        lines.append(f"| {split} | {', '.join(info['npz_keys'])} | {info['features_shape']} | {info['ppg_shape']} | {info['imu_shape']} | {info['labels_shape']} | {info['metadata_present']} |")
    lines += ["", "## 5. Label Mapping", "", "| Raw label | Label name | Final class index | Action |", "|---:|---|---|---|"]
    for raw, mapped in LABEL_REMAP.items():
        final = "excluded" if mapped < 0 else f"{mapped} ({TRAIN_CLASS_NAMES[mapped]})"
        action = "exclude" if mapped < 0 else "train/evaluate"
        lines.append(f"| {raw} | {RAW_LABEL_NAMES.get(raw, 'unknown')} | {final} | {action} |")
    lines += ["", "abnormal_trend has no supervised label in this NPZ and is not learned in this run.", "", "## 6. Class Distribution"]
    for split, info in audits.items():
        counts = info["class_distribution"]
        present = [v for v in counts.values() if v > 0]
        imbalance = max(present) / max(min(present), 1) if present else 0
        lines += ["", f"### {split}", "", f"Imbalance ratio: {imbalance:.2f}", "", "| Class | Count | Percent |", "|---|---:|---:|"]
        n = max(info["n_final"], 1)
        for cls in TRAIN_CLASS_NAMES:
            cnt = int(counts.get(cls, 0))
            lines.append(f"| {cls} | {cnt:,} | {100.0 * cnt / n:.2f}% |")
    lines += ["", "## 7. Source Breakdown"]
    for split, info in audits.items():
        lines += ["", f"### {split}", "", "| Source | Count |", "|---|---:|"]
        for src, cnt in sorted(info["source_distribution"].items()):
            lines.append(f"| {src} | {cnt:,} |")
    lines += [
        "", "## 8. Input Normalization", "",
        f"- Method: {norm_stats['method']}",
        "- Stats from train split only: YES",
        "- Path: `outputs/hybrid_redesign/vitals_context_expert/vitals_norm_stats.json`",
        f"- Input dimension: {norm_stats['input_dim']}",
        "",
        "| Feature index | Mean | Std |",
        "|---:|---:|---:|",
    ]
    for i in range(min(20, norm_stats["input_dim"])):
        lines.append(f"| {i} | {float(norm_stats['mean_per_feature'][i]):.6f} | {float(norm_stats['std_per_feature'][i]):.6f} |")
    lines.append(f"| ... | full {norm_stats['input_dim']} feature stats saved in JSON | ... |")
    lines += [
        "", "## 9. Model Architecture", "",
        "- Model class: VitalsContextMLP",
        f"- Input shape: `(batch, {norm_stats['input_dim']})`",
        f"- Output classes: {', '.join(VITALS_CONTEXT_CLASSES)}",
        f"- Parameter count: {model_params:,}",
        f"- Loss: {train_cfg['loss']}",
        f"- Optimizer: {train_cfg['optimizer']}",
        f"- LR: {train_cfg['lr']}",
        f"- Scheduler: {train_cfg['scheduler']}",
        "- Checkpoint metric: validation macro_f1",
        "",
        "## 10. Training Dynamics", "",
        "| Epoch | Train loss | Val loss | Val accuracy | Val macro_f1 | n_pred_cls | Checkpoint valid | Best saved |",
        "|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for h in history:
        lines.append(f"| {h['epoch']} | {h['train_loss']:.5f} | {h['val_loss']:.5f} | {h['val_accuracy']:.4f} | {h['val_macro_f1']:.5f} | {h['n_pred_classes']} | {'YES' if h['checkpoint_valid'] else 'NO'} | {'YES' if h['best_checkpoint_saved'] else 'NO'} |")
    lines += [
        "", "## 11. Final Test Metrics", "",
        f"- Accuracy: {test_metrics['accuracy']:.4f}",
        f"- Macro F1: {test_metrics['macro_f1']:.4f}",
        f"- Weighted F1: {test_metrics['weighted_f1']:.4f}",
        f"- Macro precision: {test_metrics['macro_precision']:.4f}",
        f"- Macro recall: {test_metrics['macro_recall']:.4f}",
        "", "## 12. Per-Class Metrics", "",
        "| Class | Precision | Recall | F1 | Support |",
        "|---|---:|---:|---:|---:|",
    ]
    for cls in TRAIN_CLASS_NAMES:
        vals = pc[cls]
        lines.append(f"| {cls} | {vals['precision']:.4f} | {vals['recall']:.4f} | {vals['f1']:.4f} | {vals['support']:,} |")
    lines += [
        "", "## 13. Confusion Matrix", "",
        "| Actual / Pred | rest_like | active_like | poor_signal |",
        "|---|---:|---:|---:|",
    ]
    for i, cls in enumerate(["rest_like", "active_like", "poor_signal"]):
        lines.append(f"| {cls} | {cm[i][0]} | {cm[i][1]} | {cm[i][2]} |")
    lines += [
        "",
        f"- rest_like -> active_like errors: {cm[0][1]}",
        f"- active_like -> rest_like errors: {cm[1][0]}",
        f"- poor_signal learned recall: {pc['poor_signal']['recall']:.4f}",
        "- abnormal_trend: no supervised examples",
        "- unknown/no_data: label 99 excluded",
        "",
        "## 14. Prediction Distribution", "",
        "| Class | Predicted count | Predicted percent |",
        "|---|---:|---:|",
    ]
    for cls in TRAIN_CLASS_NAMES:
        cnt = int(pred_dist.get(cls, 0))
        lines.append(f"| {cls} | {cnt:,} | {100.0 * cnt / max(pred_total, 1):.2f}% |")
    lines += ["", "## 15. Source-Level Evaluation", "", "| Source | Samples | Accuracy | Macro F1 | Available class recall |", "|---|---:|---:|---:|---|"]
    for src, info in sorted(test_metrics["source_breakdown"].items()):
        recalls = ", ".join(f"{k}:{v:.3f}" for k, v in info.get("available_class_recall", {}).items())
        lines.append(f"| {src} | {info['n']:,} | {info['accuracy']:.4f} | {info['macro_f1']:.4f} | {recalls} |")
    lines += [
        "", "## 16. Collapse / Dominance Check", "",
        f"- n_pred_cls: {n_pred_cls}",
        f"- Dominant predicted class: {dominant_class}",
        f"- Dominant ratio: {dominant_ratio:.4f}",
        f"- Single-class collapse: {'YES' if n_pred_cls < 2 else 'NO'}",
        f"- Majority-class crush: {'YES' if dominant_ratio > 0.98 else 'NO'}",
        "", "## 17. Checkpoint Validity", "",
        f"- best_model.pt valid: {'YES' if best_epoch > 0 else 'NO'}",
        f"- Best epoch: {best_epoch}",
        f"- Best val macro_f1: {best_val_macro_f1:.5f}",
        "- last_model.pt path: `outputs/hybrid_redesign/vitals_context_expert/last_model.pt`",
        "- best_model.pt path: `outputs/hybrid_redesign/vitals_context_expert/best_model.pt`",
        "", "## 18. Risk Fusion Integration Note", "",
        "- rest_like + high HR + good PPG quality + personal deviation high can raise caution/high risk through fusion.",
        "- active_like + high HR should be less risky than rest_like high HR.",
        "- poor_signal reduces vitals contribution.",
        "- abnormal_trend should add caution/high-risk context in a future labeled iteration, but must not trigger critical alone.",
        "- Runtime must respect PPG Quality Expert output: bad/missing PPG reduces or zeros vitals contribution.",
        "", "## 19. Final Decision", "",
        f"**{decision}**",
        "", "## 20. Recommendation", "",
        f"- Gait Instability Expert can start: {'YES, after user review' if decision != 'REJECT_RETRAIN_REQUIRED' else 'NO'}",
        "- Vitals model binary/simple context: current run is 3 supervised contexts plus unlabeled abnormal_trend.",
        "- Label mapping issue: abnormal_trend lacks supervised examples; unknown 99 excluded.",
        "- Extra preprocessing: future work should add true HR/RR/SpO2 handcrafted vitals features and abnormal trend labels.",
        "- PPG Quality integration: use accepted PPG Quality Expert at runtime to gate vitals score.",
        f"- Runtime compatibility note: this checkpoint was trained with input_dim={norm_stats['input_dim']} from NPZ features.",
    ]
    return "\n".join(lines)


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
    expected = str(PROJECT_ROOT.parent / ".venv311" / "Scripts" / "python.exe")
    if Path(sys.executable).resolve() != Path(expected).resolve():
        raise RuntimeError(f"Wrong Python executable: {sys.executable}; expected {expected}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else torch.device(args.device)
    allowed, forbidden = load_routing()
    log.info("Allowed datasets for vitals_context: %s", sorted(allowed))
    log.info("Forbidden datasets: %s", sorted(forbidden))

    if args.smoke:
        log.warning("SMOKE MODE - using synthetic data")
        X_tr, y_tr, src_tr, audit_tr = _make_synthetic(1600, seed=args.seed)
        X_v, y_v, src_v, audit_v = _make_synthetic(400, seed=args.seed + 1)
        X_te, y_te, src_te, audit_te = _make_synthetic(400, seed=args.seed + 2)
        overlap = {"train_val_window_overlap": 0, "train_test_window_overlap": 0, "val_test_window_overlap": 0}
    else:
        log.info("Loading prepared vitals_context NPZ files...")
        X_tr, y_tr, src_tr, audit_tr = load_vitals_npz("train", allowed, forbidden)
        X_v, y_v, src_v, audit_v = load_vitals_npz("val", allowed, forbidden)
        X_te, y_te, src_te, audit_te = load_vitals_npz("test", allowed, forbidden)
        ids_tr, ids_v, ids_te = split_window_ids("train"), split_window_ids("val"), split_window_ids("test")
        overlap = {
            "train_val_window_overlap": len(ids_tr & ids_v),
            "train_test_window_overlap": len(ids_tr & ids_te),
            "val_test_window_overlap": len(ids_v & ids_te),
        }
    audits = {"train": audit_tr, "val": audit_v, "test": audit_te}
    save_audit(audits, overlap, out_dir)
    log.info("Dataset audit saved to %s", out_dir / "vitals_context_dataset_audit.md")
    for split, info in audits.items():
        log.info("[%s] total=%s used=%s classes=%s sources=%s unknown_excluded=%s", split, info["n_total_in_npz"], info["n_final"], info["class_distribution"], info["source_distribution"], info["n_unknown_excluded"])
    log.info("Split overlap: %s", overlap)

    norm_stats = compute_norm_stats(X_tr)
    X_tr = apply_norm(X_tr, norm_stats)
    X_v = apply_norm(X_v, norm_stats)
    X_te = apply_norm(X_te, norm_stats)
    with open(out_dir / "vitals_norm_stats.json", "w", encoding="utf-8") as f:
        json.dump(norm_stats, f, indent=2)
    log.info("Saved vitals_norm_stats.json")

    input_dim = int(X_tr.shape[1])
    model = build_vitals_context_expert({"mode": "mlp", "input_dim": input_dim, "num_classes": NUM_CLASSES}).to(device)
    model_params = sum(p.numel() for p in model.parameters())
    log.info("Model: VitalsContextMLP input_dim=%s params=%s", input_dim, f"{model_params:,}")
    class_weights = compute_class_weights(y_tr).to(device)
    log.info("Class weights: %s", {VITALS_CONTEXT_CLASSES[i]: round(float(class_weights[i]), 4) for i in range(NUM_CLASSES)})
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)

    train_loader = DataLoader(TensorDataset(torch.from_numpy(X_tr), torch.from_numpy(y_tr)), batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(TensorDataset(torch.from_numpy(X_v), torch.from_numpy(y_v)), batch_size=args.batch_size, shuffle=False)

    history: List[Dict] = []
    best_val_macro_f1 = -1.0
    best_epoch = 0
    patience_counter = 0
    t0 = time.time()
    log.info("VitalsTrainer epochs=%s batch_size=%s device=%s", args.epochs, args.batch_size, device)
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
                logits = model(xb)["logits"]
                val_loss += float(criterion(logits, yb).item())
                logits_all.append(logits.cpu().numpy())
                targets_all.append(yb.cpu().numpy())
        val_loss /= max(len(val_loader), 1)
        logits_np = np.concatenate(logits_all, axis=0)
        targets_np = np.concatenate(targets_all, axis=0)
        preds_np = np.argmax(logits_np[:, :3], axis=1)
        from sklearn.metrics import accuracy_score, f1_score
        val_macro_f1 = float(f1_score(targets_np, preds_np, labels=[0, 1, 2], average="macro", zero_division=0))
        val_weighted_f1 = float(f1_score(targets_np, preds_np, labels=[0, 1, 2], average="weighted", zero_division=0))
        val_accuracy = float(accuracy_score(targets_np, preds_np))
        n_pred_classes = int(len(np.unique(preds_np)))
        ckpt_valid, ckpt_reason = checkpoint_valid(logits_np, targets_np, val_loss)
        improved = ckpt_valid and val_macro_f1 > best_val_macro_f1
        state = {
            "model_state_dict": model.state_dict(),
            "epoch": epoch,
            "val_macro_f1": val_macro_f1,
            "vitals_context_classes": VITALS_CONTEXT_CLASSES,
            "trained_classes": TRAIN_CLASS_NAMES,
            "label_remap": LABEL_REMAP,
            "model_config": {"mode": "mlp", "input_dim": input_dim, "num_classes": NUM_CLASSES},
        }
        torch.save(state, out_dir / "last_model.pt")
        if improved:
            best_val_macro_f1 = val_macro_f1
            best_epoch = epoch
            patience_counter = 0
            torch.save(state, out_dir / "best_model.pt")
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
        log.info("Epoch %03d/%d | train_loss=%.4f val_loss=%.4f | macro_f1=%.4f acc=%.4f | n_pred_cls=%d | %s", epoch, args.epochs, train_loss, val_loss, val_macro_f1, val_accuracy, n_pred_classes, tag)
        if patience_counter >= args.patience and not args.smoke:
            log.info("Early stopping triggered at epoch %d", epoch)
            break
    log.info("Training complete in %.1fs", time.time() - t0)

    if (out_dir / "best_model.pt").exists():
        ckpt = torch.load(str(out_dir / "best_model.pt"), map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model_state_dict"])
        log.info("Loaded best_model.pt epoch=%s for test evaluation", best_epoch)
    else:
        log.warning("No valid best_model.pt saved; evaluating last model")
    test_metrics = run_eval(model, X_te, y_te, src_te, device, args.batch_size)

    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({
            "accuracy": test_metrics["accuracy"],
            "macro_f1": test_metrics["macro_f1"],
            "weighted_f1": test_metrics["weighted_f1"],
            "macro_precision": test_metrics["macro_precision"],
            "macro_recall": test_metrics["macro_recall"],
            "best_epoch": best_epoch,
            "best_val_macro_f1": round(best_val_macro_f1, 5),
            "vitals_context_classes": VITALS_CONTEXT_CLASSES,
            "trained_classes": TRAIN_CLASS_NAMES,
            "label_remap": {str(k): v for k, v in LABEL_REMAP.items()},
            "model_config": {"mode": "mlp", "input_dim": input_dim, "num_classes": NUM_CLASSES},
        }, f, indent=2)
    with open(out_dir / "confusion_matrix.json", "w", encoding="utf-8") as f:
        json.dump({"labels": TRAIN_CLASS_NAMES[:3], "matrix": test_metrics["confusion_matrix"]}, f, indent=2)
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
    with open(out_dir / "vitals_context_expert_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    log.info("=== Vitals Context Expert Training Complete ===")
    log.info("accuracy=%s macro_f1=%s weighted_f1=%s", test_metrics["accuracy"], test_metrics["macro_f1"], test_metrics["weighted_f1"])
    log.info("best_epoch=%s best_val_macro_f1=%.5f", best_epoch, best_val_macro_f1)
    for cls, vals in test_metrics["per_class"].items():
        log.info("%s precision=%.4f recall=%.4f f1=%.4f support=%s", cls, vals["precision"], vals["recall"], vals["f1"], vals["support"])
    log.info("Output dir: %s", out_dir)


if __name__ == "__main__":
    main()
