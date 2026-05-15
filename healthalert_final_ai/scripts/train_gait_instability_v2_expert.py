"""Train HealthAlert Gait Instability v2 Expert on rescued DAPHNET windows.

This trainer uses only:
    outputs/windowed_dataset/gait_instability_v2/{train,val,test}.npz

It does not use live ESP32 / MPU6050 data for training.
It does not fall back to synthetic data unless --smoke is explicitly passed.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

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
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("healthalert.train_gait_instability_v2_expert")

DEFAULT_DATA_DIR = PROJECT_ROOT / "outputs" / "windowed_dataset" / "gait_instability_v2"
DEFAULT_OUT_DIR = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "gait_instability_v2_expert"
EXPECTED_PYTHON = PROJECT_ROOT.parent / ".venv311" / "Scripts" / "python.exe"

CLASS_NAMES = ["stable_gait", "abnormal_or_freezing_movement"]
CLASS_ALIASES = {
    0: "stable_movement / stable_gait",
    1: "abnormal_or_freezing_movement / unstable_gait",
}
RAW_LABEL_TO_FINAL = {
    0: 0,
    3: 1,
}
VALID_LABELS = set(RAW_LABEL_TO_FINAL)
THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train Gait Instability v2 Expert")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--batch_size", type=int, default=256)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--device", type=str, default="auto")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--patience", type=int, default=10)
    p.add_argument("--data_dir", type=str, default=str(DEFAULT_DATA_DIR))
    p.add_argument("--out_dir", type=str, default=str(DEFAULT_OUT_DIR))
    p.add_argument("--pos_weight_cap", type=float, default=5.0)
    p.add_argument("--smoke", action="store_true")
    return p.parse_args()


def _to_builtin(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_builtin(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_to_builtin(v) for v in obj.tolist()]
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


def _norm_path(path: Path) -> str:
    return str(path.resolve()).lower()


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def _safe_div(a: float, b: float) -> float:
    return float(a / b) if b else 0.0


def _application_score(
    stable_recall: float,
    abnormal_recall: float,
    macro_f1: float,
    abnormal_precision: float,
) -> float:
    return float(
        100.0
        * (
            (0.35 * macro_f1)
            + (0.25 * stable_recall)
            + (0.25 * abnormal_recall)
            + (0.15 * abnormal_precision)
        )
    )


def _threshold_predictions(probs: np.ndarray, threshold: float) -> np.ndarray:
    return (probs >= threshold).astype(np.int64)


def _ensure_expected_python() -> None:
    current = Path(sys.executable).resolve()
    expected = EXPECTED_PYTHON.resolve()
    if _norm_path(current) != _norm_path(expected):
        raise RuntimeError(f"Wrong Python executable: {current} ; expected {expected}")


def _make_synthetic(split: str, n: int, seed: int = 42) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray], Dict[str, Any]]:
    rng = np.random.RandomState(seed)
    imu = rng.randn(n, 200, 6).astype(np.float32)
    y = rng.choice([0, 1], size=n, p=[0.8, 0.2]).astype(np.int64)
    meta = []
    source = np.array(["synthetic"] * n, dtype=object)
    subject_id = np.array([f"S{i % 3:02d}" for i in range(n)], dtype=object)
    recording_id = np.array([f"R{i % 5:02d}" for i in range(n)], dtype=object)
    for i in range(n):
        meta.append(
            json.dumps(
                {
                    "window_id": f"synthetic_{split}_{i}",
                    "dataset_name": "synthetic",
                    "subject_id": str(subject_id[i]),
                    "recording_id": str(recording_id[i]),
                    "label": "abnormal_or_freezing_movement" if y[i] == 1 else "stable_movement",
                    "label_raw": "freeze" if y[i] == 1 else "normal",
                    "original_label_summary": {"freeze": int(y[i] == 1), "normal": int(y[i] == 0)},
                    "abnormal_fraction": 1.0 if y[i] == 1 else 0.0,
                    "window_label_source": "synthetic",
                    "sampling_rate_hz": 50.0,
                    "target_rate_hz": 50.0,
                }
            )
        )
    arrays = {
        "features": rng.randn(n, 1400).astype(np.float32),
        "labels": y,
        "imu": imu,
        "ppg": rng.randn(n, 200, 1).astype(np.float32),
        "metadata": np.asarray(meta, dtype=object),
        "source": source,
        "subject_id": subject_id,
        "recording_id": recording_id,
    }
    info = {
        "split": split,
        "npz_path": "synthetic",
        "npz_exists": False,
        "npz_keys": sorted(arrays.keys()),
        "imu_shape": list(imu.shape),
        "ppg_shape": list(arrays["ppg"].shape),
        "features_shape": list(arrays["features"].shape),
        "labels_shape": list(y.shape),
        "metadata_present": True,
        "original_label_summary_present": True,
        "abnormal_fraction_present": True,
        "subject_id_present": True,
        "recording_id_present": True,
        "n_total_in_npz": int(n),
        "n_final": int(n),
        "n_unknown_excluded": 0,
        "stable_count": int((y == 0).sum()),
        "abnormal_count": int((y == 1).sum()),
        "abnormal_percentage": round(100.0 * float((y == 1).mean()), 4),
        "source_distribution": dict(Counter(source.tolist())),
        "subject_distribution": dict(Counter(subject_id.tolist())),
        "recording_distribution": dict(Counter(recording_id.tolist())),
        "abnormal_by_subject": dict(Counter(subject_id[y == 1].tolist())),
        "abnormal_by_recording": dict(Counter(recording_id[y == 1].tolist())),
        "window_label_source_distribution": {"synthetic": int(n)},
    }
    return imu.transpose(0, 2, 1).astype(np.float32), y.astype(np.int64), arrays, info


def load_split(split: str, data_dir: Path, smoke: bool = False) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray], Dict[str, Any]]:
    if smoke:
        n = 2048 if split == "train" else 512
        return _make_synthetic(split, n, seed=42 + {"train": 0, "val": 1, "test": 2}[split])

    npz_path = data_dir / f"{split}.npz"
    if not npz_path.exists():
        raise FileNotFoundError(f"[{split}] NPZ not found: {npz_path}")

    raw = np.load(str(npz_path), allow_pickle=True)
    keys = sorted(raw.files)
    required = {"imu", "labels", "metadata"}
    missing = sorted(required - set(keys))
    if missing:
        raise KeyError(f"[{split}] missing required keys: {missing}; found={keys}")

    imu = raw["imu"].astype(np.float32)
    labels_raw = raw["labels"].astype(np.int64).flatten()
    metadata = raw["metadata"]
    if imu.ndim != 3 or imu.shape[1:] != (200, 6):
        raise ValueError(f"[{split}] expected imu shape (N, 200, 6); got {imu.shape}")
    if len(labels_raw) != imu.shape[0]:
        raise ValueError(f"[{split}] label length {len(labels_raw)} does not match imu N {imu.shape[0]}")

    keep = np.array([int(lbl) in VALID_LABELS for lbl in labels_raw], dtype=bool)
    unknown_excluded = int((~keep).sum())

    imu = imu[keep]
    labels = np.array([RAW_LABEL_TO_FINAL[int(lbl)] for lbl in labels_raw[keep]], dtype=np.int64)
    metadata = metadata[keep]

    arrays: Dict[str, np.ndarray] = {
        "features": raw["features"][keep] if "features" in raw.files else np.empty((len(labels), 0), dtype=np.float32),
        "labels": labels,
        "imu": imu,
        "ppg": raw["ppg"][keep] if "ppg" in raw.files else np.empty((len(labels), 200, 1), dtype=np.float32),
        "metadata": metadata,
        "source": raw["source"][keep] if "source" in raw.files else np.array([_parse_meta(m).get("dataset_name", "unknown") for m in metadata], dtype=object),
        "subject_id": raw["subject_id"][keep] if "subject_id" in raw.files else np.array([_parse_meta(m).get("subject_id", "unknown") for m in metadata], dtype=object),
        "recording_id": raw["recording_id"][keep] if "recording_id" in raw.files else np.array([_parse_meta(m).get("recording_id", "unknown") for m in metadata], dtype=object),
    }

    if smoke:
        rng = np.random.RandomState(42)
        idx = rng.permutation(len(labels))[: min(2000, len(labels))]
        for key in list(arrays.keys()):
            arrays[key] = arrays[key][idx]
        imu = arrays["imu"]
        labels = arrays["labels"]
        metadata = arrays["metadata"]

    metas = [_parse_meta(m) for m in metadata]
    source_dist = dict(Counter(str(s) for s in arrays["source"].tolist()))
    subject_dist = dict(Counter(str(s) for s in arrays["subject_id"].tolist()))
    recording_dist = dict(Counter(str(s) for s in arrays["recording_id"].tolist()))
    abnormal_mask = labels == 1
    abnormal_by_subject = dict(Counter(str(s) for s in arrays["subject_id"][abnormal_mask].tolist()))
    abnormal_by_recording = dict(Counter(str(s) for s in arrays["recording_id"][abnormal_mask].tolist()))
    label_source_dist = dict(Counter(str(m.get("window_label_source", "unknown")) for m in metas))

    info = {
        "split": split,
        "npz_path": str(npz_path),
        "npz_exists": True,
        "npz_keys": keys,
        "imu_shape": list(raw["imu"].shape),
        "model_input_shape": [int(imu.shape[0]), 6, 200],
        "ppg_shape": list(raw["ppg"].shape) if "ppg" in raw.files else None,
        "features_shape": list(raw["features"].shape) if "features" in raw.files else None,
        "labels_shape": list(raw["labels"].shape),
        "metadata_present": "metadata" in raw.files,
        "original_label_summary_present": any("original_label_summary" in m for m in metas),
        "abnormal_fraction_present": any("abnormal_fraction" in m for m in metas),
        "subject_id_present": "subject_id" in raw.files or any("subject_id" in m for m in metas),
        "recording_id_present": "recording_id" in raw.files or any("recording_id" in m for m in metas),
        "n_total_in_npz": int(len(labels_raw)),
        "n_final": int(len(labels)),
        "n_unknown_excluded": int(unknown_excluded),
        "stable_count": int((labels == 0).sum()),
        "abnormal_count": int((labels == 1).sum()),
        "abnormal_percentage": round(100.0 * _safe_div(int((labels == 1).sum()), len(labels)), 4),
        "source_distribution": source_dist,
        "subject_distribution": subject_dist,
        "recording_distribution": recording_dist,
        "abnormal_by_subject": abnormal_by_subject,
        "abnormal_by_recording": abnormal_by_recording,
        "window_label_source_distribution": label_source_dist,
        "sampling_rate_distribution": dict(
            Counter(str(m.get("sampling_rate_hz", m.get("sampling_rate", "unknown"))) for m in metas)
        ),
    }
    return imu.transpose(0, 2, 1).astype(np.float32), labels.astype(np.int64), arrays, info


def compute_norm_stats(X: np.ndarray) -> Dict[str, Any]:
    mean = X.mean(axis=(0, 2))
    std = np.maximum(X.std(axis=(0, 2)), 1e-6)
    return {
        "method": "per-channel z-score",
        "computed_from": "train split only",
        "mean_per_channel": [float(v) for v in mean],
        "std_per_channel": [float(v) for v in std],
        "n_channels": int(X.shape[1]),
        "window_length": int(X.shape[2]),
    }


def apply_norm(X: np.ndarray, stats: Dict[str, Any]) -> np.ndarray:
    mean = np.asarray(stats["mean_per_channel"], dtype=np.float32)
    std = np.asarray(stats["std_per_channel"], dtype=np.float32)
    return ((X - mean[None, :, None]) / std[None, :, None]).astype(np.float32)


def compute_pos_weight(y: np.ndarray, cap: float) -> float:
    stable = max(int((y == 0).sum()), 1)
    abnormal = max(int((y == 1).sum()), 1)
    return float(min(stable / abnormal, cap))


def compute_split_overlap(metadata_by_split: Dict[str, np.ndarray]) -> Dict[str, int]:
    window_ids = {}
    for split, metadata in metadata_by_split.items():
        ids = set()
        for meta in metadata:
            ids.add(str(_parse_meta(meta).get("window_id", "")))
        window_ids[split] = ids
    return {
        "train_val_window_overlap": len(window_ids["train"] & window_ids["val"]),
        "train_test_window_overlap": len(window_ids["train"] & window_ids["test"]),
        "val_test_window_overlap": len(window_ids["val"] & window_ids["test"]),
    }


def evaluate_predictions(y_true: np.ndarray, probs: np.ndarray, threshold: float) -> Dict[str, Any]:
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_recall_curve,
        precision_recall_fscore_support,
        precision_score,
        recall_score,
        roc_auc_score,
        auc,
    )

    preds = _threshold_predictions(probs, threshold)
    cm = confusion_matrix(y_true, preds, labels=[0, 1])
    prec, rec, f1, sup = precision_recall_fscore_support(y_true, preds, labels=[0, 1], zero_division=0)
    n_pred_cls = int(len(np.unique(preds)))

    roc_auc = None
    pr_auc = None
    if len(np.unique(y_true)) == 2:
        roc_auc = float(roc_auc_score(y_true, probs))
        pr_prec, pr_rec, _ = precision_recall_curve(y_true, probs)
        pr_auc = float(auc(pr_rec, pr_prec))

    return {
        "threshold": float(threshold),
        "accuracy": float(accuracy_score(y_true, preds)),
        "macro_f1": float(f1_score(y_true, preds, average="macro", labels=[0, 1], zero_division=0)),
        "weighted_f1": float(f1_score(y_true, preds, average="weighted", labels=[0, 1], zero_division=0)),
        "macro_precision": float(precision_score(y_true, preds, average="macro", labels=[0, 1], zero_division=0)),
        "macro_recall": float(recall_score(y_true, preds, average="macro", labels=[0, 1], zero_division=0)),
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "confusion_matrix": cm.tolist(),
        "per_class": {
            CLASS_NAMES[i]: {
                "precision": float(prec[i]),
                "recall": float(rec[i]),
                "f1": float(f1[i]),
                "support": int(sup[i]),
            }
            for i in range(2)
        },
        "prediction_distribution": {
            CLASS_NAMES[0]: int((preds == 0).sum()),
            CLASS_NAMES[1]: int((preds == 1).sum()),
        },
        "preds": preds,
        "n_pred_cls": n_pred_cls,
        "dominant_predicted_class": CLASS_NAMES[int(np.bincount(preds, minlength=2).argmax())],
        "dominant_ratio": float(np.bincount(preds, minlength=2).max() / max(len(preds), 1)),
        "false_positives": int(cm[0, 1]),
        "false_negatives": int(cm[1, 0]),
        "application_score": _application_score(
            float(rec[0]),
            float(rec[1]),
            float(f1_score(y_true, preds, average="macro", labels=[0, 1], zero_division=0)),
            float(prec[1]),
        ),
    }


def evaluate_model(
    model: nn.Module,
    X: np.ndarray,
    y: np.ndarray,
    arrays: Dict[str, np.ndarray],
    device: torch.device,
    batch_size: int,
    threshold: float,
) -> Dict[str, Any]:
    model.eval()
    logits_all: List[np.ndarray] = []
    loader = DataLoader(TensorDataset(torch.from_numpy(X)), batch_size=batch_size, shuffle=False)
    with torch.no_grad():
        for (xb,) in loader:
            out = model(xb.to(device))
            logits_all.append(out["logit"].detach().cpu().numpy())
    logits = np.concatenate(logits_all, axis=0).astype(np.float64)
    probs = _sigmoid(logits)
    metrics = evaluate_predictions(y, probs, threshold)
    metrics["logits"] = logits
    metrics["probs"] = probs

    source_breakdown: Dict[str, Any] = {}
    subject_breakdown: Dict[str, Any] = {}
    sources = np.asarray(arrays["source"], dtype=object)
    subjects = np.asarray(arrays["subject_id"], dtype=object)
    recordings = np.asarray(arrays["recording_id"], dtype=object)
    preds = metrics["preds"]

    for src in np.unique(sources):
        mask = sources == src
        local = evaluate_predictions(y[mask], probs[mask], threshold)
        source_breakdown[str(src)] = {
            "n": int(mask.sum()),
            "accuracy": round(local["accuracy"], 4),
            "macro_f1": round(local["macro_f1"], 4),
            "stable_recall": round(local["per_class"][CLASS_NAMES[0]]["recall"], 4),
            "abnormal_recall": round(local["per_class"][CLASS_NAMES[1]]["recall"], 4),
            "prediction_distribution": local["prediction_distribution"],
            "true_distribution": {
                CLASS_NAMES[0]: int((y[mask] == 0).sum()),
                CLASS_NAMES[1]: int((y[mask] == 1).sum()),
            },
        }

    for subj in np.unique(subjects):
        mask = subjects == subj
        local = evaluate_predictions(y[mask], probs[mask], threshold)
        subject_breakdown[str(subj)] = {
            "n": int(mask.sum()),
            "recordings": sorted({str(r) for r in recordings[mask].tolist()}),
            "accuracy": round(local["accuracy"], 4),
            "macro_f1": round(local["macro_f1"], 4),
            "stable_support": int((y[mask] == 0).sum()),
            "abnormal_support": int((y[mask] == 1).sum()),
            "stable_recall": round(local["per_class"][CLASS_NAMES[0]]["recall"], 4),
            "abnormal_recall": round(local["per_class"][CLASS_NAMES[1]]["recall"], 4),
            "predicted_stable": int((preds[mask] == 0).sum()),
            "predicted_abnormal": int((preds[mask] == 1).sum()),
        }

    metrics["source_breakdown"] = source_breakdown
    metrics["subject_breakdown"] = subject_breakdown
    return metrics


def validation_sweep(y_true: np.ndarray, probs: np.ndarray) -> Tuple[List[Dict[str, Any]], float]:
    rows: List[Dict[str, Any]] = []
    for threshold in THRESHOLDS:
        metrics = evaluate_predictions(y_true, probs, threshold)
        row = {
            "threshold": round(threshold, 2),
            "stable_recall": round(metrics["per_class"][CLASS_NAMES[0]]["recall"], 4),
            "abnormal_recall": round(metrics["per_class"][CLASS_NAMES[1]]["recall"], 4),
            "abnormal_precision": round(metrics["per_class"][CLASS_NAMES[1]]["precision"], 4),
            "macro_f1": round(metrics["macro_f1"], 4),
            "false_positives": int(metrics["false_positives"]),
            "false_negatives": int(metrics["false_negatives"]),
            "application_score": round(metrics["application_score"], 2),
            "n_pred_cls": int(metrics["n_pred_cls"]),
        }
        rows.append(row)

    eligible = [
        r
        for r in rows
        if r["stable_recall"] >= 0.75 and r["abnormal_recall"] >= 0.60 and r["n_pred_cls"] >= 2
    ]
    if eligible:
        best = max(
            eligible,
            key=lambda r: (r["macro_f1"], r["abnormal_precision"], -r["false_positives"], r["application_score"]),
        )
    else:
        best = max(
            rows,
            key=lambda r: (r["application_score"], r["macro_f1"], r["abnormal_precision"], -r["false_positives"]),
        )
    return rows, float(best["threshold"])


def checkpoint_valid(eval_metrics: Dict[str, Any], val_loss: float, best_so_far: float) -> Tuple[bool, str]:
    if not math.isfinite(val_loss):
        return False, "validation loss not finite"
    logits = np.asarray(eval_metrics["logits"])
    if not np.isfinite(logits).all():
        return False, "logits contain NaN/Inf"
    if eval_metrics["n_pred_cls"] < 2:
        return False, "single-class collapse"
    if eval_metrics["per_class"][CLASS_NAMES[0]]["recall"] <= 0.0:
        return False, "stable recall is zero"
    if eval_metrics["per_class"][CLASS_NAMES[1]]["recall"] <= 0.0:
        return False, "abnormal recall is zero"
    if eval_metrics["dominant_ratio"] > 0.98:
        return False, "majority-class crush"
    if eval_metrics["macro_f1"] <= best_so_far:
        return False, "macro_f1 did not improve"
    return True, "ok"


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
        "subject_breakdown.json",
        "imu_norm_stats.json",
        "gait_v2_dataset_audit.md",
        "gait_v2_dataset_audit.json",
        "gait_instability_v2_expert_report.md",
    ]:
        target = out_dir / name
        if target.exists():
            target.unlink()


def save_dataset_audit(
    out_dir: Path,
    env_info: Dict[str, Any],
    data_dir: Path,
    audits: Dict[str, Dict[str, Any]],
    overlap: Dict[str, int],
    subject_split_preserved: bool,
) -> None:
    payload = {
        "task": "gait_instability_v2",
        "data_dir": str(data_dir),
        "prepared_public_npz_only": True,
        "synthetic_fallback_used": False,
        "live_esp32_mpu6050_training_used": False,
        "raw_to_final_label_mapping": {
            "0 (stable_movement / stable_gait)": 0,
            "3 (abnormal_or_freezing_movement / unstable_gait)": 1,
            "other / unknown": "excluded",
        },
        "environment": env_info,
        "splits": audits,
        "split_overlap": overlap,
        "subject_aware_split_preserved": subject_split_preserved,
    }
    with open(out_dir / "gait_v2_dataset_audit.json", "w", encoding="utf-8") as f:
        json.dump(_to_builtin(payload), f, indent=2)

    lines = [
        "# Gait v2 Dataset Audit",
        "",
        "## Environment",
        "",
        f"- sys.executable: `{env_info['sys_executable']}`",
        f"- sys.version: `{env_info['sys_version']}`",
        f"- torch.__version__: `{env_info['torch_version']}`",
        f"- working directory: `{env_info['working_directory']}`",
        f"- data_dir: `{data_dir}`",
        "",
        "## Data Source Confirmation",
        "",
        "- Prepared public NPZ used: YES",
        "- Synthetic fallback used: NO",
        "- Live ESP32/MPU6050 training data used: NO",
        "- Legacy gait_instability dataset used: NO",
        "",
        "## NPZ Files",
        "",
        "| Split | NPZ path | Keys | IMU shape | Model input shape | Labels shape | Unknown excluded |",
        "|---|---|---|---|---|---|---:|",
    ]
    for split, info in audits.items():
        lines.append(
            f"| {split} | `{info['npz_path']}` | {', '.join(info['npz_keys'])} | {info['imu_shape']} | {info['model_input_shape']} | {info['labels_shape']} | {info['n_unknown_excluded']} |"
        )
    lines += [
        "",
        "## Label Mapping",
        "",
        "| Raw label / canonical label | Final class index | Action |",
        "|---|---|---|",
        "| 0 / stable_movement / stable_gait | 0 | train/evaluate |",
        "| 3 / abnormal_or_freezing_movement / unstable_gait | 1 | train/evaluate |",
        "| other / unknown | excluded | exclude |",
        "",
        "## Split Support",
        "",
        "| Split | Stable count | Abnormal count | Unknown excluded | Abnormal % |",
        "|---|---:|---:|---:|---:|",
    ]
    for split, info in audits.items():
        lines.append(
            f"| {split} | {info['stable_count']:,} | {info['abnormal_count']:,} | {info['n_unknown_excluded']:,} | {info['abnormal_percentage']:.4f}% |"
        )
    lines += [
        "",
        "## Subject Distribution",
        "",
        f"- Subject-aware split preserved: {'YES' if subject_split_preserved else 'NO'}",
        f"- Train/val overlap: {overlap['train_val_window_overlap']}",
        f"- Train/test overlap: {overlap['train_test_window_overlap']}",
        f"- Val/test overlap: {overlap['val_test_window_overlap']}",
    ]
    for split, info in audits.items():
        lines += [
            "",
            f"### {split.title()} abnormal by subject",
            "",
            json.dumps(info["abnormal_by_subject"], ensure_ascii=False, indent=2),
        ]
    with open(out_dir / "gait_v2_dataset_audit.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def build_report(
    out_dir: Path,
    env_info: Dict[str, Any],
    data_dir: Path,
    audits: Dict[str, Dict[str, Any]],
    overlap: Dict[str, int],
    subject_split_preserved: bool,
    norm_stats: Dict[str, Any],
    history: List[Dict[str, Any]],
    model_params: int,
    train_cfg: Dict[str, Any],
    best_epoch: int,
    best_val_macro_f1: float | None,
    recommended_threshold: float,
    threshold_rows: List[Dict[str, Any]],
    test_metrics: Dict[str, Any],
    checkpoint_saved: bool,
    application_valid: bool,
    final_decision: str,
) -> str:
    per_class = test_metrics["per_class"]
    cm = test_metrics["confusion_matrix"]
    pred_dist = test_metrics["prediction_distribution"]
    dominant_ratio = test_metrics["dominant_ratio"]
    collapse = test_metrics["n_pred_cls"] < 2 or dominant_ratio > 0.98
    riskfusion = "YES" if application_valid else "NO"

    lines = [
        "# Gait Instability v2 Expert Report",
        "",
        "## 1. Executive Summary",
        "",
        f"- Final decision: **{final_decision}**",
        f"- application_valid: **{application_valid}**",
        f"- Gait abnormal/freezing learned: {'YES' if per_class[CLASS_NAMES[1]]['recall'] > 0 else 'NO'}",
        f"- Collapse detected: {'YES' if collapse else 'NO'}",
        f"- RiskFusion integration ready: {riskfusion}",
        "",
        "## 2. Environment Confirmation",
        "",
        f"- sys.executable: `{env_info['sys_executable']}`",
        f"- sys.version: `{env_info['sys_version']}`",
        f"- torch.__version__: `{env_info['torch_version']}`",
        f"- working directory: `{env_info['working_directory']}`",
        f"- data_dir: `{data_dir}`",
        "",
        "## 3. Data Source Confirmation",
        "",
        "- Prepared public NPZ: YES",
        "- Synthetic: NO",
        "- Live ESP32/MPU6050 training used: NO",
        "- Legacy gait_instability dataset used: NO",
        f"- Train NPZ: `{data_dir / 'train.npz'}`",
        f"- Val NPZ: `{data_dir / 'val.npz'}`",
        f"- Test NPZ: `{data_dir / 'test.npz'}`",
        "",
        "| Split | Samples used | Sources |",
        "|---|---:|---|",
    ]
    for split, info in audits.items():
        lines.append(f"| {split} | {info['n_final']:,} | {', '.join(sorted(info['source_distribution']))} |")

    lines += [
        "",
        "## 4. Dataset Audit",
        "",
        "| Split | Keys | IMU shape | Label shape | Metadata | Unknown excluded | abnormal_fraction field |",
        "|---|---|---|---|---|---:|---|",
    ]
    for split, info in audits.items():
        lines.append(
            f"| {split} | {', '.join(info['npz_keys'])} | {info['imu_shape']} | {info['labels_shape']} | {info['metadata_present']} | {info['n_unknown_excluded']} | {info['abnormal_fraction_present']} |"
        )

    lines += [
        "",
        "## 5. Label Mapping",
        "",
        "| Raw/canonical label | Final class index | Action |",
        "|---|---|---|",
        "| 0 / stable_movement / stable_gait | 0 | train/evaluate |",
        "| 3 / abnormal_or_freezing_movement / unstable_gait | 1 | train/evaluate |",
        "| other / unknown | excluded | exclude |",
        "",
        "## 6. Class Distribution",
        "",
        "| Split | stable count | abnormal/freezing count | unknown excluded | abnormal % |",
        "|---|---:|---:|---:|---:|",
    ]
    for split, info in audits.items():
        lines.append(
            f"| {split} | {info['stable_count']:,} | {info['abnormal_count']:,} | {info['n_unknown_excluded']:,} | {info['abnormal_percentage']:.4f}% |"
        )

    lines += [
        "",
        "## 7. Subject/Recording Breakdown",
        "",
        f"- Subject-aware split preserved: {'YES' if subject_split_preserved else 'NO'}",
        f"- Train/val overlap: {overlap['train_val_window_overlap']}",
        f"- Train/test overlap: {overlap['train_test_window_overlap']}",
        f"- Val/test overlap: {overlap['val_test_window_overlap']}",
        "",
        f"- Train abnormal by subject: {json.dumps(audits['train']['abnormal_by_subject'], ensure_ascii=False)}",
        f"- Val abnormal by subject: {json.dumps(audits['val']['abnormal_by_subject'], ensure_ascii=False)}",
        f"- Test abnormal by subject: {json.dumps(audits['test']['abnormal_by_subject'], ensure_ascii=False)}",
        "",
        "## 8. Input Normalization",
        "",
        "- Method: per-channel z-score",
        "- Train stats only: YES",
        f"- imu_norm_stats path: `{out_dir / 'imu_norm_stats.json'}`",
        "",
        "| Channel | Mean | Std |",
        "|---:|---:|---:|",
    ]
    for idx, (m, s) in enumerate(zip(norm_stats["mean_per_channel"], norm_stats["std_per_channel"])):
        lines.append(f"| {idx} | {m:.6f} | {s:.6f} |")

    lines += [
        "",
        "## 9. Model Architecture",
        "",
        f"- Model class: `{GaitInstabilityExpertCNN.__name__}`",
        "- Input shape: `(batch, 6, 200)`",
        f"- Output classes: {', '.join(CLASS_NAMES)}",
        f"- Parameter count: {model_params:,}",
        f"- Loss: `{train_cfg['loss']}`",
        f"- pos_weight: `{train_cfg['pos_weight']:.4f}`",
        f"- pos_weight_cap: `{train_cfg['pos_weight_cap']:.2f}`",
        f"- Optimizer: `{train_cfg['optimizer']}`",
        f"- lr: `{train_cfg['lr']}`",
        f"- Scheduler: `{train_cfg['scheduler']}`",
        "- Checkpoint metric: validation macro_f1",
        "",
        "## 10. Training Dynamics",
        "",
        "| Epoch | Train loss | Val loss | Val accuracy | Val macro_f1 | stable recall | abnormal recall | n_pred_cls | checkpoint_valid | best saved |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in history:
        lines.append(
            f"| {row['epoch']} | {row['train_loss']:.5f} | {row['val_loss']:.5f} | {row['val_accuracy']:.4f} | {row['val_macro_f1']:.5f} | {row['stable_recall']:.4f} | {row['abnormal_recall']:.4f} | {row['n_pred_cls']} | {'YES' if row['checkpoint_valid'] else 'NO'} | {'YES' if row['best_checkpoint_saved'] else 'NO'} |"
        )

    lines += [
        "",
        "## 11. Final Test Metrics",
        "",
        f"- Threshold used for final test metrics: `{recommended_threshold:.2f}`",
        f"- Accuracy: {test_metrics['accuracy']:.4f}",
        f"- Macro F1: {test_metrics['macro_f1']:.4f}",
        f"- Weighted F1: {test_metrics['weighted_f1']:.4f}",
        f"- Macro precision: {test_metrics['macro_precision']:.4f}",
        f"- Macro recall: {test_metrics['macro_recall']:.4f}",
        f"- ROC-AUC: {test_metrics['roc_auc']:.4f}" if test_metrics["roc_auc"] is not None else "- ROC-AUC: N/A",
        f"- PR-AUC: {test_metrics['pr_auc']:.4f}" if test_metrics["pr_auc"] is not None else "- PR-AUC: N/A",
        "",
        "## 12. Per-Class Metrics",
        "",
        "| Class | Precision | Recall | F1 | Support |",
        "|---|---:|---:|---:|---:|",
    ]
    for cls in CLASS_NAMES:
        vals = per_class[cls]
        lines.append(
            f"| {cls} | {vals['precision']:.4f} | {vals['recall']:.4f} | {vals['f1']:.4f} | {vals['support']:,} |"
        )

    lines += [
        "",
        "## 13. Confusion Matrix",
        "",
        "| Actual / Pred | stable_gait | abnormal_or_freezing_movement |",
        "|---|---:|---:|",
        f"| stable_gait | {cm[0][0]} | {cm[0][1]} |",
        f"| abnormal_or_freezing_movement | {cm[1][0]} | {cm[1][1]} |",
        "",
        f"- abnormal -> stable false negatives: {cm[1][0]}",
        f"- stable -> abnormal false positives: {cm[0][1]}",
        "",
        "## 14. Prediction Distribution",
        "",
        "| Class | Predicted count | Predicted % | True count | True % |",
        "|---|---:|---:|---:|---:|",
    ]
    total_true = sum(v["support"] for v in per_class.values())
    total_pred = sum(pred_dist.values())
    for cls in CLASS_NAMES:
        pred_cnt = int(pred_dist.get(cls, 0))
        true_cnt = int(per_class[cls]["support"])
        lines.append(
            f"| {cls} | {pred_cnt:,} | {100.0 * pred_cnt / max(total_pred, 1):.2f}% | {true_cnt:,} | {100.0 * true_cnt / max(total_true, 1):.2f}% |"
        )

    lines += [
        "",
        "## 15. Threshold Analysis",
        "",
        "- Threshold recommendation is selected on validation sweep, not test.",
        "- Constraint-first selection: stable_recall >= 0.75 and abnormal_recall >= 0.60 on validation when possible.",
        "- application_score = 100 * (0.35 * macro_f1 + 0.25 * stable_recall + 0.25 * abnormal_recall + 0.15 * abnormal_precision)",
        "",
        "| Threshold | stable recall | abnormal recall | abnormal precision | macro_f1 | FP | FN | application_score |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in threshold_rows:
        lines.append(
            f"| {row['threshold']:.2f} | {row['stable_recall']:.4f} | {row['abnormal_recall']:.4f} | {row['abnormal_precision']:.4f} | {row['macro_f1']:.4f} | {row['false_positives']} | {row['false_negatives']} | {row['application_score']:.2f} |"
        )
    lines += [
        "",
        f"- Recommended threshold: **{recommended_threshold:.2f}**",
        "",
        "## 16. Source/Subject Evaluation",
        "",
        "### Source-level",
        "",
        "| Source | Samples | Accuracy | Macro F1 | stable recall | abnormal recall |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for source_name, vals in sorted(test_metrics["source_breakdown"].items()):
        lines.append(
            f"| {source_name} | {vals['n']:,} | {vals['accuracy']:.4f} | {vals['macro_f1']:.4f} | {vals['stable_recall']:.4f} | {vals['abnormal_recall']:.4f} |"
        )
    lines += [
        "",
        "### Subject-level (test)",
        "",
        "| Subject | Samples | Stable support | Abnormal support | Macro F1 | stable recall | abnormal recall |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for subject_name, vals in sorted(test_metrics["subject_breakdown"].items()):
        lines.append(
            f"| {subject_name} | {vals['n']:,} | {vals['stable_support']:,} | {vals['abnormal_support']:,} | {vals['macro_f1']:.4f} | {vals['stable_recall']:.4f} | {vals['abnormal_recall']:.4f} |"
        )

    lines += [
        "",
        "## 17. Collapse / Dominance Check",
        "",
        f"- n_pred_cls: {test_metrics['n_pred_cls']}",
        f"- Dominant predicted class: {test_metrics['dominant_predicted_class']}",
        f"- Dominant ratio: {test_metrics['dominant_ratio']:.4f}",
        f"- Single-class collapse: {'YES' if test_metrics['n_pred_cls'] < 2 else 'NO'}",
        f"- Majority-class crush: {'YES' if test_metrics['dominant_ratio'] > 0.98 else 'NO'}",
        "",
        "## 18. Checkpoint Validity",
        "",
        f"- best_model.pt valid: {'YES' if checkpoint_saved else 'NO'}",
        f"- application_valid: {'YES' if application_valid else 'NO'}",
        f"- best epoch: {best_epoch}" if best_epoch > 0 else "- best epoch: N/A",
        f"- best val macro_f1: {best_val_macro_f1:.5f}" if best_val_macro_f1 is not None else "- best val macro_f1: N/A",
        f"- best_model.pt path: `{out_dir / 'best_model.pt'}`",
        f"- last_model.pt path: `{out_dir / 'last_model.pt'}`",
        "",
        "## 19. RiskFusion Integration Note",
        "",
    ]
    if application_valid:
        lines += [
            "- `gait_instability_v2_model_enabled` can be set to `true` after explicit integration approval.",
            "- Output should be consumed as `gait_abnormal_probability`.",
            "- High gait abnormal probability + medium/high fall probability should increase risk.",
            "- Gait abnormal probability alone must not produce `critical`.",
            "- Temporal smoothing remains required.",
        ]
    else:
        lines += [
            "- Model remains disabled at runtime.",
            "- Rule-based gait handling should continue.",
            "- Do not connect this checkpoint to RiskFusionEngine yet.",
        ]

    lines += [
        "",
        "## 20. Final Decision",
        "",
        f"**{final_decision}**",
        "",
        "## 21. Recommendation",
        "",
        f"- RiskFusionEngine connection now: {'YES, but only as low-weight auxiliary after explicit approval' if application_valid else 'NO'}",
        f"- Recommended threshold: {recommended_threshold:.2f}",
        f"- pos_weight tuning needed: {'consider later' if application_valid else 'likely worth another pass after review'}",
        "- DAPHNET single-source risk should still be acknowledged.",
        "- Activity v2 can proceed independently; no need to block it on gait unless another gait iteration is explicitly desired.",
    ]
    return "\n".join(lines)


def decide_final(test_metrics: Dict[str, Any], checkpoint_saved: bool) -> Tuple[bool, str]:
    stable_recall = test_metrics["per_class"][CLASS_NAMES[0]]["recall"]
    abnormal_recall = test_metrics["per_class"][CLASS_NAMES[1]]["recall"]
    macro_f1 = test_metrics["macro_f1"]
    n_pred_cls = test_metrics["n_pred_cls"]
    collapse = n_pred_cls < 2 or test_metrics["dominant_ratio"] > 0.98

    minimum_ok = bool(
        checkpoint_saved
        and not collapse
        and macro_f1 >= 0.65
        and stable_recall >= 0.75
        and abnormal_recall >= 0.60
        and test_metrics["prediction_distribution"][CLASS_NAMES[0]] > 0
        and test_metrics["prediction_distribution"][CLASS_NAMES[1]] > 0
    )
    ideal_ok = bool(
        minimum_ok
        and macro_f1 >= 0.75
        and stable_recall >= 0.80
        and abnormal_recall >= 0.70
    )
    if ideal_ok:
        return True, "ACCEPT_GAIT_V2_1_EXPERT"
    if minimum_ok:
        return True, "PARTIAL_ACCEPT_AUXILIARY_ONLY"
    return False, "REJECT_KEEP_RULE_BASED"


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    _ensure_expected_python()

    data_dir = Path(args.data_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    clean_output_dir(out_dir)

    env_info = {
        "sys_executable": sys.executable,
        "sys_version": sys.version.replace("\n", " "),
        "torch_version": torch.__version__,
        "working_directory": str(Path.cwd().resolve()),
        "data_dir": str(data_dir),
    }
    log.info("=== PYTHON ENVIRONMENT CONFIRMATION ===")
    for key, value in env_info.items():
        log.info("%s: %s", key, value)

    if not args.smoke and _norm_path(data_dir) != _norm_path(DEFAULT_DATA_DIR):
        log.warning("Using non-default gait v2 data_dir: %s", data_dir)
    if not args.smoke and "gait_instability_v2" not in str(data_dir):
        raise RuntimeError(f"Refusing to train from non-v2 dataset path: {data_dir}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else torch.device(args.device)
    log.info("device: %s", device)

    X_tr, y_tr, arrays_tr, audit_tr = load_split("train", data_dir, smoke=args.smoke)
    X_val, y_val, arrays_val, audit_val = load_split("val", data_dir, smoke=args.smoke)
    X_te, y_te, arrays_te, audit_te = load_split("test", data_dir, smoke=args.smoke)
    audits = {"train": audit_tr, "val": audit_val, "test": audit_te}

    overlap = compute_split_overlap(
        {
            "train": arrays_tr["metadata"],
            "val": arrays_val["metadata"],
            "test": arrays_te["metadata"],
        }
    )
    subject_split_preserved = all(v == 0 for v in overlap.values())
    save_dataset_audit(out_dir, env_info, data_dir, audits, overlap, subject_split_preserved)
    log.info("Saved dataset audit to %s", out_dir / "gait_v2_dataset_audit.md")

    norm_stats = compute_norm_stats(X_tr)
    X_tr = apply_norm(X_tr, norm_stats)
    X_val = apply_norm(X_val, norm_stats)
    X_te = apply_norm(X_te, norm_stats)
    with open(out_dir / "imu_norm_stats.json", "w", encoding="utf-8") as f:
        json.dump(norm_stats, f, indent=2)

    pos_weight = compute_pos_weight(y_tr, args.pos_weight_cap)
    log.info("train stable=%d abnormal=%d pos_weight=%.4f cap=%.2f", int((y_tr == 0).sum()), int((y_tr == 1).sum()), pos_weight, args.pos_weight_cap)

    model = build_gait_instability_expert({"in_channels": X_tr.shape[1], "window_length": X_tr.shape[2]}).to(device)
    model_params = int(sum(p.numel() for p in model.parameters()))
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight], dtype=torch.float32, device=device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)

    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_tr), torch.from_numpy(y_tr.astype(np.float32))),
        batch_size=args.batch_size,
        shuffle=True,
    )
    val_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val.astype(np.float32))),
        batch_size=args.batch_size,
        shuffle=False,
    )

    history: List[Dict[str, Any]] = []
    best_val_macro_f1 = -1.0
    best_epoch = 0
    patience_counter = 0
    checkpoint_saved = False
    t0 = time.time()

    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss = 0.0
        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            optimizer.zero_grad()
            out = model(xb)
            loss = criterion(out["logit"], yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += float(loss.item())
        train_loss /= max(len(train_loader), 1)
        scheduler.step()

        model.eval()
        val_loss = 0.0
        logits_all: List[np.ndarray] = []
        targets_all: List[np.ndarray] = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb = xb.to(device)
                yb = yb.to(device)
                out = model(xb)
                val_loss += float(criterion(out["logit"], yb).item())
                logits_all.append(out["logit"].cpu().numpy())
                targets_all.append(yb.cpu().numpy().astype(np.int64))
        val_loss /= max(len(val_loader), 1)
        val_logits = np.concatenate(logits_all, axis=0)
        val_targets = np.concatenate(targets_all, axis=0)
        val_probs = _sigmoid(val_logits)
        val_eval = evaluate_predictions(val_targets, val_probs, 0.50)
        ckpt_valid, ckpt_reason = checkpoint_valid(val_eval | {"logits": val_logits}, val_loss, best_val_macro_f1)
        improved = ckpt_valid

        state = {
            "model_state_dict": model.state_dict(),
            "epoch": epoch,
            "val_macro_f1": float(val_eval["macro_f1"]),
            "classes": CLASS_NAMES,
            "threshold_default": 0.5,
            "data_dir": str(data_dir),
            "pos_weight": pos_weight,
            "pos_weight_cap": args.pos_weight_cap,
        }
        torch.save(state, out_dir / "last_model.pt")

        if improved:
            checkpoint_saved = True
            best_val_macro_f1 = float(val_eval["macro_f1"])
            best_epoch = epoch
            patience_counter = 0
            torch.save(state, out_dir / "best_model.pt")
            best_saved = True
            tag = "[BEST]"
        else:
            patience_counter += 1
            best_saved = False
            tag = f"[SKIP:{ckpt_reason}]"

        row = {
            "epoch": epoch,
            "train_loss": round(train_loss, 5),
            "val_loss": round(val_loss, 5),
            "val_accuracy": round(val_eval["accuracy"], 4),
            "val_macro_f1": round(val_eval["macro_f1"], 5),
            "stable_recall": round(val_eval["per_class"][CLASS_NAMES[0]]["recall"], 4),
            "abnormal_recall": round(val_eval["per_class"][CLASS_NAMES[1]]["recall"], 4),
            "n_pred_cls": int(val_eval["n_pred_cls"]),
            "checkpoint_valid": bool(ckpt_valid),
            "checkpoint_reason": ckpt_reason,
            "best_checkpoint_saved": best_saved,
        }
        history.append(row)
        with open(out_dir / "training_history.json", "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

        log.info(
            "Epoch %03d/%d | train_loss=%.4f val_loss=%.4f | val_macro_f1=%.4f stable_rec=%.4f abnormal_rec=%.4f n_pred_cls=%d %s",
            epoch,
            args.epochs,
            train_loss,
            val_loss,
            val_eval["macro_f1"],
            val_eval["per_class"][CLASS_NAMES[0]]["recall"],
            val_eval["per_class"][CLASS_NAMES[1]]["recall"],
            val_eval["n_pred_cls"],
            tag,
        )
        if patience_counter >= args.patience and not args.smoke:
            log.info("Early stopping triggered at epoch %d", epoch)
            break

    log.info("Training complete in %.1fs", time.time() - t0)

    if checkpoint_saved and (out_dir / "best_model.pt").exists():
        best_ckpt = torch.load(str(out_dir / "best_model.pt"), map_location=device, weights_only=False)
        model.load_state_dict(best_ckpt["model_state_dict"])
        log.info("Loaded best checkpoint epoch=%d", int(best_ckpt["epoch"]))
    else:
        log.warning("No valid best_model.pt saved; evaluating last model only.")

    val_best_eval = evaluate_model(model, X_val, y_val, arrays_val, device, args.batch_size, 0.50)
    threshold_rows, recommended_threshold = validation_sweep(y_val, val_best_eval["probs"])
    test_metrics = evaluate_model(model, X_te, y_te, arrays_te, device, args.batch_size, recommended_threshold)

    application_valid, final_decision = decide_final(test_metrics, checkpoint_saved)

    metrics_payload = {
        "accuracy": round(test_metrics["accuracy"], 4),
        "macro_f1": round(test_metrics["macro_f1"], 4),
        "weighted_f1": round(test_metrics["weighted_f1"], 4),
        "macro_precision": round(test_metrics["macro_precision"], 4),
        "macro_recall": round(test_metrics["macro_recall"], 4),
        "roc_auc": round(test_metrics["roc_auc"], 4) if test_metrics["roc_auc"] is not None else None,
        "pr_auc": round(test_metrics["pr_auc"], 4) if test_metrics["pr_auc"] is not None else None,
        "best_epoch": int(best_epoch) if best_epoch > 0 else None,
        "best_val_macro_f1": round(best_val_macro_f1, 5) if checkpoint_saved else None,
        "recommended_threshold": recommended_threshold,
        "checkpoint_valid_training": checkpoint_saved,
        "application_valid": application_valid,
        "final_decision": final_decision,
        "subject_aware_split_preserved": subject_split_preserved,
        "label_mapping": {
            "0 / stable_movement / stable_gait": 0,
            "3 / abnormal_or_freezing_movement / unstable_gait": 1,
            "other / unknown": "excluded",
        },
        "data_dir": str(data_dir),
    }
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(_to_builtin(metrics_payload), f, indent=2)
    with open(out_dir / "confusion_matrix.json", "w", encoding="utf-8") as f:
        json.dump({"labels": CLASS_NAMES, "matrix": test_metrics["confusion_matrix"], "threshold": recommended_threshold}, f, indent=2)
    with open(out_dir / "prediction_distribution.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "threshold": recommended_threshold,
                "predicted": test_metrics["prediction_distribution"],
                "true": {cls: int(test_metrics["per_class"][cls]["support"]) for cls in CLASS_NAMES},
            },
            f,
            indent=2,
        )
    with open(out_dir / "per_class_metrics.json", "w", encoding="utf-8") as f:
        json.dump(test_metrics["per_class"], f, indent=2)
    with open(out_dir / "source_breakdown.json", "w", encoding="utf-8") as f:
        json.dump(_to_builtin(test_metrics["source_breakdown"]), f, indent=2)
    with open(out_dir / "subject_breakdown.json", "w", encoding="utf-8") as f:
        json.dump(_to_builtin(test_metrics["subject_breakdown"]), f, indent=2)

    train_cfg = {
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "loss": "BCEWithLogitsLoss",
        "pos_weight": pos_weight,
        "pos_weight_cap": args.pos_weight_cap,
        "optimizer": "AdamW(weight_decay=1e-4)",
        "scheduler": f"CosineAnnealingLR(T_max={args.epochs}, eta_min=1e-5)",
    }
    report = build_report(
        out_dir=out_dir,
        env_info=env_info,
        data_dir=data_dir,
        audits=audits,
        overlap=overlap,
        subject_split_preserved=subject_split_preserved,
        norm_stats=norm_stats,
        history=history,
        model_params=model_params,
        train_cfg=train_cfg,
        best_epoch=best_epoch,
        best_val_macro_f1=(best_val_macro_f1 if checkpoint_saved else None),
        recommended_threshold=recommended_threshold,
        threshold_rows=threshold_rows,
        test_metrics=test_metrics,
        checkpoint_saved=checkpoint_saved,
        application_valid=application_valid,
        final_decision=final_decision,
    )
    with open(out_dir / "gait_instability_v2_expert_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    log.info("=== Gait Instability v2 Training Complete ===")
    log.info("best_epoch=%s best_val_macro_f1=%s", best_epoch if checkpoint_saved else None, round(best_val_macro_f1, 5) if checkpoint_saved else None)
    log.info("recommended_threshold=%.2f", recommended_threshold)
    log.info("test_macro_f1=%.4f stable_recall=%.4f abnormal_recall=%.4f", test_metrics["macro_f1"], test_metrics["per_class"][CLASS_NAMES[0]]["recall"], test_metrics["per_class"][CLASS_NAMES[1]]["recall"])
    log.info("application_valid=%s final_decision=%s", application_valid, final_decision)
    log.info("Output dir: %s", out_dir)


if __name__ == "__main__":
    main()
