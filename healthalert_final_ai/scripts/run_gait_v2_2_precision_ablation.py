from __future__ import annotations

import argparse
import json
import logging
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import average_precision_score, roc_auc_score
from torch.utils.data import DataLoader, TensorDataset

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.healthalert.models.gait_instability_expert import build_gait_instability_expert  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("gait_v2_2")

EXPECTED_PYTHON = PROJECT_ROOT.parent / ".venv311" / "Scripts" / "python.exe"
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_gait_instability_v2_dataset.py"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "gait_instability_v2_2_ablation"
DATASET_ROOT = PROJECT_ROOT / "outputs" / "windowed_dataset"
REPORT_PATH = OUTPUT_ROOT / "gait_v2_2_precision_recall_report.md"
ALL_RESULTS_PATH = OUTPUT_ROOT / "all_results.json"
DATASET_THRESHOLDS = [0.30, 0.35, 0.40, 0.45]
POS_WEIGHTS = [1.0, 1.25, 1.5, 1.75, 2.0]
LRS = [3e-4, 1e-4]
THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
CLASS_NAMES = ["stable_gait", "abnormal_or_freezing_movement"]
RAW_LABEL_TO_FINAL = {0: 0, 3: 1}
VALID_LABELS = set(RAW_LABEL_TO_FINAL)
EPOCHS = 50
BATCH_SIZE = 256
PATIENCE = 10
SEED = 42
STRONG_FN_DELTA = 10

BASELINE_V21 = {
    "experiment_id": "pw2.0_lr3e-04_ft0.30",
    "frac_threshold": 0.30,
    "pos_weight": 2.0,
    "lr": 3e-4,
    "best_epoch": 23,
    "best_val_auc": 0.78492,
    "selected_threshold": 0.10,
    "test_macro_f1": 0.7631,
    "test_accuracy": 0.8842,
    "stable_precision": 0.9604,
    "stable_recall": 0.9062,
    "stable_f1": 0.9325,
    "abnormal_precision": 0.5054,
    "abnormal_recall": 0.7194,
    "abnormal_f1": 0.5937,
    "TP": 141,
    "TN": 1333,
    "FP": 138,
    "FN": 55,
    "application_valid": True,
    "decision": "ACCEPT_GAIT_V2_1_EXPERT",
    "usage": "low-weight auxiliary only",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Gait v2.2 precision/recall improvement grid")
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--patience", type=int, default=PATIENCE)
    parser.add_argument("--smoke", action="store_true", help="Run a very small validation subset")
    parser.add_argument("--max_experiments", type=int, default=None, help="Optional cap for experiment count")
    parser.add_argument("--skip_dataset_build", action="store_true", help="Reuse existing dataset variants")
    parser.add_argument("--dataset_thresholds", nargs="*", type=float, default=None, help="Optional subset of fraction thresholds")
    parser.add_argument("--pos_weights", nargs="*", type=float, default=None, help="Optional subset of pos_weight values")
    parser.add_argument("--lrs", nargs="*", type=float, default=None, help="Optional subset of learning rates")
    parser.add_argument("--resume_existing", action="store_true", help="Load and keep existing results in all_results.json")
    return parser.parse_args()


def _norm_path(path: Path) -> str:
    return str(path.resolve()).lower()


def _ensure_expected_python() -> None:
    current = Path(sys.executable).resolve()
    expected = EXPECTED_PYTHON.resolve()
    if _norm_path(current) != _norm_path(expected):
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


def _format_lr(lr: float) -> str:
    return f"{lr:.0e}"


def _format_ft(ft: float) -> str:
    return f"{ft:.2f}"


def _format_pw(pos_weight: float) -> str:
    text = f"{pos_weight:.2f}".rstrip("0")
    if text.endswith("."):
        text += "0"
    return text


def _experiment_id(frac_threshold: float, pos_weight: float, lr: float) -> str:
    return f"ft{_format_ft(frac_threshold)}_pw{_format_pw(pos_weight)}_lr{_format_lr(lr)}"


def log_environment() -> None:
    print(f"sys.executable={sys.executable}")
    print(f"sys.version={sys.version}")
    print(f"torch.__version__={torch.__version__}")
    print(f"working_directory={PROJECT_ROOT}")


def dataset_dir_for_threshold(frac_threshold: float) -> Path:
    return DATASET_ROOT / f"gait_instability_v2_ft{_format_ft(frac_threshold)}"


def report_dir_for_threshold(frac_threshold: float) -> Path:
    return PROJECT_ROOT / "outputs" / "hybrid_redesign" / f"gait_label_rescue_ft{_format_ft(frac_threshold)}"


def build_dataset_variant(frac_threshold: float) -> Dict[str, Any]:
    dataset_dir = dataset_dir_for_threshold(frac_threshold)
    report_dir = report_dir_for_threshold(frac_threshold)
    command = [
        str(Path(sys.executable).resolve()),
        str(BUILD_SCRIPT),
        "--abnormal_fraction_threshold",
        f"{frac_threshold:.2f}",
        "--output_dir",
        str(dataset_dir),
        "--report_dir",
        str(report_dir),
    ]
    log.info("Building dataset variant ft=%.2f", frac_threshold)
    subprocess.run(command, cwd=str(PROJECT_ROOT), check=True)
    support_path = report_dir / "gait_v2_support_recount.json"
    if not support_path.exists():
        raise FileNotFoundError(f"Missing support recount: {support_path}")
    with open(support_path, "r", encoding="utf-8") as handle:
        support = json.load(handle)
    return {
        "frac_threshold": frac_threshold,
        "dataset_dir": str(dataset_dir),
        "report_dir": str(report_dir),
        "support": support,
    }


def load_split_raw(data_dir: Path, split: str) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray]]:
    npz_path = data_dir / f"{split}.npz"
    raw = np.load(str(npz_path), allow_pickle=True)
    imu = raw["imu"].astype(np.float32)
    labels_raw = raw["labels"].astype(np.int64).flatten()
    metadata = raw["metadata"]

    keep = np.array([int(label) in VALID_LABELS for label in labels_raw], dtype=bool)
    imu = imu[keep]
    labels = np.array([RAW_LABEL_TO_FINAL[int(label)] for label in labels_raw[keep]], dtype=np.int64)
    metadata = metadata[keep]

    arrays = {
        "labels": labels,
        "imu": imu,
        "metadata": metadata,
        "source": raw["source"][keep] if "source" in raw.files else np.array(["DAPHNET_FOG"] * len(labels), dtype=object),
        "subject_id": raw["subject_id"][keep] if "subject_id" in raw.files else np.array(["unknown"] * len(labels), dtype=object),
        "recording_id": raw["recording_id"][keep] if "recording_id" in raw.files else np.array(["unknown"] * len(labels), dtype=object),
    }
    features = imu.transpose(0, 2, 1).astype(np.float32)
    return features, labels, arrays


def load_dataset_bundle(data_dir: Path) -> Dict[str, Any]:
    bundle: Dict[str, Any] = {}
    for split in ("train", "val", "test"):
        X, y, arrays = load_split_raw(data_dir, split)
        bundle[split] = {"X": X, "y": y, "arrays": arrays}
    return bundle


def compute_norm_stats(X: np.ndarray) -> Dict[str, Any]:
    mean = X.mean(axis=(0, 2))
    std = np.maximum(X.std(axis=(0, 2)), 1e-6)
    return {
        "mean_per_channel": [float(value) for value in mean],
        "std_per_channel": [float(value) for value in std],
    }


def apply_norm(X: np.ndarray, stats: Dict[str, Any]) -> np.ndarray:
    mean = np.asarray(stats["mean_per_channel"], dtype=np.float32)
    std = np.asarray(stats["std_per_channel"], dtype=np.float32)
    return ((X - mean[None, :, None]) / std[None, :, None]).astype(np.float32)


def evaluate_predictions(y_true: np.ndarray, probs: np.ndarray, threshold: float) -> Dict[str, Any]:
    preds = (probs >= threshold).astype(np.int64)
    n_pred_cls = int(len(np.unique(preds)))
    tp = int(((y_true == 1) & (preds == 1)).sum())
    tn = int(((y_true == 0) & (preds == 0)).sum())
    fp = int(((y_true == 0) & (preds == 1)).sum())
    fn = int(((y_true == 1) & (preds == 0)).sum())

    stable_recall = _safe_div(tn, tn + fp)
    abnormal_recall = _safe_div(tp, tp + fn)
    stable_precision = _safe_div(tn, tn + fn)
    abnormal_precision = _safe_div(tp, tp + fp)
    stable_f1 = _safe_div(2 * stable_recall * stable_precision, stable_recall + stable_precision)
    abnormal_f1 = _safe_div(2 * abnormal_recall * abnormal_precision, abnormal_recall + abnormal_precision)
    macro_f1 = (stable_f1 + abnormal_f1) / 2.0
    weighted_f1 = _safe_div(
        stable_f1 * int((y_true == 0).sum()) + abnormal_f1 * int((y_true == 1).sum()),
        len(y_true),
    )
    accuracy = _safe_div(tp + tn, tp + tn + fp + fn)
    counts = np.bincount(preds, minlength=2)
    dominant_cls = int(counts.argmax()) if len(counts) else 0
    dominant_ratio = float(counts.max() / max(len(preds), 1)) if len(counts) else 1.0

    return {
        "threshold": float(threshold),
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "macro_precision": round((stable_precision + abnormal_precision) / 2.0, 4),
        "macro_recall": round((stable_recall + abnormal_recall) / 2.0, 4),
        "n_pred_cls": n_pred_cls,
        "dominant_ratio": dominant_ratio,
        "dominant_predicted_class": CLASS_NAMES[dominant_cls],
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "per_class": {
            CLASS_NAMES[0]: {
                "precision": round(stable_precision, 4),
                "recall": round(stable_recall, 4),
                "f1": round(stable_f1, 4),
                "support": int((y_true == 0).sum()),
            },
            CLASS_NAMES[1]: {
                "precision": round(abnormal_precision, 4),
                "recall": round(abnormal_recall, 4),
                "f1": round(abnormal_f1, 4),
                "support": int((y_true == 1).sum()),
            },
        },
        "prediction_distribution": {
            CLASS_NAMES[0]: int((preds == 0).sum()),
            CLASS_NAMES[1]: int((preds == 1).sum()),
        },
        "preds": preds,
    }


def evaluate_model(
    model: nn.Module,
    X: np.ndarray,
    y: np.ndarray,
    arrays: Dict[str, np.ndarray],
    device: torch.device,
    threshold: float,
) -> Dict[str, Any]:
    model.eval()
    logits_all: List[np.ndarray] = []
    loader = DataLoader(TensorDataset(torch.from_numpy(X)), batch_size=BATCH_SIZE, shuffle=False)
    with torch.no_grad():
        for (xb,) in loader:
            out = model(xb.to(device))
            logits_all.append(out["logit"].detach().cpu().numpy())
    logits = np.concatenate(logits_all, axis=0).astype(np.float64)
    probs = _sigmoid(logits)
    metrics = evaluate_predictions(y, probs, threshold)
    metrics["logits"] = logits
    metrics["probs"] = probs

    if len(np.unique(y)) >= 2:
        metrics["roc_auc"] = round(float(roc_auc_score(y, probs)), 4)
        metrics["pr_auc"] = round(float(average_precision_score(y, probs)), 4)
    else:
        metrics["roc_auc"] = None
        metrics["pr_auc"] = None

    subjects = np.asarray(arrays["subject_id"])
    subject_breakdown: Dict[str, Any] = {}
    for subject in np.unique(subjects):
        mask = subjects == subject
        subject_metrics = evaluate_predictions(y[mask], probs[mask], threshold)
        subject_breakdown[str(subject)] = {
            "n": int(mask.sum()),
            "stable_support": int((y[mask] == 0).sum()),
            "abnormal_support": int((y[mask] == 1).sum()),
            "stable_precision": subject_metrics["per_class"][CLASS_NAMES[0]]["precision"],
            "stable_recall": subject_metrics["per_class"][CLASS_NAMES[0]]["recall"],
            "abnormal_precision": subject_metrics["per_class"][CLASS_NAMES[1]]["precision"],
            "abnormal_recall": subject_metrics["per_class"][CLASS_NAMES[1]]["recall"],
            "macro_f1": subject_metrics["macro_f1"],
            "tp": subject_metrics["tp"],
            "tn": subject_metrics["tn"],
            "fp": subject_metrics["fp"],
            "fn": subject_metrics["fn"],
        }
    metrics["subject_breakdown"] = subject_breakdown
    return metrics


def checkpoint_valid(
    val_targets: np.ndarray,
    val_probs: np.ndarray,
    val_logits: np.ndarray,
    val_loss: float,
    best_auc_so_far: float,
) -> Tuple[bool, str, float]:
    if not math.isfinite(val_loss):
        return False, "val_loss_not_finite", 0.0
    if not np.isfinite(val_logits).all():
        return False, "logits_nan_inf", 0.0
    if len(np.unique(val_targets)) < 2:
        return False, "single_class_in_val", 0.0
    neg_mean = float(val_probs[val_targets == 0].mean())
    pos_mean = float(val_probs[val_targets == 1].mean())
    if abs(pos_mean - neg_mean) < 1e-4:
        return False, "probability_gap_too_small", 0.0
    try:
        val_auc = float(roc_auc_score(val_targets, val_probs))
    except Exception as exc:
        return False, f"auc_error:{exc}", 0.0
    if val_auc <= best_auc_so_far:
        return False, f"no_auc_improvement(auc={val_auc:.4f})", val_auc
    return True, f"ok(auc={val_auc:.4f})", val_auc


def select_validation_threshold(y_true: np.ndarray, probs: np.ndarray) -> Tuple[List[Dict[str, Any]], Dict[str, Any], bool, str]:
    rows: List[Dict[str, Any]] = []
    for threshold in THRESHOLDS:
        metrics = evaluate_predictions(y_true, probs, threshold)
        row = {
            "threshold": round(threshold, 2),
            "stable_precision": metrics["per_class"][CLASS_NAMES[0]]["precision"],
            "stable_recall": metrics["per_class"][CLASS_NAMES[0]]["recall"],
            "abnormal_precision": metrics["per_class"][CLASS_NAMES[1]]["precision"],
            "abnormal_recall": metrics["per_class"][CLASS_NAMES[1]]["recall"],
            "stable_f1": metrics["per_class"][CLASS_NAMES[0]]["f1"],
            "abnormal_f1": metrics["per_class"][CLASS_NAMES[1]]["f1"],
            "macro_f1": metrics["macro_f1"],
            "fp": metrics["fp"],
            "fn": metrics["fn"],
            "tp": metrics["tp"],
            "tn": metrics["tn"],
            "n_pred_cls": metrics["n_pred_cls"],
            "dominant_ratio": round(metrics["dominant_ratio"], 4),
        }
        rows.append(row)

    eligible = [
        row
        for row in rows
        if row["stable_recall"] >= 0.88
        and row["abnormal_recall"] >= 0.70
        and row["abnormal_precision"] >= 0.65
        and row["n_pred_cls"] >= 2
        and row["dominant_ratio"] < 0.98
    ]
    if eligible:
        selected = max(
            eligible,
            key=lambda row: (row["macro_f1"], row["abnormal_precision"], -row["fp"], row["abnormal_recall"]),
        )
        return rows, selected, True, "constraint_satisfied"

    secondary = [
        row
        for row in rows
        if row["stable_recall"] >= 0.88
        and row["abnormal_recall"] >= 0.70
        and row["n_pred_cls"] >= 2
        and row["dominant_ratio"] < 0.98
    ]
    if secondary:
        selected = max(
            secondary,
            key=lambda row: (row["macro_f1"], row["abnormal_precision"], -row["fp"], row["stable_recall"]),
        )
        return rows, selected, False, "secondary_no_precision65"

    selected = max(
        rows,
        key=lambda row: (row["macro_f1"], row["abnormal_precision"], -row["fp"], row["stable_recall"]),
    )
    return rows, selected, False, "fallback_best_macro_f1"


def decide_experiment(
    test_metrics: Dict[str, Any],
    threshold_constraints_met: bool,
) -> Tuple[bool, str]:
    stable_recall = test_metrics["per_class"][CLASS_NAMES[0]]["recall"]
    abnormal_recall = test_metrics["per_class"][CLASS_NAMES[1]]["recall"]
    abnormal_precision = test_metrics["per_class"][CLASS_NAMES[1]]["precision"]
    macro_f1 = test_metrics["macro_f1"]
    fp = test_metrics["fp"]
    fn = test_metrics["fn"]
    n_pred_cls = test_metrics["n_pred_cls"]
    collapse = n_pred_cls < 2 or test_metrics["dominant_ratio"] >= 0.98

    minimum_accept = (
        threshold_constraints_met
        and macro_f1 > BASELINE_V21["test_macro_f1"]
        and stable_recall >= 0.88
        and abnormal_recall >= 0.70
        and abnormal_precision >= 0.65
        and not collapse
    )
    strong_accept = (
        minimum_accept
        and macro_f1 >= 0.80
        and stable_recall >= 0.90
        and abnormal_precision >= 0.70
        and fp < BASELINE_V21["FP"]
        and fn <= BASELINE_V21["FN"] + STRONG_FN_DELTA
    )

    if strong_accept:
        return True, "STRONG_ACCEPT_GAIT_V2_2_EXPERT"
    if minimum_accept:
        return True, "ACCEPT_GAIT_V2_2_EXPERT"
    if collapse:
        return False, "REJECT_GAIT_ML_KEEP_RULE_BASED"
    return False, "KEEP_GAIT_V2_1_BASELINE"


def run_experiment(
    dataset_info: Dict[str, Any],
    pos_weight: float,
    lr: float,
    epochs: int,
    patience: int,
    device: torch.device,
    smoke: bool = False,
) -> Dict[str, Any]:
    frac_threshold = float(dataset_info["frac_threshold"])
    experiment_id = _experiment_id(frac_threshold, pos_weight, lr)
    out_dir = OUTPUT_ROOT / experiment_id
    out_dir.mkdir(parents=True, exist_ok=True)
    console_lines: List[str] = []

    def exp_log(message: str) -> None:
        timestamped = f"[{time.strftime('%H:%M:%S')}] {message}"
        console_lines.append(timestamped)
        log.info("[%s] %s", experiment_id, message)

    t0 = time.time()
    exp_log(
        f"start frac_threshold={frac_threshold:.2f} pos_weight={pos_weight:.2f} lr={lr:.0e} dataset_dir={dataset_info['dataset_dir']}"
    )

    bundle = dataset_info["bundle"]
    X_tr_raw = bundle["train"]["X"]
    y_tr = bundle["train"]["y"]
    arrays_tr = bundle["train"]["arrays"]
    X_val_raw = bundle["val"]["X"]
    y_val = bundle["val"]["y"]
    arrays_val = bundle["val"]["arrays"]
    X_te_raw = bundle["test"]["X"]
    y_te = bundle["test"]["y"]
    arrays_te = bundle["test"]["arrays"]

    n_train_stable = int((y_tr == 0).sum())
    n_train_abnormal = int((y_tr == 1).sum())
    n_val_abnormal = int((y_val == 1).sum())
    n_test_abnormal = int((y_te == 1).sum())
    if n_train_abnormal == 0 or n_val_abnormal == 0 or n_test_abnormal == 0:
        exp_log("dataset invalid: one split has zero abnormal support")
        skipped = {
            "experiment_id": experiment_id,
            "frac_threshold": frac_threshold,
            "pos_weight": pos_weight,
            "lr": lr,
            "skipped": True,
            "skip_reason": "zero_abnormal_support",
            "application_valid": False,
            "decision": "KEEP_GAIT_V2_1_BASELINE",
        }
        with open(out_dir / "console.log", "w", encoding="utf-8") as handle:
            handle.write("\n".join(console_lines) + "\n")
        return skipped

    norm_stats = compute_norm_stats(X_tr_raw)
    X_tr = apply_norm(X_tr_raw, norm_stats)
    X_val = apply_norm(X_val_raw, norm_stats)
    X_te = apply_norm(X_te_raw, norm_stats)

    torch.manual_seed(SEED)
    np.random.seed(SEED)
    model = build_gait_instability_expert({"in_channels": 6, "window_length": 200}).to(device)
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([pos_weight], dtype=torch.float32, device=device)
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-5)

    if smoke:
        rng = np.random.RandomState(SEED)
        train_indices = rng.permutation(len(y_tr))[: min(512, len(y_tr))]
        val_indices = rng.permutation(len(y_val))[: min(512, len(y_val))]
        test_indices = rng.permutation(len(y_te))[: min(768, len(y_te))]
        X_tr = X_tr[train_indices]
        y_tr_fit = y_tr[train_indices]
        X_val = X_val[val_indices]
        y_val_eval = y_val[val_indices]
        arrays_val_eval = {key: value[val_indices] for key, value in arrays_val.items()}
        X_te = X_te[test_indices]
        y_te_eval = y_te[test_indices]
        arrays_te_eval = {key: value[test_indices] for key, value in arrays_te.items()}
    else:
        y_tr_fit = y_tr
        y_val_eval = y_val
        arrays_val_eval = arrays_val
        y_te_eval = y_te
        arrays_te_eval = arrays_te

    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_tr), torch.from_numpy(y_tr_fit.astype(np.float32))),
        batch_size=BATCH_SIZE,
        shuffle=True,
    )
    val_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val_eval.astype(np.float32))),
        batch_size=BATCH_SIZE,
        shuffle=False,
    )

    history: List[Dict[str, Any]] = []
    best_epoch = 0
    best_val_auc = 0.5
    patience_counter = 0
    checkpoint_saved = False

    for epoch in range(1, epochs + 1):
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
        val_logits_list: List[np.ndarray] = []
        val_targets_list: List[np.ndarray] = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb = xb.to(device)
                yb = yb.to(device)
                out = model(xb)
                val_loss += float(criterion(out["logit"], yb).item())
                val_logits_list.append(out["logit"].cpu().numpy())
                val_targets_list.append(yb.cpu().numpy().astype(np.int64))
        val_loss /= max(len(val_loader), 1)
        val_logits = np.concatenate(val_logits_list, axis=0).astype(np.float64)
        val_targets = np.concatenate(val_targets_list, axis=0)
        val_probs = _sigmoid(val_logits)
        threshold_rows, selected_row, threshold_constraints_met, threshold_mode = select_validation_threshold(
            val_targets, val_probs
        )

        ckpt_ok, ckpt_reason, val_auc = checkpoint_valid(
            val_targets=val_targets,
            val_probs=val_probs,
            val_logits=val_logits,
            val_loss=val_loss,
            best_auc_so_far=best_val_auc,
        )
        state_dict = {
            "model_state_dict": model.state_dict(),
            "epoch": epoch,
            "val_auc": val_auc,
            "threshold_selected": selected_row["threshold"],
            "classes": CLASS_NAMES,
            "data_dir": dataset_info["dataset_dir"],
            "pos_weight": pos_weight,
            "lr": lr,
            "frac_threshold": frac_threshold,
            "experiment_id": experiment_id,
        }
        torch.save(state_dict, out_dir / "last_model.pt")

        if ckpt_ok:
            best_val_auc = val_auc
            best_epoch = epoch
            patience_counter = 0
            checkpoint_saved = True
            torch.save(state_dict, out_dir / "best_model.pt")
            saved_tag = "saved_best"
        else:
            patience_counter += 1
            saved_tag = ckpt_reason

        history_row = {
            "epoch": epoch,
            "train_loss": round(train_loss, 5),
            "val_loss": round(val_loss, 5),
            "val_auc": round(val_auc, 5),
            "selected_threshold": selected_row["threshold"],
            "threshold_mode": threshold_mode,
            "threshold_constraints_met": threshold_constraints_met,
            "val_macro_f1_at_selected_threshold": selected_row["macro_f1"],
            "val_stable_recall": selected_row["stable_recall"],
            "val_abnormal_recall": selected_row["abnormal_recall"],
            "val_abnormal_precision": selected_row["abnormal_precision"],
            "checkpoint_valid": ckpt_ok,
            "checkpoint_reason": ckpt_reason,
            "best_saved": ckpt_ok,
        }
        history.append(history_row)
        exp_log(
            "epoch=%03d train_loss=%.4f val_loss=%.4f val_auc=%.4f thr=%.2f val_f1=%.4f stable_rec=%.4f abnormal_rec=%.4f abnormal_prec=%.4f %s"
            % (
                epoch,
                train_loss,
                val_loss,
                val_auc,
                selected_row["threshold"],
                selected_row["macro_f1"],
                selected_row["stable_recall"],
                selected_row["abnormal_recall"],
                selected_row["abnormal_precision"],
                saved_tag,
            )
        )

        if patience_counter >= patience and checkpoint_saved and not smoke:
            exp_log(f"early_stopping epoch={epoch}")
            break
        if patience_counter >= patience * 2 and not checkpoint_saved and not smoke:
            exp_log(f"stop_without_checkpoint epoch={epoch}")
            break

    with open(out_dir / "training_history.json", "w", encoding="utf-8") as handle:
        json.dump(history, handle, indent=2)

    if checkpoint_saved and (out_dir / "best_model.pt").exists():
        checkpoint = torch.load(str(out_dir / "best_model.pt"), map_location=device, weights_only=False)
        model.load_state_dict(checkpoint["model_state_dict"])
        exp_log(f"loaded best_model epoch={int(checkpoint['epoch'])}")
    else:
        exp_log("using last_model for evaluation")

    val_metrics_full = evaluate_model(model, X_val, y_val_eval, arrays_val_eval, device, 0.50)
    threshold_rows, selected_row, threshold_constraints_met, threshold_mode = select_validation_threshold(
        y_val_eval, val_metrics_full["probs"]
    )
    selected_threshold = float(selected_row["threshold"])
    test_metrics = evaluate_model(model, X_te, y_te_eval, arrays_te_eval, device, selected_threshold)
    application_valid, decision = decide_experiment(test_metrics, threshold_constraints_met)

    elapsed = time.time() - t0
    exp_log(
        "done elapsed=%.1fs test_macro_f1=%.4f stable_rec=%.4f abnormal_rec=%.4f abnormal_prec=%.4f fp=%d fn=%d decision=%s"
        % (
            elapsed,
            test_metrics["macro_f1"],
            test_metrics["per_class"][CLASS_NAMES[0]]["recall"],
            test_metrics["per_class"][CLASS_NAMES[1]]["recall"],
            test_metrics["per_class"][CLASS_NAMES[1]]["precision"],
            test_metrics["fp"],
            test_metrics["fn"],
            decision,
        )
    )

    result = {
        "experiment_id": experiment_id,
        "dataset_dir": dataset_info["dataset_dir"],
        "frac_threshold": frac_threshold,
        "pos_weight": pos_weight,
        "lr": lr,
        "n_train_stable": n_train_stable,
        "n_train_abnormal": n_train_abnormal,
        "best_epoch": best_epoch,
        "best_val_auc": round(best_val_auc, 5) if checkpoint_saved else None,
        "checkpoint_saved": checkpoint_saved,
        "selected_threshold": selected_threshold,
        "threshold_mode": threshold_mode,
        "threshold_constraints_met": threshold_constraints_met,
        "test_macro_f1": round(test_metrics["macro_f1"], 4),
        "test_accuracy": round(test_metrics["accuracy"], 4),
        "stable_precision": test_metrics["per_class"][CLASS_NAMES[0]]["precision"],
        "stable_recall": test_metrics["per_class"][CLASS_NAMES[0]]["recall"],
        "stable_f1": test_metrics["per_class"][CLASS_NAMES[0]]["f1"],
        "abnormal_precision": test_metrics["per_class"][CLASS_NAMES[1]]["precision"],
        "abnormal_recall": test_metrics["per_class"][CLASS_NAMES[1]]["recall"],
        "abnormal_f1": test_metrics["per_class"][CLASS_NAMES[1]]["f1"],
        "roc_auc": test_metrics["roc_auc"],
        "pr_auc": test_metrics["pr_auc"],
        "TP": int(test_metrics["tp"]),
        "TN": int(test_metrics["tn"]),
        "FP": int(test_metrics["fp"]),
        "FN": int(test_metrics["fn"]),
        "n_pred_cls": int(test_metrics["n_pred_cls"]),
        "single_class_collapse": bool(test_metrics["n_pred_cls"] < 2 or test_metrics["dominant_ratio"] >= 0.98),
        "prediction_distribution": test_metrics["prediction_distribution"],
        "application_valid": application_valid,
        "decision": decision,
        "elapsed_s": round(elapsed, 1),
    }

    metrics_payload = {
        **result,
        "per_class_metrics": test_metrics["per_class"],
        "subject_breakdown": test_metrics["subject_breakdown"],
        "threshold_sweep": threshold_rows,
        "confusion_matrix": [[test_metrics["tn"], test_metrics["fp"]], [test_metrics["fn"], test_metrics["tp"]]],
        "validation_selection": {
            "selected_row": selected_row,
            "threshold_constraints_met": threshold_constraints_met,
            "threshold_mode": threshold_mode,
        },
        "training_config": {
            "epochs_planned": epochs,
            "batch_size": BATCH_SIZE,
            "loss": "BCEWithLogitsLoss",
            "optimizer": "AdamW(weight_decay=1e-4)",
            "scheduler": f"CosineAnnealingLR(T_max={epochs}, eta_min=1e-5)",
        },
    }

    with open(out_dir / "metrics.json", "w", encoding="utf-8") as handle:
        json.dump(_to_builtin(metrics_payload), handle, indent=2)
    with open(out_dir / "threshold_sweep.json", "w", encoding="utf-8") as handle:
        json.dump(_to_builtin(threshold_rows), handle, indent=2)
    with open(out_dir / "confusion_matrix.json", "w", encoding="utf-8") as handle:
        json.dump({
            "labels": CLASS_NAMES,
            "threshold": selected_threshold,
            "matrix": [[test_metrics["tn"], test_metrics["fp"]], [test_metrics["fn"], test_metrics["tp"]]],
        }, handle, indent=2)
    with open(out_dir / "per_class_metrics.json", "w", encoding="utf-8") as handle:
        json.dump(_to_builtin(test_metrics["per_class"]), handle, indent=2)
    with open(out_dir / "prediction_distribution.json", "w", encoding="utf-8") as handle:
        json.dump({
            "predicted": test_metrics["prediction_distribution"],
            "true": {label: int(test_metrics["per_class"][label]["support"]) for label in CLASS_NAMES},
        }, handle, indent=2)
    with open(out_dir / "subject_breakdown.json", "w", encoding="utf-8") as handle:
        json.dump(_to_builtin(test_metrics["subject_breakdown"]), handle, indent=2)
    with open(out_dir / "imu_norm_stats.json", "w", encoding="utf-8") as handle:
        json.dump(norm_stats, handle, indent=2)
    with open(out_dir / "console.log", "w", encoding="utf-8") as handle:
        handle.write("\n".join(console_lines) + "\n")

    return result


def best_candidate(results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    valid_results = [result for result in results if not result.get("skipped")]
    if not valid_results:
        return None
    return sorted(
        valid_results,
        key=lambda result: (
            1 if result["decision"] == "STRONG_ACCEPT_GAIT_V2_2_EXPERT" else 0,
            1 if result["decision"] == "ACCEPT_GAIT_V2_2_EXPERT" else 0,
            result.get("abnormal_precision", 0.0),
            result.get("abnormal_recall", 0.0),
            result.get("test_macro_f1", 0.0),
            -result.get("FP", 10**9),
            result.get("stable_recall", 0.0),
        ),
        reverse=True,
    )[0]


def final_decision(results: List[Dict[str, Any]]) -> str:
    if any(result.get("decision") == "STRONG_ACCEPT_GAIT_V2_2_EXPERT" for result in results):
        return "STRONG_ACCEPT_GAIT_V2_2_EXPERT"
    if any(result.get("decision") == "ACCEPT_GAIT_V2_2_EXPERT" for result in results):
        return "ACCEPT_GAIT_V2_2_EXPERT"
    if BASELINE_V21["application_valid"]:
        return "KEEP_GAIT_V2_1_BASELINE"
    return "REJECT_GAIT_ML_KEEP_RULE_BASED"


def build_report(
    dataset_variants: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    best_result: Optional[Dict[str, Any]],
    overall_decision: str,
) -> str:
    lines = [
        "# Gait v2.2 Precision/Recall Report",
        "",
        "## 1. Executive Summary",
        "",
        f"- Overall decision: **{overall_decision}**",
        f"- RiskFusion integration now: **NO**",
        "- User approval required before any future integration: **YES**",
    ]
    if best_result:
        lines.extend(
            [
                f"- Best v2.2 experiment: **{best_result['experiment_id']}**",
                f"- Selected threshold: **{best_result['selected_threshold']:.2f}**",
                f"- test_macro_f1: **{best_result['test_macro_f1']:.4f}**",
                f"- stable_recall: **{best_result['stable_recall']:.4f}**",
                f"- abnormal_recall: **{best_result['abnormal_recall']:.4f}**",
                f"- abnormal_precision: **{best_result['abnormal_precision']:.4f}**",
                f"- application_valid: **{best_result['application_valid']}**",
            ]
        )
    else:
        lines.append("- No completed v2.2 experiment produced usable metrics.")

    lines.extend(
        [
            "",
            "## 2. Baseline v2.1 Metrics",
            "",
            f"- experiment_id: {BASELINE_V21['experiment_id']}",
            f"- frac_threshold: {BASELINE_V21['frac_threshold']}",
            f"- pos_weight: {BASELINE_V21['pos_weight']}",
            f"- lr: {BASELINE_V21['lr']}",
            f"- selected_threshold: {BASELINE_V21['selected_threshold']}",
            f"- test_macro_f1: {BASELINE_V21['test_macro_f1']}",
            f"- stable_recall: {BASELINE_V21['stable_recall']}",
            f"- abnormal_recall: {BASELINE_V21['abnormal_recall']}",
            f"- abnormal_precision: {BASELINE_V21['abnormal_precision']}",
            f"- TP/TN/FP/FN: {BASELINE_V21['TP']} / {BASELINE_V21['TN']} / {BASELINE_V21['FP']} / {BASELINE_V21['FN']}",
            f"- application_valid: {BASELINE_V21['application_valid']}",
            f"- decision: {BASELINE_V21['decision']}",
            "",
            "## 3. v2.2 Goal",
            "",
            "- Improve abnormal/freezing precision while keeping abnormal_recall >= 0.70.",
            "- Keep stable_recall >= 0.88 and beat baseline test_macro_f1=0.7631.",
            "- Reduce or at least not materially worsen FP relative to baseline FP=138.",
            "",
            "## 4. Dataset Variants",
            "",
            "| frac_threshold | dataset_dir | report_dir | built |",
            "|---|---|---|---|",
        ]
    )
    for variant in dataset_variants:
        lines.append(
            f"| {variant['frac_threshold']:.2f} | {variant['dataset_dir']} | {variant['report_dir']} | YES |"
        )

    lines.extend(
        [
            "",
            "## 5. Support Recount by Fraction Threshold",
            "",
            "| frac_threshold | train_stable | train_abnormal | val_stable | val_abnormal | test_stable | test_abnormal | train_abnormal_pct | val_abnormal_pct | test_abnormal_pct | unknown_excluded_train | unknown_excluded_val | unknown_excluded_test |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for variant in dataset_variants:
        splits = variant["support"]["splits"]
        lines.append(
            f"| {variant['frac_threshold']:.2f} | {splits['train']['stable_movement_count']} | {splits['train']['abnormal_or_freezing_movement_count']} | {splits['val']['stable_movement_count']} | {splits['val']['abnormal_or_freezing_movement_count']} | {splits['test']['stable_movement_count']} | {splits['test']['abnormal_or_freezing_movement_count']} | {splits['train']['abnormal_percentage']:.4f}% | {splits['val']['abnormal_percentage']:.4f}% | {splits['test']['abnormal_percentage']:.4f}% | {splits['train']['unknown_excluded_count']} | {splits['val']['unknown_excluded_count']} | {splits['test']['unknown_excluded_count']} |"
        )

    lines.extend(
        [
            "",
            "## 6. Ablation Grid",
            "",
            "- frac_threshold: 0.30, 0.35, 0.40, 0.45",
            "- pos_weight: 1.0, 1.25, 1.5, 1.75, 2.0",
            "- lr: 3e-4, 1e-4",
            "- checkpoint metric: validation ROC-AUC",
            "",
            "## 7. Threshold Selection Policy",
            "",
            "- Primary validation constraint: stable_recall >= 0.88, abnormal_recall >= 0.70, abnormal_precision >= 0.65.",
            "- Among valid thresholds: maximize macro_f1, then abnormal_precision, then minimize FP, while keeping abnormal_recall >= 0.70.",
            "- If no threshold satisfies precision>=0.65 and recall>=0.70 together, a secondary threshold is recorded but application_valid stays false.",
            "",
            "## 8. Results Table",
            "",
            "| experiment_id | frac_threshold | pos_weight | lr | best_epoch | best_val_auc | selected_threshold | test_macro_f1 | stable_recall | abnormal_recall | abnormal_precision | stable_precision | FP | FN | TP | TN | application_valid | decision |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    sorted_results = sorted(
        [result for result in results if not result.get("skipped")],
        key=lambda result: (
            1 if result["decision"] == "STRONG_ACCEPT_GAIT_V2_2_EXPERT" else 0,
            1 if result["decision"] == "ACCEPT_GAIT_V2_2_EXPERT" else 0,
            result.get("abnormal_precision", 0.0),
            result.get("abnormal_recall", 0.0),
            result.get("test_macro_f1", 0.0),
            -result.get("FP", 10**9),
        ),
        reverse=True,
    )
    for result in sorted_results:
        lines.append(
            f"| {result['experiment_id']} | {result['frac_threshold']:.2f} | {result['pos_weight']:.2f} | {result['lr']:.0e} | {result['best_epoch']} | {result.get('best_val_auc', 'N/A')} | {result['selected_threshold']:.2f} | {result['test_macro_f1']:.4f} | {result['stable_recall']:.4f} | {result['abnormal_recall']:.4f} | {result['abnormal_precision']:.4f} | {result['stable_precision']:.4f} | {result['FP']} | {result['FN']} | {result['TP']} | {result['TN']} | {'true' if result['application_valid'] else 'false'} | {result['decision']} |"
        )
    for result in results:
        if result.get("skipped"):
            lines.append(
                f"| {result['experiment_id']} | {result['frac_threshold']:.2f} | {result['pos_weight']:.2f} | {result['lr']:.0e} | - | - | - | - | - | - | - | - | - | - | - | - | false | {result['skip_reason']} |"
            )

    lines.extend(["", "## 9. Best Experiment", ""])
    if best_result:
        lines.extend(
            [
                f"- experiment_id: **{best_result['experiment_id']}**",
                f"- frac_threshold: {best_result['frac_threshold']:.2f}",
                f"- pos_weight: {best_result['pos_weight']:.2f}",
                f"- lr: {best_result['lr']:.0e}",
                f"- selected_threshold: {best_result['selected_threshold']:.2f}",
                f"- best_epoch: {best_result['best_epoch']}",
                f"- best_val_auc: {best_result.get('best_val_auc', 'N/A')}",
                f"- application_valid: {best_result['application_valid']}",
                f"- decision: {best_result['decision']}",
            ]
        )
    else:
        lines.append("- No best experiment available.")

    lines.extend(["", "## 10. Test Metrics", ""])
    if best_result:
        lines.extend(
            [
                f"- test_macro_f1: {best_result['test_macro_f1']:.4f}",
                f"- test_accuracy: {best_result['test_accuracy']:.4f}",
                f"- stable_precision: {best_result['stable_precision']:.4f}",
                f"- stable_recall: {best_result['stable_recall']:.4f}",
                f"- stable_f1: {best_result['stable_f1']:.4f}",
                f"- abnormal_precision: {best_result['abnormal_precision']:.4f}",
                f"- abnormal_recall: {best_result['abnormal_recall']:.4f}",
                f"- abnormal_f1: {best_result['abnormal_f1']:.4f}",
                f"- ROC-AUC: {best_result['roc_auc']}",
                f"- PR-AUC: {best_result['pr_auc']}",
            ]
        )

    lines.extend(["", "## 11. Confusion Matrix", ""])
    if best_result:
        lines.extend(
            [
                "| Actual / Pred | stable_gait | abnormal_or_freezing_movement |",
                "|---|---:|---:|",
                f"| stable_gait | {best_result['TN']} | {best_result['FP']} |",
                f"| abnormal_or_freezing_movement | {best_result['FN']} | {best_result['TP']} |",
            ]
        )

    lines.extend(["", "## 12. Precision/Recall Tradeoff", ""])
    if best_result:
        lines.extend(
            [
                f"- Baseline abnormal_precision -> v2.2 best: {BASELINE_V21['abnormal_precision']:.4f} -> {best_result['abnormal_precision']:.4f}",
                f"- Baseline abnormal_recall -> v2.2 best: {BASELINE_V21['abnormal_recall']:.4f} -> {best_result['abnormal_recall']:.4f}",
                f"- Baseline FP -> v2.2 best: {BASELINE_V21['FP']} -> {best_result['FP']}",
                f"- Baseline macro_f1 -> v2.2 best: {BASELINE_V21['test_macro_f1']:.4f} -> {best_result['test_macro_f1']:.4f}",
            ]
        )

    lines.extend(["", "## 13. Subject-Level Evaluation", ""])
    if best_result:
        metrics_path = OUTPUT_ROOT / best_result["experiment_id"] / "subject_breakdown.json"
        if metrics_path.exists():
            with open(metrics_path, "r", encoding="utf-8") as handle:
                subject_breakdown = json.load(handle)
            lines.extend(
                [
                    "| Subject | Samples | Stable support | Abnormal support | Stable precision | Stable recall | Abnormal precision | Abnormal recall | Macro F1 | TP | TN | FP | FN |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for subject, info in sorted(subject_breakdown.items()):
                lines.append(
                    f"| {subject} | {info['n']} | {info['stable_support']} | {info['abnormal_support']} | {info['stable_precision']:.4f} | {info['stable_recall']:.4f} | {info['abnormal_precision']:.4f} | {info['abnormal_recall']:.4f} | {info['macro_f1']:.4f} | {info['tp']} | {info['tn']} | {info['fp']} | {info['fn']} |"
                )

    lines.extend(["", "## 14. Application Validity", ""])
    if best_result:
        lines.extend(
            [
                f"- threshold constraints met on validation: {best_result['threshold_constraints_met']}",
                f"- n_pred_cls: {best_result['n_pred_cls']}",
                f"- single_class_collapse: {best_result['single_class_collapse']}",
                f"- application_valid: {best_result['application_valid']}",
            ]
        )

    lines.extend(
        [
            "",
            "## 15. Final Decision",
            "",
            f"**{overall_decision}**",
            "",
            "## 16. RiskFusion Recommendation",
            "",
            "- Automatic integration: NO",
            "- User approval required before any future integration: YES",
            "- Integration mode if later approved: low-weight auxiliary only",
            "",
            "## 17. Files Changed",
            "",
            "- scripts/build_gait_instability_v2_dataset.py",
            "- scripts/run_gait_v2_2_precision_ablation.py",
            f"- {REPORT_PATH}",
            "",
            "## 18. Next Step",
            "",
        ]
    )
    if overall_decision in {"STRONG_ACCEPT_GAIT_V2_2_EXPERT", "ACCEPT_GAIT_V2_2_EXPERT"}:
        lines.extend(
            [
                "- Present v2.2 result to the user and wait for explicit integration approval.",
                "- Activity v2 can proceed independently if integration approval is deferred.",
            ]
        )
    else:
        lines.extend(
            [
                "- Keep v2.1 baseline as the accepted auxiliary gait model.",
                "- Continue with Activity v2 work; do not auto-integrate new gait model.",
            ]
        )
    return "\n".join(lines)


def write_master_outputs(dataset_variants: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str]:
    with open(ALL_RESULTS_PATH, "w", encoding="utf-8") as handle:
        json.dump(_to_builtin(results), handle, indent=2)

    best_result = best_candidate(results)
    overall = final_decision(results)
    report_text = build_report(dataset_variants, results, best_result, overall)
    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        handle.write(report_text)
    return best_result, overall


def main() -> None:
    args = parse_args()
    _ensure_expected_python()
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    log_environment()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info("device: %s", device)

    requested_thresholds = args.dataset_thresholds or DATASET_THRESHOLDS
    requested_pos_weights = args.pos_weights or POS_WEIGHTS
    requested_lrs = args.lrs or LRS

    dataset_variants: List[Dict[str, Any]] = []
    for frac_threshold in requested_thresholds:
        dataset_dir = dataset_dir_for_threshold(frac_threshold)
        report_dir = report_dir_for_threshold(frac_threshold)
        support_path = report_dir / "gait_v2_support_recount.json"
        if args.skip_dataset_build and dataset_dir.exists() and support_path.exists():
            with open(support_path, "r", encoding="utf-8") as handle:
                support = json.load(handle)
            variant = {
                "frac_threshold": frac_threshold,
                "dataset_dir": str(dataset_dir),
                "report_dir": str(report_dir),
                "support": support,
            }
        else:
            variant = build_dataset_variant(frac_threshold)

        splits = variant["support"]["splits"]
        if (
            splits["val"]["abnormal_or_freezing_movement_count"] == 0
            or splits["test"]["abnormal_or_freezing_movement_count"] == 0
        ):
            log.warning("Skipping dataset ft=%.2f due to zero abnormal support in val or test", frac_threshold)
            continue
        variant["bundle"] = load_dataset_bundle(Path(variant["dataset_dir"]))
        dataset_variants.append(variant)

    if not dataset_variants:
        raise RuntimeError("No valid dataset variants available for v2.2 training")

    epochs = 3 if args.smoke else args.epochs
    patience = 2 if args.smoke else args.patience
    existing_results: List[Dict[str, Any]] = []
    completed_ids: set[str] = set()
    if args.resume_existing and ALL_RESULTS_PATH.exists():
        with open(ALL_RESULTS_PATH, "r", encoding="utf-8") as handle:
            existing_results = json.load(handle)
        completed_ids = {str(result.get("experiment_id")) for result in existing_results}

    experiment_plan = [
        (variant, pos_weight, lr)
        for variant in dataset_variants
        for pos_weight in requested_pos_weights
        for lr in requested_lrs
        if _experiment_id(float(variant["frac_threshold"]), float(pos_weight), float(lr)) not in completed_ids
    ]
    if args.max_experiments is not None:
        experiment_plan = experiment_plan[: args.max_experiments]

    results: List[Dict[str, Any]] = list(existing_results)
    for variant, pos_weight, lr in experiment_plan:
        result = run_experiment(
            dataset_info=variant,
            pos_weight=pos_weight,
            lr=lr,
            epochs=epochs,
            patience=patience,
            device=device,
            smoke=args.smoke,
        )
        results.append(result)
        write_master_outputs(dataset_variants, results)

    best_result, overall = write_master_outputs(dataset_variants, results)

    print("\n" + "=" * 72)
    print("GAIT v2.2 PRECISION/RECALL SUMMARY")
    print("=" * 72)
    print(f"report_path={REPORT_PATH}")
    if best_result:
        print(f"best_experiment_id={best_result['experiment_id']}")
        print(f"frac_threshold={best_result['frac_threshold']:.2f}")
        print(f"pos_weight={best_result['pos_weight']:.2f}")
        print(f"lr={best_result['lr']:.0e}")
        print(f"selected_threshold={best_result['selected_threshold']:.2f}")
        print(f"test_macro_f1={best_result['test_macro_f1']:.4f}")
        print(f"stable_recall={best_result['stable_recall']:.4f}")
        print(f"abnormal_recall={best_result['abnormal_recall']:.4f}")
        print(f"abnormal_precision={best_result['abnormal_precision']:.4f}")
        print(f"confusion_matrix=TP:{best_result['TP']} TN:{best_result['TN']} FP:{best_result['FP']} FN:{best_result['FN']}")
    else:
        print("best_experiment_id=NONE")
    print(f"final_decision={overall}")
    print("riskfusion_connect_now=NO")
    print("user_approval_required=YES")
    print(
        f"better_model={'v2.2' if overall in {'STRONG_ACCEPT_GAIT_V2_2_EXPERT', 'ACCEPT_GAIT_V2_2_EXPERT'} else 'v2.1'}"
    )
    print(
        f"next_step={'Gait integration review' if overall in {'STRONG_ACCEPT_GAIT_V2_2_EXPERT', 'ACCEPT_GAIT_V2_2_EXPERT'} else 'Activity v2'}"
    )
    print("=" * 72)


if __name__ == "__main__":
    main()
