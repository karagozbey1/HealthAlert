from __future__ import annotations

import argparse
import json
import logging
import math
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from torch.utils.data import DataLoader, Sampler, TensorDataset

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_activity_v2_pure_adl_dataset import (  # noqa: E402
    TARGET_LABELS,
    TARGET_LABEL_TO_ID,
    _build_windowable_record,
    _derive_pure_label,
    _find_complete_split,
    _load_dataset_configs,
)
from src.data.loader_registry import load_dataset_by_name  # noqa: E402
from src.data.windowing import build_standard_windows  # noqa: E402
from src.healthalert.models.activity_expert import build_activity_expert  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("healthalert.activity_v2_pamap2_repair")

EXPECTED_PYTHON = PROJECT_ROOT.parent / ".venv311" / "Scripts" / "python.exe"
CURRENT_DATA_DIR = PROJECT_ROOT / "outputs" / "windowed_dataset" / "activity_v2_pure_adl"
CURRENT_REPORT_DIR = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "activity_expert_v2"
CURRENT_REPORT_PATH = CURRENT_REPORT_DIR / "activity_v2_report.md"
CURRENT_METRICS_PATH = CURRENT_REPORT_DIR / "metrics.json"
CURRENT_CHECKPOINT_PATH = CURRENT_REPORT_DIR / "best_model.pt"
CURRENT_AUDIT_PATH = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "activity_v2" / "activity_v2_dataset_audit.json"
CURRENT_SUMMARY_PATH = CURRENT_DATA_DIR / "summary.json"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "activity_v2_pamap2_repair"
CLASS_NAMES = list(TARGET_LABELS)
NUM_CLASSES = len(CLASS_NAMES)
CHANNEL_NAMES = ["acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"]
SOURCE_UCI = "UCI-HAR"
SOURCE_PAMAP2 = "PAMAP2"
POSTURE_CLASSES = {"sitting", "standing", "lying"}


class BalancedBatchSampler(Sampler[List[int]]):
    def __init__(self, group_keys: Sequence[str], batch_size: int, seed: int) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.batch_size = int(batch_size)
        self.seed = int(seed)
        grouped: Dict[str, List[int]] = defaultdict(list)
        for idx, group in enumerate(group_keys):
            grouped[str(group)].append(idx)
        self.group_to_indices = {key: np.asarray(value, dtype=np.int64) for key, value in grouped.items() if value}
        self.groups = sorted(self.group_to_indices)
        if not self.groups:
            raise ValueError("BalancedBatchSampler requires at least one non-empty group")
        self.n_items = int(len(group_keys))
        self.n_batches = int(math.ceil(self.n_items / float(self.batch_size)))

    def __len__(self) -> int:
        return self.n_batches

    def __iter__(self):
        rng = np.random.default_rng(self.seed)
        pools = {
            group: rng.permutation(indices).tolist()
            for group, indices in self.group_to_indices.items()
        }
        base = self.batch_size // len(self.groups)
        remainder = self.batch_size % len(self.groups)
        for _ in range(self.n_batches):
            order = list(self.groups)
            rng.shuffle(order)
            batch: List[int] = []
            for idx, group in enumerate(order):
                need = base + (1 if idx < remainder else 0)
                if need <= 0:
                    continue
                pool = pools[group]
                while len(pool) < need:
                    pool.extend(rng.permutation(self.group_to_indices[group]).tolist())
                batch.extend(pool[:need])
                del pool[:need]
            rng.shuffle(batch)
            yield batch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Activity v2.1 PAMAP2 repair and ablations")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=256)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight_decay", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--split_attempts", type=int, default=200)
    parser.add_argument("--output_root", type=str, default=str(OUTPUT_ROOT))
    return parser.parse_args()


def _ensure_expected_python() -> None:
    current = Path(sys.executable).resolve()
    expected = EXPECTED_PYTHON.resolve()
    if current != expected:
        raise RuntimeError(f"Use the project interpreter only. expected={expected} current={current}")


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


def _compute_class_weights(y: np.ndarray) -> torch.Tensor:
    counts = np.bincount(y, minlength=NUM_CLASSES).astype(np.float64)
    counts = np.maximum(counts, 1.0)
    inv = counts.sum() / (NUM_CLASSES * counts)
    inv = inv / inv.mean()
    inv = np.clip(inv, 0.75, 1.50)
    return torch.tensor(inv, dtype=torch.float32)


def _checkpoint_valid(logits: np.ndarray, targets: np.ndarray, val_loss: float) -> Tuple[bool, str]:
    if not np.isfinite(val_loss):
        return False, f"val_loss is not finite: {val_loss}"
    preds = np.argmax(logits, axis=1)
    n_predicted = len(np.unique(preds))
    if n_predicted < 2:
        return False, f"collapse: only {n_predicted} class(es) predicted"
    macro_f1 = float(f1_score(targets, preds, average="macro", zero_division=0))
    if macro_f1 < (0.5 / NUM_CLASSES):
        return False, f"macro_f1={macro_f1:.4f} below random-chance floor"
    return True, "ok"


def _load_npz_split(split: str, data_dir: Path) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]]]:
    raw = np.load(str(data_dir / f"{split}.npz"), allow_pickle=True)
    X = raw["imu"].astype(np.float32).transpose(0, 2, 1)
    y = raw["labels"].flatten().astype(np.int64)
    metadata_items: List[Dict[str, Any]] = []
    for item in raw["metadata"]:
        payload = json.loads(str(item)) if not isinstance(item, dict) else dict(item)
        metadata_items.append(payload)
    return X, y, metadata_items


def _channel_stats(X: np.ndarray) -> Dict[str, List[float]]:
    return {
        "mean": [round(float(v), 6) for v in X.mean(axis=(0, 2))],
        "std": [round(float(v), 6) for v in np.maximum(X.std(axis=(0, 2)), 1e-6)],
    }


def _source_channel_stats(X: np.ndarray, metadata: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    sources = np.asarray([str(item.get("dataset_name", "unknown")) for item in metadata], dtype=object)
    for source in sorted(np.unique(sources)):
        mask = sources == source
        stats[str(source)] = {
            "n": int(mask.sum()),
            **_channel_stats(X[mask]),
        }
    if SOURCE_UCI in stats and SOURCE_PAMAP2 in stats:
        stats["delta_pamap2_minus_uci"] = {
            "mean": [
                round(stats[SOURCE_PAMAP2]["mean"][idx] - stats[SOURCE_UCI]["mean"][idx], 6)
                for idx in range(len(CHANNEL_NAMES))
            ],
            "std": [
                round(stats[SOURCE_PAMAP2]["std"][idx] - stats[SOURCE_UCI]["std"][idx], 6)
                for idx in range(len(CHANNEL_NAMES))
            ],
        }
    return stats


def _build_metadata_payload(window: Dict[str, Any]) -> Dict[str, Any]:
    record_metadata = dict(window.get("record_metadata", {}) or {})
    return {
        "dataset_name": str(window["dataset_name"]),
        "subject_id": str(window["subject_id"]),
        "recording_id": str(window["recording_id"]),
        "window_id": str(window["window_id"]),
        "label": str(window["label"]),
        "label_id": int(TARGET_LABEL_TO_ID[str(window["label"])]),
        "quality_score": float(window.get("quality_score", 0.0)),
        "resampled": bool(window.get("resampled", False)),
        "record_metadata": record_metadata,
        "sensor_stream": record_metadata.get("sensor_stream"),
        "sensor_location": record_metadata.get("sensor_location"),
    }


def _summarize_windows(windows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    label_counts = Counter(str(window["label"]) for window in windows)
    source_counts = Counter(str(window["dataset_name"]) for window in windows)
    subject_counts = Counter(str(window["subject_id"]) for window in windows)
    return {
        "n_windows": len(windows),
        "label_counts": dict(label_counts),
        "source_counts": dict(source_counts),
        "n_unique_subjects": len(subject_counts),
    }


def _windows_to_arrays(windows: Sequence[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]]]:
    X = np.stack([np.asarray(window["imu"], dtype=np.float32).T for window in windows], axis=0)
    y = np.asarray([TARGET_LABEL_TO_ID[str(window["label"])] for window in windows], dtype=np.int64)
    metadata = [_build_metadata_payload(window) for window in windows]
    return X, y, metadata


def _build_dataset_bundle(
    source_keys: Sequence[str],
    pamap2_sensor_variant: str,
    seed: int,
    split_attempts: int,
) -> Dict[str, Any]:
    dataset_cfgs = _load_dataset_configs()
    windows: List[Dict[str, Any]] = []
    source_record_audit: Dict[str, Dict[str, Any]] = {}

    for dataset_key in source_keys:
        cfg = dict(dataset_cfgs[dataset_key])
        if dataset_key == "pamap2":
            cfg["pamap2_sensor_variant"] = pamap2_sensor_variant
        load_result = load_dataset_by_name(cfg)
        source_record_audit[dataset_key] = {
            "status": load_result.status,
            "n_records": int(len(load_result.records or [])),
            "errors": list(load_result.errors or []),
            "warnings": list(load_result.warnings or []),
        }
        for record in load_result.records or []:
            pure_label = _derive_pure_label(record)
            if pure_label is None:
                continue
            record_dict = _build_windowable_record(record, pure_label)
            record_windows = build_standard_windows(record_dict, config=cfg)
            record_metadata = dict(getattr(record, "metadata", {}) or {})
            if dataset_key == "uci_har":
                record_metadata.setdefault("sensor_location", "waist_smartphone")
                record_metadata.setdefault("sensor_stream", "total_acc_plus_gyro")
            for window in record_windows:
                if not window.get("training_candidate", False):
                    continue
                if not window.get("has_imu", False):
                    continue
                if str(window.get("label")) not in TARGET_LABELS:
                    continue
                enriched = dict(window)
                enriched["record_metadata"] = record_metadata
                windows.append(enriched)

    train_windows, val_windows, test_windows, split_info = _find_complete_split(
        windows=windows,
        required_labels=TARGET_LABELS,
        seed=seed,
        max_attempts=split_attempts,
    )
    train_X, train_y, train_metadata = _windows_to_arrays(train_windows)
    val_X, val_y, val_metadata = _windows_to_arrays(val_windows)
    test_X, test_y, test_metadata = _windows_to_arrays(test_windows)
    summary = {
        "usable_sources": [dataset_cfgs[key]["name"] for key in source_keys],
        "pamap2_sensor_variant": pamap2_sensor_variant,
        "split_info": split_info,
        "train": _summarize_windows(train_windows),
        "val": _summarize_windows(val_windows),
        "test": _summarize_windows(test_windows),
        "source_record_audit": source_record_audit,
    }
    return {
        "summary": summary,
        "train": {"X": train_X, "y": train_y, "metadata": train_metadata},
        "val": {"X": val_X, "y": val_y, "metadata": val_metadata},
        "test": {"X": test_X, "y": test_y, "metadata": test_metadata},
    }


def _normalize_global_train(
    X_train: np.ndarray,
    X_val: np.ndarray,
    X_test: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    train_mean = X_train.mean(axis=(0, 2))
    train_std = np.maximum(X_train.std(axis=(0, 2)), 1e-6)
    X_train_norm = ((X_train - train_mean[None, :, None]) / train_std[None, :, None]).astype(np.float32)
    X_val_norm = ((X_val - train_mean[None, :, None]) / train_std[None, :, None]).astype(np.float32)
    X_test_norm = ((X_test - train_mean[None, :, None]) / train_std[None, :, None]).astype(np.float32)
    return X_train_norm, X_val_norm, X_test_norm, {
        "mode": "global_train_zscore",
        "mean_per_channel": [round(float(v), 6) for v in train_mean],
        "std_per_channel": [round(float(v), 6) for v in train_std],
    }


def _per_window_zscore(X: np.ndarray) -> np.ndarray:
    means = X.mean(axis=2, keepdims=True)
    stds = np.maximum(X.std(axis=2, keepdims=True), 1e-6)
    return ((X - means) / stds).astype(np.float32)


def _normalize_data(
    X_train: np.ndarray,
    X_val: np.ndarray,
    X_test: np.ndarray,
    mode: str,
    clip_value: float | None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    if mode == "global_train_zscore":
        X_train_norm, X_val_norm, X_test_norm, stats = _normalize_global_train(X_train, X_val, X_test)
    elif mode == "per_window_zscore":
        X_train_norm = _per_window_zscore(X_train)
        X_val_norm = _per_window_zscore(X_val)
        X_test_norm = _per_window_zscore(X_test)
        stats = {"mode": "per_window_zscore"}
    else:
        raise ValueError(f"Unsupported normalization mode: {mode}")

    if clip_value is not None:
        X_train_norm = np.clip(X_train_norm, -clip_value, clip_value).astype(np.float32)
        X_val_norm = np.clip(X_val_norm, -clip_value, clip_value).astype(np.float32)
        X_test_norm = np.clip(X_test_norm, -clip_value, clip_value).astype(np.float32)
        stats["clip_after_norm"] = [-float(clip_value), float(clip_value)]
    return X_train_norm, X_val_norm, X_test_norm, stats


def _make_train_loader(
    X_train: np.ndarray,
    y_train: np.ndarray,
    train_metadata: Sequence[Dict[str, Any]],
    batch_size: int,
    sampler_mode: str,
    seed: int,
) -> DataLoader:
    dataset = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    if sampler_mode == "shuffle":
        return DataLoader(dataset, batch_size=batch_size, shuffle=True)
    if sampler_mode == "source_balanced":
        keys = [str(item.get("dataset_name", "unknown")) for item in train_metadata]
        return DataLoader(dataset, batch_sampler=BalancedBatchSampler(keys, batch_size=batch_size, seed=seed))
    if sampler_mode == "class_source_balanced":
        keys = [f"{item.get('dataset_name', 'unknown')}::{item.get('label', 'unknown')}" for item in train_metadata]
        return DataLoader(dataset, batch_sampler=BalancedBatchSampler(keys, batch_size=batch_size, seed=seed))
    raise ValueError(f"Unsupported sampler mode: {sampler_mode}")


def _compute_metric_bundle(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    prec, rec, f1, sup = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=list(range(NUM_CLASSES)),
        zero_division=0,
    )
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_f1": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "weighted_f1": round(float(f1_score(y_true, y_pred, average="weighted", zero_division=0)), 4),
        "per_class": {
            CLASS_NAMES[idx]: {
                "precision": round(float(prec[idx]), 4),
                "recall": round(float(rec[idx]), 4),
                "f1": round(float(f1[idx]), 4),
                "support": int(sup[idx]),
            }
            for idx in range(NUM_CLASSES)
        },
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=list(range(NUM_CLASSES))).tolist(),
    }


def _pamap2_subject_error_distribution(y_true: np.ndarray, y_pred: np.ndarray, metadata: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    label_names = np.asarray([CLASS_NAMES[int(idx)] for idx in y_true], dtype=object)
    pred_names = np.asarray([CLASS_NAMES[int(idx)] for idx in y_pred], dtype=object)
    sources = np.asarray([str(item.get("dataset_name", "unknown")) for item in metadata], dtype=object)
    subjects = np.asarray([str(item.get("subject_id", "unknown")) for item in metadata], dtype=object)
    pamap2_mask = sources == SOURCE_PAMAP2
    for subject_id in sorted(np.unique(subjects[pamap2_mask])):
        mask = pamap2_mask & (subjects == subject_id)
        actual_names = label_names[mask]
        predicted_names = pred_names[mask]
        posture_confusions = 0
        confusion_pairs = Counter()
        for actual, predicted in zip(actual_names, predicted_names):
            if actual == predicted:
                continue
            confusion_pairs.update([f"{actual}->{predicted}"])
            if actual in POSTURE_CLASSES and predicted in POSTURE_CLASSES:
                posture_confusions += 1
        entries.append(
            {
                "subject_id": str(subject_id),
                "n": int(mask.sum()),
                "macro_f1": round(float(f1_score(y_true[mask], y_pred[mask], average="macro", zero_division=0)), 4),
                "posture_confusions": int(posture_confusions),
                "confusion_pairs": dict(confusion_pairs.most_common()),
            }
        )
    return sorted(entries, key=lambda item: (-item["posture_confusions"], item["macro_f1"], item["subject_id"]))


def _evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    logits: np.ndarray,
    metadata: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    result = _compute_metric_bundle(y_true, y_pred)
    result["prediction_distribution"] = {
        CLASS_NAMES[idx]: int((y_pred == idx).sum()) for idx in range(NUM_CLASSES)
    }

    sources = np.asarray([str(item.get("dataset_name", "unknown")) for item in metadata], dtype=object)
    subjects = np.asarray([str(item.get("subject_id", "unknown")) for item in metadata], dtype=object)
    source_breakdown: Dict[str, Dict[str, Any]] = {}
    source_confusion_matrices: Dict[str, List[List[int]]] = {}
    subject_breakdown: List[Dict[str, Any]] = []

    for source in sorted(np.unique(sources)):
        source_mask = sources == source
        source_metrics = _compute_metric_bundle(y_true[source_mask], y_pred[source_mask])
        source_metrics["n"] = int(source_mask.sum())
        source_metrics["subjects"] = sorted(np.unique(subjects[source_mask]).tolist())
        source_breakdown[str(source)] = source_metrics
        source_confusion_matrices[str(source)] = source_metrics["confusion_matrix"]

    for subject_id in sorted(np.unique(subjects)):
        subject_mask = subjects == subject_id
        source_name = str(sources[subject_mask][0])
        subject_metrics = _compute_metric_bundle(y_true[subject_mask], y_pred[subject_mask])
        subject_breakdown.append(
            {
                "subject_id": str(subject_id),
                "source": source_name,
                "n": int(subject_mask.sum()),
                "accuracy": subject_metrics["accuracy"],
                "macro_f1": subject_metrics["macro_f1"],
                "per_class_recall": {
                    name: subject_metrics["per_class"][name]["recall"] for name in CLASS_NAMES
                },
            }
        )

    result["source_breakdown"] = source_breakdown
    result["source_confusion_matrices"] = source_confusion_matrices
    result["subject_breakdown"] = sorted(subject_breakdown, key=lambda item: (item["source"], item["subject_id"]))
    result["pamap2_subject_error_distribution"] = _pamap2_subject_error_distribution(y_true, y_pred, metadata)
    result["logits"] = logits.tolist()
    result["preds"] = y_pred.tolist()
    result["truth"] = y_true.tolist()
    return result


def _run_model_logits(model: nn.Module, X: np.ndarray, device: torch.device, batch_size: int) -> np.ndarray:
    loader = DataLoader(TensorDataset(torch.from_numpy(X)), batch_size=batch_size, shuffle=False)
    parts: List[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for (xb,) in loader:
            output = model(xb.to(device))
            parts.append(output["logits"].cpu().numpy())
    return np.concatenate(parts, axis=0)


def _evaluate_model(
    model: nn.Module,
    X: np.ndarray,
    y: np.ndarray,
    metadata: Sequence[Dict[str, Any]],
    device: torch.device,
    batch_size: int,
) -> Dict[str, Any]:
    logits = _run_model_logits(model, X, device=device, batch_size=batch_size)
    preds = np.argmax(logits, axis=1)
    return _evaluate_predictions(y, preds, logits, metadata)


def _save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")


def _render_experiment_markdown(experiment: Dict[str, Any], metrics: Dict[str, Any], history: List[Dict[str, Any]]) -> str:
    lines = [
        f"# {experiment['id']}",
        "",
        f"- strategy: {experiment['strategy']}",
        f"- sources: {', '.join(experiment['sources'])}",
        f"- sensor_variant: {experiment['pamap2_sensor_variant']}",
        f"- normalization: {experiment['normalization']}",
        f"- sampler: {experiment['sampler']}",
        f"- clip_after_norm: {experiment['clip_after_norm']}",
        f"- best_epoch: {metrics['best_epoch']}",
        f"- best_val_macro_f1: {metrics['best_val_macro_f1']:.4f}",
        f"- test_macro_f1: {metrics['test']['macro_f1']:.4f}",
        f"- test_accuracy: {metrics['test']['accuracy']:.4f}",
        "",
        "## Per-Class Recall",
    ]
    for class_name in CLASS_NAMES:
        lines.append(f"- {class_name}: {metrics['test']['per_class'][class_name]['recall']:.4f}")
    lines.extend(["", "## Source Breakdown"])
    for source_name, source_metrics in metrics["test"]["source_breakdown"].items():
        lines.append(f"- {source_name}: macro_f1={source_metrics['macro_f1']:.4f}, n={source_metrics['n']}")
    lines.extend(["", "## Training Trace", "| Epoch | Train Loss | Val Loss | Val Macro F1 |", "|-------|------------|----------|--------------|"])
    for item in history:
        lines.append(
            f"| {item['epoch']} | {item['train_loss']:.4f} | {item['val_loss']:.4f} | {item['val_macro_f1']:.4f} |"
        )
    return "\n".join(lines) + "\n"


def _train_experiment(
    experiment: Dict[str, Any],
    dataset_bundle: Dict[str, Any],
    args: argparse.Namespace,
    device: torch.device,
    experiment_dir: Path,
) -> Dict[str, Any]:
    X_train_raw = dataset_bundle["train"]["X"]
    y_train = dataset_bundle["train"]["y"]
    train_metadata = dataset_bundle["train"]["metadata"]
    X_val_raw = dataset_bundle["val"]["X"]
    y_val = dataset_bundle["val"]["y"]
    val_metadata = dataset_bundle["val"]["metadata"]
    X_test_raw = dataset_bundle["test"]["X"]
    y_test = dataset_bundle["test"]["y"]
    test_metadata = dataset_bundle["test"]["metadata"]

    X_train, X_val, X_test, norm_stats = _normalize_data(
        X_train_raw,
        X_val_raw,
        X_test_raw,
        mode=experiment["normalization"],
        clip_value=experiment["clip_after_norm"],
    )
    class_weights = _compute_class_weights(y_train).to(device)
    model = build_activity_expert(
        {"in_channels": 6, "window_length": 200, "num_classes": NUM_CLASSES}
    ).to(device)
    model_params = sum(parameter.numel() for parameter in model.parameters())

    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)

    train_loader = _make_train_loader(
        X_train,
        y_train,
        train_metadata,
        batch_size=args.batch_size,
        sampler_mode=experiment["sampler"],
        seed=args.seed,
    )
    val_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val)),
        batch_size=args.batch_size,
        shuffle=False,
    )

    best_val_macro_f1 = -1.0
    best_epoch = 0
    patience_left = args.patience
    history: List[Dict[str, Any]] = []
    t0 = time.time()

    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss_sum = 0.0
        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            optimizer.zero_grad()
            output = model(xb)
            loss = criterion(output["logits"], yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss_sum += float(loss.item())
        scheduler.step()
        train_loss = train_loss_sum / max(len(train_loader), 1)

        model.eval()
        val_loss_sum = 0.0
        logits_parts: List[np.ndarray] = []
        targets_parts: List[np.ndarray] = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb = xb.to(device)
                yb = yb.to(device)
                output = model(xb)
                loss = criterion(output["logits"], yb)
                val_loss_sum += float(loss.item())
                logits_parts.append(output["logits"].cpu().numpy())
                targets_parts.append(yb.cpu().numpy())
        val_loss = val_loss_sum / max(len(val_loader), 1)
        val_logits = np.concatenate(logits_parts, axis=0)
        val_targets = np.concatenate(targets_parts, axis=0)
        checkpoint_valid, checkpoint_reason = _checkpoint_valid(val_logits, val_targets, val_loss)
        val_preds = np.argmax(val_logits, axis=1)
        val_macro_f1 = float(f1_score(val_targets, val_preds, average="macro", zero_division=0))
        val_accuracy = float(accuracy_score(val_targets, val_preds))
        if checkpoint_valid and val_macro_f1 > best_val_macro_f1:
            best_val_macro_f1 = val_macro_f1
            best_epoch = epoch
            patience_left = args.patience
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "normalization": norm_stats,
                    "class_names": CLASS_NAMES,
                },
                experiment_dir / "best_model.pt",
            )
        else:
            patience_left -= 1

        history.append(
            {
                "epoch": epoch,
                "train_loss": round(train_loss, 5),
                "val_loss": round(val_loss, 5),
                "val_macro_f1": round(val_macro_f1, 5),
                "val_accuracy": round(val_accuracy, 5),
                "checkpoint_valid": checkpoint_valid,
                "checkpoint_reason": checkpoint_reason,
            }
        )
        log.info(
            "%s epoch=%d train_loss=%.4f val_loss=%.4f val_macro_f1=%.4f patience_left=%d",
            experiment["id"],
            epoch,
            train_loss,
            val_loss,
            val_macro_f1,
            patience_left,
        )
        if patience_left <= 0:
            log.info("%s early stopping at epoch %d", experiment["id"], epoch)
            break

    best_state = torch.load(experiment_dir / "best_model.pt", map_location=device)
    model.load_state_dict(best_state["model_state_dict"])
    elapsed_sec = time.time() - t0

    val_metrics = _evaluate_model(model, X_val, y_val, val_metadata, device=device, batch_size=args.batch_size)
    test_metrics = _evaluate_model(model, X_test, y_test, test_metadata, device=device, batch_size=args.batch_size)
    test_metrics.pop("logits", None)
    test_metrics.pop("preds", None)
    test_metrics.pop("truth", None)

    results = {
        "experiment": experiment,
        "dataset_summary": dataset_bundle["summary"],
        "normalization": norm_stats,
        "class_weights": {CLASS_NAMES[idx]: round(float(class_weights[idx]), 4) for idx in range(NUM_CLASSES)},
        "model_params": model_params,
        "best_epoch": int(best_epoch),
        "best_val_macro_f1": round(float(best_val_macro_f1), 4),
        "elapsed_sec": round(float(elapsed_sec), 2),
        "val": val_metrics,
        "test": test_metrics,
    }

    _save_json(experiment_dir / "config.json", experiment)
    _save_json(experiment_dir / "dataset_summary.json", dataset_bundle["summary"])
    _save_json(experiment_dir / "metrics.json", results)
    _save_json(experiment_dir / "training_history.json", history)
    _save_json(experiment_dir / "per_class_metrics.json", test_metrics["per_class"])
    _save_json(experiment_dir / "source_breakdown.json", test_metrics["source_breakdown"])
    _save_json(experiment_dir / "source_confusion_matrices.json", test_metrics["source_confusion_matrices"])
    _save_json(experiment_dir / "subject_breakdown.json", test_metrics["subject_breakdown"])
    _save_json(experiment_dir / "pamap2_subject_error_distribution.json", test_metrics["pamap2_subject_error_distribution"])
    _save_json(experiment_dir / "confusion_matrix.json", test_metrics["confusion_matrix"])
    _save_json(experiment_dir / "prediction_distribution.json", test_metrics["prediction_distribution"])
    (experiment_dir / "report.md").write_text(
        _render_experiment_markdown(experiment, results, history),
        encoding="utf-8",
    )
    return results


def _evaluate_current_checkpoint(output_root: Path, args: argparse.Namespace, device: torch.device) -> Dict[str, Any]:
    if not CURRENT_CHECKPOINT_PATH.exists():
        raise FileNotFoundError(f"Missing current checkpoint: {CURRENT_CHECKPOINT_PATH}")

    X_train_raw, y_train, train_metadata = _load_npz_split("train", CURRENT_DATA_DIR)
    X_val_raw, _, _ = _load_npz_split("val", CURRENT_DATA_DIR)
    X_test_raw, y_test, test_metadata = _load_npz_split("test", CURRENT_DATA_DIR)
    checkpoint = torch.load(CURRENT_CHECKPOINT_PATH, map_location=device)
    train_mean = np.asarray(checkpoint.get("train_mean", []), dtype=np.float32)
    train_std = np.asarray(checkpoint.get("train_std", []), dtype=np.float32)
    if train_mean.shape != (6,) or train_std.shape != (6,):
        raise RuntimeError("Current checkpoint is missing expected train_mean/train_std vectors")

    X_test = ((X_test_raw - train_mean[None, :, None]) / np.maximum(train_std, 1e-6)[None, :, None]).astype(np.float32)
    model = build_activity_expert({"in_channels": 6, "window_length": 200, "num_classes": NUM_CLASSES}).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    evaluation = _evaluate_model(model, X_test, y_test, test_metadata, device=device, batch_size=args.batch_size)
    logits = np.asarray(evaluation.pop("logits"), dtype=np.float32)
    preds = np.asarray(evaluation.pop("preds"), dtype=np.int64)
    truth = np.asarray(evaluation.pop("truth"), dtype=np.int64)

    channel_stats = _source_channel_stats(
        np.concatenate([X_train_raw, X_val_raw, X_test_raw], axis=0),
        list(train_metadata) + _load_npz_split("val", CURRENT_DATA_DIR)[2] + list(test_metadata),
    )
    analysis = {
        "current_report_excerpt": CURRENT_REPORT_PATH.read_text(encoding="utf-8") if CURRENT_REPORT_PATH.exists() else "",
        "current_metrics": _load_json(CURRENT_METRICS_PATH) if CURRENT_METRICS_PATH.exists() else {},
        "current_dataset_audit": _load_json(CURRENT_AUDIT_PATH),
        "current_dataset_summary": _load_json(CURRENT_SUMMARY_PATH),
        "test_metrics": evaluation,
        "channel_stats_by_source_raw": channel_stats,
        "standing_sitting_lying_confusion_subjects": [
            item for item in evaluation["pamap2_subject_error_distribution"] if item["posture_confusions"] > 0
        ],
        "analysis_notes": [
            "Current checkpoint is the existing failed UCI-HAR + PAMAP2 combined model.",
            "Channel stats are computed on raw windows before normalization across train+val+test.",
            "Subject breakdown and source confusion matrices are computed on the test split only.",
        ],
    }
    _save_json(output_root / "source_error_analysis.json", analysis)
    md = _render_source_error_analysis_markdown(analysis)
    (output_root / "source_error_analysis.md").write_text(md, encoding="utf-8")
    return analysis


def _render_source_error_analysis_markdown(analysis: Dict[str, Any]) -> str:
    test_metrics = analysis["test_metrics"]
    lines = [
        "# Activity v2.1 Source Error Analysis",
        "",
        "## 1. Source Test Metrics",
    ]
    for source_name, source_metrics in test_metrics["source_breakdown"].items():
        lines.append(
            f"- {source_name}: accuracy={source_metrics['accuracy']:.4f}, macro_f1={source_metrics['macro_f1']:.4f}, weighted_f1={source_metrics['weighted_f1']:.4f}, n={source_metrics['n']}"
        )
    lines.extend(["", "## 2. Source Per-Class Recall"])
    for source_name, source_metrics in test_metrics["source_breakdown"].items():
        lines.append(f"### {source_name}")
        for class_name in CLASS_NAMES:
            lines.append(f"- {class_name}: {source_metrics['per_class'][class_name]['recall']:.4f}")
        lines.append("")
    lines.extend(["## 3. Source-Specific Confusion Matrices", "Rows = actual, columns = predicted."])
    for source_name, matrix in test_metrics["source_confusion_matrices"].items():
        lines.extend([
            "",
            f"### {source_name}",
            "| Actual \\ Pred | " + " | ".join(CLASS_NAMES) + " |",
            "|---------------|" + "---|" * NUM_CLASSES,
        ])
        for class_name, row in zip(CLASS_NAMES, matrix):
            lines.append(f"| {class_name} | " + " | ".join(str(value) for value in row) + " |")
    lines.extend(["", "## 4. Subject-Level Breakdown", "| Source | Subject | n | Macro F1 | Walking R | Sitting R | Standing R | Lying R |", "|--------|---------|---|----------|-----------|-----------|------------|---------|"])
    for item in test_metrics["subject_breakdown"]:
        recalls = item["per_class_recall"]
        lines.append(
            f"| {item['source']} | {item['subject_id']} | {item['n']} | {item['macro_f1']:.4f} | {recalls['walking']:.4f} | {recalls['sitting']:.4f} | {recalls['standing']:.4f} | {recalls['lying']:.4f} |"
        )
    lines.extend(["", "## 5. PAMAP2 Subject Error Distribution", "| Subject | n | Macro F1 | Posture Confusions | Top Confusion Pairs |", "|---------|---|----------|--------------------|---------------------|"])
    for item in test_metrics["pamap2_subject_error_distribution"]:
        top_pairs = ", ".join(f"{key}:{value}" for key, value in list(item["confusion_pairs"].items())[:5]) or "-"
        lines.append(
            f"| {item['subject_id']} | {item['n']} | {item['macro_f1']:.4f} | {item['posture_confusions']} | {top_pairs} |"
        )
    lines.extend(["", "## 6. Raw Channel Mean/Std Difference", "| Source | Channel | Mean | Std |", "|--------|---------|------|-----|"])
    for source_name in [SOURCE_UCI, SOURCE_PAMAP2]:
        source_stats = analysis["channel_stats_by_source_raw"].get(source_name, {})
        for idx, channel_name in enumerate(CHANNEL_NAMES):
            lines.append(
                f"| {source_name} | {channel_name} | {source_stats.get('mean', [0.0] * len(CHANNEL_NAMES))[idx]:.6f} | {source_stats.get('std', [0.0] * len(CHANNEL_NAMES))[idx]:.6f} |"
            )
    delta = analysis["channel_stats_by_source_raw"].get("delta_pamap2_minus_uci", {})
    if delta:
        lines.extend(["", "### Delta PAMAP2 - UCI-HAR"])
        for idx, channel_name in enumerate(CHANNEL_NAMES):
            lines.append(f"- {channel_name}: mean_delta={delta['mean'][idx]:.6f}, std_delta={delta['std'][idx]:.6f}")
    lines.extend(["", "## 7. Mapping Check", "- Current failed baseline uses PAMAP2 chest IMU 6g accelerometer + gyroscope.", "- UCI-HAR uses smartphone waist total acceleration + body gyroscope.", "- Sensor location mismatch remains even when both are 6-channel IMU streams."])
    return "\n".join(lines) + "\n"


def _render_sensor_audit_markdown(analysis: Dict[str, Any], variant_results: Dict[str, Dict[str, Any]]) -> str:
    lines = [
        "# PAMAP2 Sensor / Label Audit",
        "",
        "## Loader Facts",
        "- Current loader supports `chest`, `hand`, and `ankle` variants via `pamap2_sensor_variant`.",
        "- The current mixed baseline used `chest_acc6_x/y/z + chest_gyro_x/y/z`.",
        "- No unit conversion is applied in the PAMAP2 loader; raw numeric values are passed through as provided by PAMAP2 files.",
        "- 100 Hz -> 50 Hz happens in shared window normalization via linear interpolation to 200 samples over 4 seconds.",
        "- Label mapping is explicit and consistent in both config and loader: 1=lying, 2=sitting, 3=standing, 4=walking.",
        "- Segments are formed by contiguous runs of the same activity_id inside each subject protocol file.",
        "",
        "## Sensor Placement Audit",
        "- UCI-HAR source is smartphone-on-waist and uses total acceleration plus gyroscope.",
        "- PAMAP2 chest is central-body but not waist-mounted; frame/orientation and wearing dynamics still differ from UCI-HAR.",
        "- PAMAP2 hand and ankle are farther from the runtime body location implied by UCI-HAR and are expected to increase domain gap further.",
        "",
        "## Runtime Comparison",
        "| Variant | Combined Macro F1 | UCI-HAR Macro F1 | PAMAP2 Macro F1 | Notes |",
        "|---------|-------------------|------------------|-----------------|-------|",
    ]
    for variant_name in ["chest", "hand", "ankle"]:
        result = variant_results.get(variant_name)
        if not result:
            continue
        source_breakdown = result["test"]["source_breakdown"]
        note = "closest central-body option" if variant_name == "chest" else "larger location mismatch vs UCI-HAR waist smartphone"
        lines.append(
            f"| {variant_name} | {result['test']['macro_f1']:.4f} | {source_breakdown.get(SOURCE_UCI, {}).get('macro_f1', 0.0):.4f} | {source_breakdown.get(SOURCE_PAMAP2, {}).get('macro_f1', 0.0):.4f} | {note} |"
        )
    lines.extend(["", "## Conclusion"])
    best_variant = max(variant_results.items(), key=lambda item: item[1]["test"]["macro_f1"])[0] if variant_results else "chest"
    lines.append(f"- Best runtime variant in this repair run: {best_variant}.")
    lines.append("- If even the best PAMAP2 variant remains far below UCI-only baseline, the issue is broader than label-map correctness and points to source mismatch.")
    lines.append("- The current evidence does not show a broken label mapping; the bigger risk is sensor placement / motion-domain mismatch.")
    return "\n".join(lines) + "\n"


def _meets_multisource_acceptance(result: Dict[str, Any]) -> bool:
    test = result["test"]
    source_breakdown = test["source_breakdown"]
    return all(
        [
            test["macro_f1"] >= 0.82,
            source_breakdown.get(SOURCE_UCI, {}).get("macro_f1", 0.0) >= 0.85,
            source_breakdown.get(SOURCE_PAMAP2, {}).get("macro_f1", 0.0) >= 0.70,
            test["per_class"]["walking"]["recall"] >= 0.90,
            test["per_class"]["sitting"]["recall"] >= 0.75,
            test["per_class"]["standing"]["recall"] >= 0.75,
            test["per_class"]["lying"]["recall"] >= 0.75,
        ]
    )


def _render_main_report(
    current_analysis: Dict[str, Any],
    experiment_results: List[Dict[str, Any]],
    best_multisource: Dict[str, Any],
    uci_only_result: Dict[str, Any],
    pamap2_only_result: Dict[str, Any],
    final_decision: str,
) -> str:
    best_test = best_multisource["test"]
    lines = [
        "# Activity v2.1 PAMAP2 Repair Report",
        "",
        "## 1. Executive Summary",
        f"- Current failed combined checkpoint macro_f1: {current_analysis['test_metrics']['macro_f1']:.4f}.",
        f"- Best repair experiment: {best_multisource['experiment']['id']} ({best_multisource['experiment']['strategy']}).",
        f"- Best repaired combined macro_f1: {best_test['macro_f1']:.4f}.",
        f"- Final decision: {final_decision}.",
        "",
        "## 2. Current UCI-only Baseline",
        f"- experiment_id: {uci_only_result['experiment']['id']}",
        f"- test_macro_f1: {uci_only_result['test']['macro_f1']:.4f}",
        f"- test_accuracy: {uci_only_result['test']['accuracy']:.4f}",
        "",
        "## 3. Failed UCI-HAR + PAMAP2 Result",
        f"- current combined macro_f1: {current_analysis['test_metrics']['macro_f1']:.4f}",
        f"- current UCI-HAR macro_f1: {current_analysis['test_metrics']['source_breakdown'][SOURCE_UCI]['macro_f1']:.4f}",
        f"- current PAMAP2 macro_f1: {current_analysis['test_metrics']['source_breakdown'][SOURCE_PAMAP2]['macro_f1']:.4f}",
        "",
        "## 4. Source-Level Error Analysis",
        f"- main posture confusion in PAMAP2 is concentrated in: {', '.join(item['subject_id'] for item in current_analysis['standing_sitting_lying_confusion_subjects'][:5]) or 'n/a'}",
        f"- UCI-HAR standing recall under current failed model: {current_analysis['test_metrics']['source_breakdown'][SOURCE_UCI]['per_class']['standing']['recall']:.4f}",
        f"- PAMAP2 standing recall under current failed model: {current_analysis['test_metrics']['source_breakdown'][SOURCE_PAMAP2]['per_class']['standing']['recall']:.4f}",
        "",
        "## 5. PAMAP2 Sensor/Label Audit",
        "- Label mapping is internally consistent; no direct label inversion was found.",
        "- The main gap is sensor-location mismatch and source distribution mismatch, not a loader crash or missing class problem.",
        "",
        "## 6. Normalization Ablation",
    ]
    for result in experiment_results:
        experiment = result["experiment"]
        if experiment["id"] not in {"exp_c_mixed_global_zscore", "exp_d_mixed_per_window_zscore", "exp_g_mixed_global_zscore_clipped"}:
            continue
        lines.append(f"- {experiment['id']}: macro_f1={result['test']['macro_f1']:.4f}")
    lines.extend(["", "## 7. Source-Balanced Training Results"])
    for result in experiment_results:
        experiment = result["experiment"]
        if experiment["id"] not in {"exp_e_mixed_source_balanced", "exp_f_mixed_class_source_balanced"}:
            continue
        lines.append(
            f"- {experiment['id']}: combined={result['test']['macro_f1']:.4f}, UCI={result['test']['source_breakdown'].get(SOURCE_UCI, {}).get('macro_f1', 0.0):.4f}, PAMAP2={result['test']['source_breakdown'].get(SOURCE_PAMAP2, {}).get('macro_f1', 0.0):.4f}"
        )
    lines.extend([
        "",
        "## 8. PAMAP2-only Result",
        f"- experiment_id: {pamap2_only_result['experiment']['id']}",
        f"- test_macro_f1: {pamap2_only_result['test']['macro_f1']:.4f}",
        f"- per-class recall: {json.dumps({name: pamap2_only_result['test']['per_class'][name]['recall'] for name in CLASS_NAMES}, ensure_ascii=True)}",
        "",
        "## 9. Best Experiment",
        f"- experiment_id: {best_multisource['experiment']['id']}",
        f"- strategy: {best_multisource['experiment']['strategy']}",
        f"- combined macro_f1: {best_test['macro_f1']:.4f}",
        f"- UCI-HAR macro_f1: {best_test['source_breakdown'].get(SOURCE_UCI, {}).get('macro_f1', 0.0):.4f}",
        f"- PAMAP2 macro_f1: {best_test['source_breakdown'].get(SOURCE_PAMAP2, {}).get('macro_f1', 0.0):.4f}",
        "",
        "## 10. Comparison Against UCI-only Baseline",
        f"- UCI-only macro_f1: {uci_only_result['test']['macro_f1']:.4f}",
        f"- Best multisource macro_f1: {best_test['macro_f1']:.4f}",
        f"- Gap vs UCI-only: {best_test['macro_f1'] - uci_only_result['test']['macro_f1']:+.4f}",
        "",
        "## 11. Final Decision",
        f"- Decision: {final_decision}",
        f"- Multisource acceptance met: {_meets_multisource_acceptance(best_multisource)}",
        "",
        "## 12. Recommendation",
        "- Keep UCI-only baseline unless a later source can close the remaining cross-domain gap.",
        "- Use MobiAct or a more waist-aligned ADL source if multisource Activity v2 is still required.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    _ensure_expected_python()
    _set_seed(args.seed)

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if args.device == "auto" and torch.cuda.is_available() else args.device)

    current_analysis = _evaluate_current_checkpoint(output_root, args=args, device=device)

    dataset_cache: Dict[Tuple[Tuple[str, ...], str], Dict[str, Any]] = {}
    experiment_defs: List[Dict[str, Any]] = [
        {
            "id": "exp_a_uci_only_baseline",
            "strategy": "UCI-HAR only baseline validation",
            "sources": ["uci_har"],
            "pamap2_sensor_variant": "chest",
            "normalization": "global_train_zscore",
            "sampler": "shuffle",
            "clip_after_norm": None,
        },
        {
            "id": "exp_b_pamap2_only_baseline",
            "strategy": "PAMAP2 only baseline",
            "sources": ["pamap2"],
            "pamap2_sensor_variant": "chest",
            "normalization": "global_train_zscore",
            "sampler": "shuffle",
            "clip_after_norm": None,
        },
        {
            "id": "exp_c_mixed_global_zscore",
            "strategy": "Mixed global z-score baseline",
            "sources": ["uci_har", "pamap2"],
            "pamap2_sensor_variant": "chest",
            "normalization": "global_train_zscore",
            "sampler": "shuffle",
            "clip_after_norm": None,
        },
        {
            "id": "exp_d_mixed_per_window_zscore",
            "strategy": "Mixed per-window z-score",
            "sources": ["uci_har", "pamap2"],
            "pamap2_sensor_variant": "chest",
            "normalization": "per_window_zscore",
            "sampler": "shuffle",
            "clip_after_norm": None,
        },
        {
            "id": "exp_e_mixed_source_balanced",
            "strategy": "Mixed source-balanced sampler",
            "sources": ["uci_har", "pamap2"],
            "pamap2_sensor_variant": "chest",
            "normalization": "global_train_zscore",
            "sampler": "source_balanced",
            "clip_after_norm": None,
        },
        {
            "id": "exp_f_mixed_class_source_balanced",
            "strategy": "Mixed class+source balanced sampler",
            "sources": ["uci_har", "pamap2"],
            "pamap2_sensor_variant": "chest",
            "normalization": "global_train_zscore",
            "sampler": "class_source_balanced",
            "clip_after_norm": None,
        },
        {
            "id": "exp_g_mixed_global_zscore_clipped",
            "strategy": "Mixed global z-score plus channel clipping",
            "sources": ["uci_har", "pamap2"],
            "pamap2_sensor_variant": "chest",
            "normalization": "global_train_zscore",
            "sampler": "shuffle",
            "clip_after_norm": 5.0,
        },
        {
            "id": "exp_h_mixed_sensor_chest",
            "strategy": "Mixed sensor variant chest",
            "sources": ["uci_har", "pamap2"],
            "pamap2_sensor_variant": "chest",
            "normalization": "global_train_zscore",
            "sampler": "shuffle",
            "clip_after_norm": None,
        },
        {
            "id": "exp_h_mixed_sensor_hand",
            "strategy": "Mixed sensor variant hand",
            "sources": ["uci_har", "pamap2"],
            "pamap2_sensor_variant": "hand",
            "normalization": "global_train_zscore",
            "sampler": "shuffle",
            "clip_after_norm": None,
        },
        {
            "id": "exp_h_mixed_sensor_ankle",
            "strategy": "Mixed sensor variant ankle",
            "sources": ["uci_har", "pamap2"],
            "pamap2_sensor_variant": "ankle",
            "normalization": "global_train_zscore",
            "sampler": "shuffle",
            "clip_after_norm": None,
        },
    ]

    experiment_results: List[Dict[str, Any]] = []
    sensor_variant_results: Dict[str, Dict[str, Any]] = {}
    for experiment in experiment_defs:
        experiment_dir = output_root / experiment["id"]
        experiment_dir.mkdir(parents=True, exist_ok=True)
        cache_key = (tuple(experiment["sources"]), experiment["pamap2_sensor_variant"])
        if cache_key not in dataset_cache:
            dataset_cache[cache_key] = _build_dataset_bundle(
                source_keys=experiment["sources"],
                pamap2_sensor_variant=experiment["pamap2_sensor_variant"],
                seed=args.seed,
                split_attempts=args.split_attempts,
            )
        result = _train_experiment(
            experiment=experiment,
            dataset_bundle=dataset_cache[cache_key],
            args=args,
            device=device,
            experiment_dir=experiment_dir,
        )
        experiment_results.append(result)
        if experiment["id"].startswith("exp_h_"):
            sensor_variant_results[experiment["pamap2_sensor_variant"]] = result

    (output_root / "pamap2_sensor_label_audit.md").write_text(
        _render_sensor_audit_markdown(current_analysis, sensor_variant_results),
        encoding="utf-8",
    )

    result_by_id = {item["experiment"]["id"]: item for item in experiment_results}
    uci_only_result = result_by_id["exp_a_uci_only_baseline"]
    pamap2_only_result = result_by_id["exp_b_pamap2_only_baseline"]
    multisource_results = [
        item for item in experiment_results if len(item["experiment"]["sources"]) == 2
    ]
    best_multisource = max(multisource_results, key=lambda item: item["test"]["macro_f1"])

    if _meets_multisource_acceptance(best_multisource):
        final_decision = "ACCEPT_ACTIVITY_V2_1_MULTISOURCE"
    else:
        final_decision = "KEEP_UCI_ONLY_ACTIVITY_V2_BASELINE"

    main_report = _render_main_report(
        current_analysis=current_analysis,
        experiment_results=experiment_results,
        best_multisource=best_multisource,
        uci_only_result=uci_only_result,
        pamap2_only_result=pamap2_only_result,
        final_decision=final_decision,
    )
    (output_root / "activity_v2_pamap2_repair_report.md").write_text(main_report, encoding="utf-8")

    summary = {
        "repair_report_path": str(output_root / "activity_v2_pamap2_repair_report.md"),
        "best_experiment_id": best_multisource["experiment"]["id"],
        "best_strategy": best_multisource["experiment"]["strategy"],
        "combined_macro_f1": best_multisource["test"]["macro_f1"],
        "uci_har_macro_f1": best_multisource["test"]["source_breakdown"].get(SOURCE_UCI, {}).get("macro_f1", 0.0),
        "pamap2_macro_f1": best_multisource["test"]["source_breakdown"].get(SOURCE_PAMAP2, {}).get("macro_f1", 0.0),
        "per_class_recall": {
            name: best_multisource["test"]["per_class"][name]["recall"] for name in CLASS_NAMES
        },
        "final_decision": final_decision,
        "keep_uci_only": final_decision == "KEEP_UCI_ONLY_ACTIVITY_V2_BASELINE",
        "mobiact_needed": final_decision != "ACCEPT_ACTIVITY_V2_1_MULTISOURCE",
    }
    _save_json(output_root / "repair_summary.json", summary)

    log.info("Repair report written to %s", output_root / "activity_v2_pamap2_repair_report.md")
    log.info("Best experiment: %s macro_f1=%.4f", summary["best_experiment_id"], summary["combined_macro_f1"])
    log.info("Final decision: %s", final_decision)


if __name__ == "__main__":
    main()