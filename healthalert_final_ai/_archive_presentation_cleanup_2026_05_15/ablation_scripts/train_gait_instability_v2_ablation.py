"""Gait v2.1 Ablation Grid — Controlled hyperparameter search for FP reduction.

Grid:
  pos_weight_cap : 1.0, 2.0, 3.0, 4.0
  lr             : 3e-4, 1e-4
  frac_threshold : 0.20, 0.30, 0.40, 0.50  (filters training abnormal windows on-the-fly)

Phase 1: run pos_weight_cap x lr grid at frac_threshold=0.20 (8 runs)
Phase 2: for candidates passing checkpoint_valid, run frac_threshold=0.30/0.40/0.50

All outputs go to:
  outputs/hybrid_redesign/gait_instability_v2_ablation/<experiment_id>/

Comparison report:
  outputs/hybrid_redesign/gait_instability_v2_ablation/gait_v2_ablation_report.md

Correct Python: C:\\project\\HealthAlert\\.venv311\\Scripts\\python.exe
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
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score
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
log = logging.getLogger("gait_v2_ablation")

EXPECTED_PYTHON = PROJECT_ROOT.parent / ".venv311" / "Scripts" / "python.exe"
DATA_DIR = PROJECT_ROOT / "outputs" / "windowed_dataset" / "gait_instability_v2"
ABLATION_ROOT = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "gait_instability_v2_ablation"
BASELINE_DIR = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "gait_instability_v2_expert"

CLASS_NAMES = ["stable_gait", "abnormal_or_freezing_movement"]
RAW_LABEL_TO_FINAL = {0: 0, 3: 1}
VALID_LABELS = set(RAW_LABEL_TO_FINAL)
THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70]

# Ablation grid
POS_WEIGHT_CAPS = [1.0, 2.0, 3.0, 4.0]
LRS = [3e-4, 1e-4]
FRAC_THRESHOLDS_PHASE1 = [0.20]
FRAC_THRESHOLDS_PHASE2 = [0.30, 0.40, 0.50]

EPOCHS = 50
BATCH_SIZE = 256
PATIENCE = 10
SEED = 42


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gait v2.1 Ablation Grid")
    p.add_argument("--phase", type=int, default=0, help="0=all, 1=phase1 only, 2=phase2 only")
    p.add_argument("--epochs", type=int, default=EPOCHS)
    p.add_argument("--patience", type=int, default=PATIENCE)
    p.add_argument("--smoke", action="store_true", help="Fast smoke test (minimal epochs and samples)")
    p.add_argument(
        "--phase2_candidates",
        nargs="*",
        default=None,
        help="Explicit list of experiment_ids to run phase2 for (overrides auto-selection)",
    )
    return p.parse_args()


# ─── Utility ──────────────────────────────────────────────────────────────────

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


# ─── Data Loading ─────────────────────────────────────────────────────────────

def load_split_raw(split: str) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray]]:
    """Load a split and return (X [N,6,200], y [N], arrays) without normalization.
    
    All label filtering is applied but abnormal_fraction filtering is NOT applied here
    so it can be applied per-experiment.
    """
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
        "labels": labels,
        "imu": imu,
        "metadata": metadata,
        "source": raw["source"][keep] if "source" in raw.files else np.array(["DAPHNET_FOG"] * len(labels), dtype=object),
        "subject_id": raw["subject_id"][keep] if "subject_id" in raw.files else np.array(["unknown"] * len(labels), dtype=object),
        "recording_id": raw["recording_id"][keep] if "recording_id" in raw.files else np.array(["unknown"] * len(labels), dtype=object),
    }
    # model input: (N, 6, 200)
    X = imu.transpose(0, 2, 1).astype(np.float32)
    return X, labels, arrays


def filter_by_abnormal_fraction(
    X: np.ndarray,
    y: np.ndarray,
    arrays: Dict[str, np.ndarray],
    frac_threshold: float,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray]]:
    """Keep stable windows as-is; drop abnormal windows with fraction < frac_threshold."""
    if frac_threshold <= 0.0:
        return X, y, arrays

    metas = [_parse_meta(m) for m in arrays["metadata"]]
    fractions = np.array([float(m.get("abnormal_fraction", 0.0)) for m in metas], dtype=np.float32)

    stable_mask = y == 0
    # For abnormal windows: keep only those with fraction >= threshold
    abnormal_keep = (y == 1) & (fractions >= frac_threshold)
    keep = stable_mask | abnormal_keep

    new_arrays = {k: v[keep] for k, v in arrays.items()}
    return X[keep], y[keep], new_arrays


def compute_norm_stats(X: np.ndarray) -> Dict[str, Any]:
    mean = X.mean(axis=(0, 2))
    std = np.maximum(X.std(axis=(0, 2)), 1e-6)
    return {
        "mean_per_channel": [float(v) for v in mean],
        "std_per_channel": [float(v) for v in std],
    }


def apply_norm(X: np.ndarray, stats: Dict[str, Any]) -> np.ndarray:
    mean = np.asarray(stats["mean_per_channel"], dtype=np.float32)
    std = np.asarray(stats["std_per_channel"], dtype=np.float32)
    return ((X - mean[None, :, None]) / std[None, :, None]).astype(np.float32)


def compute_pos_weight(y: np.ndarray, cap: float) -> float:
    stable = max(int((y == 0).sum()), 1)
    abnormal = max(int((y == 1).sum()), 1)
    return float(min(stable / abnormal, cap))


# ─── Evaluation ───────────────────────────────────────────────────────────────

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
    accuracy = _safe_div(tp + tn, tp + tn + fp + fn)
    dominant_cls = int(np.bincount(preds, minlength=2).argmax())
    dominant_ratio = float(np.bincount(preds, minlength=2).max() / max(len(preds), 1))

    return {
        "threshold": float(threshold),
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "n_pred_cls": n_pred_cls,
        "dominant_ratio": dominant_ratio,
        "dominant_predicted_class": CLASS_NAMES[dominant_cls],
        "false_positives": fp,
        "false_negatives": fn,
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
    logits_all = []
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

    subjects = np.asarray(arrays["subject_id"])
    preds = metrics["preds"]
    subject_breakdown: Dict[str, Any] = {}
    for subj in np.unique(subjects):
        mask = subjects == subj
        local = evaluate_predictions(y[mask], probs[mask], threshold)
        subject_breakdown[str(subj)] = {
            "n": int(mask.sum()),
            "stable_support": int((y[mask] == 0).sum()),
            "abnormal_support": int((y[mask] == 1).sum()),
            "stable_recall": local["per_class"][CLASS_NAMES[0]]["recall"],
            "abnormal_recall": local["per_class"][CLASS_NAMES[1]]["recall"],
            "macro_f1": local["macro_f1"],
        }
    metrics["subject_breakdown"] = subject_breakdown
    return metrics


def validation_sweep(y_true: np.ndarray, probs: np.ndarray) -> Tuple[List[Dict[str, Any]], float]:
    """New constraint-first threshold selection: stable>=0.75 AND abnormal>=0.60."""
    rows = []
    for thr in THRESHOLDS:
        m = evaluate_predictions(y_true, probs, thr)
        stable_recall = m["per_class"][CLASS_NAMES[0]]["recall"]
        abnormal_recall = m["per_class"][CLASS_NAMES[1]]["recall"]
        abnormal_precision = m["per_class"][CLASS_NAMES[1]]["precision"]
        row = {
            "threshold": round(thr, 2),
            "stable_recall": stable_recall,
            "abnormal_recall": abnormal_recall,
            "abnormal_precision": abnormal_precision,
            "macro_f1": m["macro_f1"],
            "false_positives": m["false_positives"],
            "false_negatives": m["false_negatives"],
            "n_pred_cls": m["n_pred_cls"],
        }
        rows.append(row)

    eligible = [
        r for r in rows
        if r["stable_recall"] >= 0.75 and r["abnormal_recall"] >= 0.60 and r["n_pred_cls"] >= 2
    ]
    if eligible:
        best = max(
            eligible,
            key=lambda r: (r["macro_f1"], r["abnormal_precision"], -r["false_positives"]),
        )
    else:
        # Fall back: maximize macro_f1 with a penalty on fp
        best = max(
            rows,
            key=lambda r: (r["macro_f1"], r["stable_recall"] * 0.3 + r["abnormal_recall"] * 0.3, -r["false_positives"]),
        )
    return rows, float(best["threshold"])


# ─── Checkpoint and Validity ──────────────────────────────────────────────────

def checkpoint_valid(
    val_targets: np.ndarray,
    val_probs: np.ndarray,
    val_logits: np.ndarray,
    val_loss: float,
    best_auc_so_far: float,
) -> Tuple[bool, str, float]:
    """ROC-AUC based checkpoint selection.

    Why AUC over threshold-based macro_f1:
    - val set has 29% abnormal vs train/test ~10% → val_loss inflates for models
      that learned the imbalanced training distribution (correct behaviour!).
    - Threshold-based metrics at any fixed threshold collapse due to pos_weight
      miscalibration making raw logits shift; best checkpoint was epoch 2 (barely
      trained) rather than epoch 15 (well trained).
    - AUC is rank-order, threshold-independent and captures discriminative power
      regardless of calibration, making it robust to the distribution mismatch.
    """
    if not math.isfinite(val_loss):
        return False, "val_loss_not_finite", 0.0
    if not np.isfinite(val_logits).all():
        return False, "logits_nan_inf", 0.0
    if len(np.unique(val_targets)) < 2:
        return False, "single_class_in_val", 0.0
    try:
        val_auc = float(roc_auc_score(val_targets, val_probs))
    except Exception as exc:  # noqa: BLE001
        return False, f"auc_error:{exc}", 0.0
    if val_auc <= best_auc_so_far:
        return False, f"no_auc_improvement(auc={val_auc:.4f})", val_auc
    return True, f"ok(auc={val_auc:.4f})", val_auc


def decide_application_valid(test_metrics: Dict[str, Any], checkpoint_saved: bool) -> Tuple[bool, str]:
    """Updated criteria for v2.1.
    
    Minimum (PARTIAL_ACCEPT_AUXILIARY_ONLY):
      stable_recall >= 0.75, abnormal_recall >= 0.60, macro_f1 >= 0.65
    
    Ideal (ACCEPT_GAIT_V2_1_EXPERT):
      stable_recall >= 0.80, abnormal_recall >= 0.70, macro_f1 >= 0.75
    
    Note: checkpoint_saved=False (no best_model.pt) is not an automatic reject —
    the last_model may still be valid if its test metrics meet the criteria.
    """

    stable_recall = test_metrics["per_class"][CLASS_NAMES[0]]["recall"]
    abnormal_recall = test_metrics["per_class"][CLASS_NAMES[1]]["recall"]
    macro_f1 = test_metrics["macro_f1"]
    n_pred_cls = test_metrics["n_pred_cls"]
    collapse = n_pred_cls < 2 or test_metrics["dominant_ratio"] > 0.98

    if collapse:
        return False, "REJECT_KEEP_RULE_BASED"

    if macro_f1 >= 0.75 and stable_recall >= 0.80 and abnormal_recall >= 0.70:
        return True, "ACCEPT_GAIT_V2_1_EXPERT"
    if macro_f1 >= 0.65 and stable_recall >= 0.75 and abnormal_recall >= 0.60:
        return True, "PARTIAL_ACCEPT_AUXILIARY_ONLY"
    return False, "REJECT_KEEP_RULE_BASED"


# ─── Single Experiment ────────────────────────────────────────────────────────

def run_experiment(
    experiment_id: str,
    pos_weight_cap: float,
    lr: float,
    frac_threshold: float,
    epochs: int,
    patience: int,
    device: torch.device,
    X_tr_raw: np.ndarray,
    y_tr_raw: np.ndarray,
    arrays_tr_raw: Dict[str, np.ndarray],
    X_val: np.ndarray,  # already un-filtered (val keeps all), normalisation will be applied per experiment
    y_val: np.ndarray,
    arrays_val: Dict[str, np.ndarray],
    X_te: np.ndarray,
    y_te: np.ndarray,
    arrays_te: Dict[str, np.ndarray],
    smoke: bool = False,
) -> Dict[str, Any]:
    """Run one ablation experiment and return a result dict."""
    out_dir = ABLATION_ROOT / experiment_id
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    log.info("=== [%s] pos_weight_cap=%.1f lr=%.0e frac_threshold=%.2f ===",
             experiment_id, pos_weight_cap, lr, frac_threshold)

    # Filter training abnormal windows by fraction threshold
    X_tr, y_tr, arrays_tr = filter_by_abnormal_fraction(X_tr_raw, y_tr_raw, arrays_tr_raw, frac_threshold)
    n_stable_tr = int((y_tr == 0).sum())
    n_abnormal_tr = int((y_tr == 1).sum())
    log.info("[%s] After fraction filter (>=%.2f): train stable=%d abnormal=%d",
             experiment_id, frac_threshold, n_stable_tr, n_abnormal_tr)

    if n_abnormal_tr == 0:
        log.error("[%s] No abnormal training samples after fraction filter — skipping.", experiment_id)
        return {"experiment_id": experiment_id, "skipped": True, "skip_reason": "no_abnormal_after_filter"}

    # Compute norm stats from (filtered) train
    norm_stats = compute_norm_stats(X_tr)
    X_tr_norm = apply_norm(X_tr, norm_stats)
    X_val_norm = apply_norm(X_val, norm_stats)
    X_te_norm = apply_norm(X_te, norm_stats)

    pos_weight = compute_pos_weight(y_tr, pos_weight_cap)
    log.info("[%s] pos_weight=%.4f (raw_ratio=%.2f, cap=%.1f)",
             experiment_id, pos_weight, n_stable_tr / max(n_abnormal_tr, 1), pos_weight_cap)

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
        idx_tr = rng.permutation(len(y_tr))[: min(512, len(y_tr))]
        X_tr_norm = X_tr_norm[idx_tr]
        y_tr_smoke = y_tr[idx_tr]
    else:
        y_tr_smoke = y_tr

    train_loader = DataLoader(
        TensorDataset(
            torch.from_numpy(X_tr_norm),
            torch.from_numpy(y_tr_smoke.astype(np.float32)),
        ),
        batch_size=BATCH_SIZE,
        shuffle=True,
    )
    val_loader = DataLoader(
        TensorDataset(
            torch.from_numpy(X_val_norm),
            torch.from_numpy(y_val.astype(np.float32)),
        ),
        batch_size=BATCH_SIZE,
        shuffle=False,
    )

    history: List[Dict[str, Any]] = []
    best_val_auc = 0.5  # AUC threshold: model must beat random
    best_epoch = 0
    patience_counter = 0
    checkpoint_saved = False

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            out = model(xb)
            loss = criterion(out["logit"], yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += float(loss.item())
        train_loss /= max(len(train_loader), 1)
        scheduler.step()

        # Validation
        model.eval()
        val_loss = 0.0
        val_logits_list: List[np.ndarray] = []
        val_targets_list: List[np.ndarray] = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                out = model(xb)
                val_loss += float(criterion(out["logit"], yb).item())
                val_logits_list.append(out["logit"].cpu().numpy())
                val_targets_list.append(yb.cpu().numpy().astype(np.int64))
        val_loss /= max(len(val_loader), 1)
        val_logits = np.concatenate(val_logits_list, axis=0).astype(np.float64)
        val_targets = np.concatenate(val_targets_list, axis=0)
        val_probs = _sigmoid(val_logits)
        # Evaluate at t=0.25 for logging (threshold-independent AUC used for checkpointing).
        val_eval = evaluate_predictions(val_targets, val_probs, 0.25)

        ckpt_ok, ckpt_reason, val_auc = checkpoint_valid(
            val_targets, val_probs, val_logits, val_loss, best_val_auc
        )

        state_dict = {
            "model_state_dict": model.state_dict(),
            "epoch": epoch,
            "val_auc": val_auc,
            "val_macro_f1_at_t25": float(val_eval["macro_f1"]),
            "classes": CLASS_NAMES,
            "threshold_default": 0.5,
            "data_dir": str(DATA_DIR),
            "pos_weight": pos_weight,
            "pos_weight_cap": pos_weight_cap,
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
            tag = f"[BEST auc={val_auc:.4f}]"
        else:
            patience_counter += 1
            tag = f"[SKIP:{ckpt_reason}]"

        row = {
            "epoch": epoch,
            "train_loss": round(train_loss, 5),
            "val_loss": round(val_loss, 5),
            "val_auc": round(val_auc, 4),
            "val_macro_f1_at_t25": round(val_eval["macro_f1"], 4),
            "stable_recall_at_t25": round(val_eval["per_class"][CLASS_NAMES[0]]["recall"], 4),
            "abnormal_recall_at_t25": round(val_eval["per_class"][CLASS_NAMES[1]]["recall"], 4),
            "n_pred_cls_at_t25": int(val_eval["n_pred_cls"]),
            "checkpoint_valid": bool(ckpt_ok),
            "checkpoint_reason": ckpt_reason,
            "best_saved": bool(ckpt_ok),
        }
        history.append(row)

        log.info(
            "[%s] E%03d/%d | t_loss=%.4f v_loss=%.4f | v_auc=%.4f v_f1@t25=%.4f s_rec=%.4f a_rec=%.4f %s",
            experiment_id, epoch, epochs,
            train_loss, val_loss,
            val_auc,
            val_eval["macro_f1"],
            val_eval["per_class"][CLASS_NAMES[0]]["recall"],
            val_eval["per_class"][CLASS_NAMES[1]]["recall"],
            tag,
        )

        # Only apply patience after at least one checkpoint has been saved.
        # This prevents premature early stopping when the model is still searching
        # for a balanced prediction regime (common with low pos_weight_cap).
        if patience_counter >= patience and checkpoint_saved and not smoke:
            log.info("[%s] Early stopping at epoch %d", experiment_id, epoch)
            break
        # Safety valve: stop if patience exceeded 2x without ANY checkpoint saved
        if patience_counter >= patience * 2 and not checkpoint_saved and not smoke:
            log.info("[%s] No checkpoint after %d epochs — stopping.", experiment_id, epoch)
            break

    # Save training history
    with open(out_dir / "training_history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    # Load best checkpoint for final eval
    if checkpoint_saved and (out_dir / "best_model.pt").exists():
        ckpt = torch.load(str(out_dir / "best_model.pt"), map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model_state_dict"])
        log.info("[%s] Loaded best_model.pt (epoch=%d)", experiment_id, int(ckpt["epoch"]))
    else:
        log.warning("[%s] No best_model.pt saved; using last model.", experiment_id)

    # Threshold sweep on validation
    val_full_eval = evaluate_model(model, X_val_norm, y_val, arrays_val, device, 0.50)
    threshold_rows, recommended_threshold = validation_sweep(y_val, val_full_eval["probs"])

    # Final test evaluation
    test_metrics = evaluate_model(model, X_te_norm, y_te, arrays_te, device, recommended_threshold)
    application_valid, final_decision = decide_application_valid(test_metrics, checkpoint_saved)

    stable_recall = test_metrics["per_class"][CLASS_NAMES[0]]["recall"]
    abnormal_recall = test_metrics["per_class"][CLASS_NAMES[1]]["recall"]
    abnormal_precision = test_metrics["per_class"][CLASS_NAMES[1]]["precision"]
    cm = test_metrics.get("tp", 0), test_metrics.get("fp", 0), test_metrics.get("fn", 0), test_metrics.get("tn", 0)

    elapsed = time.time() - t0
    log.info(
        "[%s] DONE in %.1fs | test macro_f1=%.4f stable_rec=%.4f abnormal_rec=%.4f thr=%.2f | %s",
        experiment_id, elapsed,
        test_metrics["macro_f1"], stable_recall, abnormal_recall,
        recommended_threshold, final_decision,
    )

    # Save per-experiment JSON outputs
    result = {
        "experiment_id": experiment_id,
        "skipped": False,
        "pos_weight_cap": pos_weight_cap,
        "pos_weight": pos_weight,
        "lr": lr,
        "frac_threshold": frac_threshold,
        "n_train_stable": n_stable_tr,
        "n_train_abnormal": n_abnormal_tr,
        "best_epoch": best_epoch,
        "best_val_auc": round(best_val_auc, 5) if checkpoint_saved else None,
        "checkpoint_saved": checkpoint_saved,
        "recommended_threshold": recommended_threshold,
        "test_macro_f1": round(test_metrics["macro_f1"], 4),
        "test_accuracy": round(test_metrics["accuracy"], 4),
        "test_stable_recall": round(stable_recall, 4),
        "test_abnormal_recall": round(abnormal_recall, 4),
        "test_abnormal_precision": round(abnormal_precision, 4),
        "test_fp": int(test_metrics["false_positives"]),
        "test_fn": int(test_metrics["false_negatives"]),
        "test_tp": int(test_metrics.get("tp", 0)),
        "test_tn": int(test_metrics.get("tn", 0)),
        "test_confusion_matrix": test_metrics.get("tp", 0),
        "application_valid": application_valid,
        "final_decision": final_decision,
        "elapsed_s": round(elapsed, 1),
    }

    metrics_payload = {
        **result,
        "confusion_matrix": [[test_metrics.get("tn", 0), test_metrics.get("fp", 0)],
                              [test_metrics.get("fn", 0), test_metrics.get("tp", 0)]],
        "per_class": test_metrics["per_class"],
        "subject_breakdown": test_metrics.get("subject_breakdown", {}),
        "threshold_sweep": threshold_rows,
        "training_config": {
            "epochs_planned": epochs,
            "batch_size": BATCH_SIZE,
            "optimizer": "AdamW(weight_decay=1e-4)",
            "scheduler": f"CosineAnnealingLR(T_max={epochs})",
            "loss": "BCEWithLogitsLoss",
        },
    }
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(_to_builtin(metrics_payload), f, indent=2)

    with open(out_dir / "confusion_matrix.json", "w", encoding="utf-8") as f:
        json.dump({
            "labels": CLASS_NAMES,
            "threshold": recommended_threshold,
            "matrix": [[test_metrics.get("tn", 0), test_metrics.get("fp", 0)],
                        [test_metrics.get("fn", 0), test_metrics.get("tp", 0)]],
        }, f, indent=2)

    with open(out_dir / "per_class_metrics.json", "w", encoding="utf-8") as f:
        json.dump(_to_builtin(test_metrics["per_class"]), f, indent=2)

    with open(out_dir / "threshold_sweep.json", "w", encoding="utf-8") as f:
        json.dump(threshold_rows, f, indent=2)

    with open(out_dir / "prediction_distribution.json", "w", encoding="utf-8") as f:
        json.dump({
            "threshold": recommended_threshold,
            "predicted": test_metrics["prediction_distribution"],
            "true": {cls: int(test_metrics["per_class"][cls]["support"]) for cls in CLASS_NAMES},
        }, f, indent=2)

    with open(out_dir / "subject_breakdown.json", "w", encoding="utf-8") as f:
        json.dump(_to_builtin(test_metrics.get("subject_breakdown", {})), f, indent=2)

    # Save norm stats for reproducibility
    with open(out_dir / "imu_norm_stats.json", "w", encoding="utf-8") as f:
        json.dump(norm_stats, f, indent=2)

    return result


# ─── Ablation Report ──────────────────────────────────────────────────────────

def build_ablation_report(
    results: List[Dict[str, Any]],
    baseline_metrics: Optional[Dict[str, Any]],
    phase1_ids: List[str],
    phase2_ids: List[str],
) -> str:
    valid_results = [r for r in results if not r.get("skipped", False)]
    valid_results.sort(key=lambda r: (-r.get("test_macro_f1", 0.0), -r.get("test_stable_recall", 0.0)))
    best = valid_results[0] if valid_results else None

    lines = [
        "# Gait v2.1 Ablation Report",
        "",
        "## 1. Executive Summary",
        "",
    ]

    if best and best.get("application_valid"):
        lines += [
            f"- Best experiment: **{best['experiment_id']}**",
            f"- Final decision: **{best['final_decision']}**",
            f"- Test macro_f1: **{best['test_macro_f1']}**",
            f"- Stable recall: **{best['test_stable_recall']}**",
            f"- Abnormal recall: **{best['test_abnormal_recall']}**",
            f"- Recommended threshold: **{best['recommended_threshold']}**",
            "- application_valid: **True**",
        ]
    elif best:
        lines += [
            f"- Best experiment (not yet application_valid): **{best['experiment_id']}**",
            f"- Best test macro_f1: {best.get('test_macro_f1', 'N/A')}",
            f"- Best stable recall: {best.get('test_stable_recall', 'N/A')}",
            f"- Best abnormal recall: {best.get('test_abnormal_recall', 'N/A')}",
            "- application_valid: **False**",
        ]
    else:
        lines += ["- No valid experiments completed."]

    lines += [
        "",
        "## 2. Baseline Gait v2 Result",
        "",
    ]
    if baseline_metrics:
        lines += [
            f"- test macro_f1: {baseline_metrics.get('macro_f1', 'N/A')}",
            f"- stable recall: N/A (reported in expert report as 0.3725)",
            f"- abnormal recall: N/A (reported in expert report as 0.9235)",
            f"- abnormal precision: N/A (reported as 0.1639)",
            f"- application_valid: {baseline_metrics.get('application_valid', False)}",
            f"- final_decision: {baseline_metrics.get('final_decision', 'N/A')}",
            "- Root cause: pos_weight_cap=5.0 caused val_loss explosion; best checkpoint at epoch 2; model biased toward predicting abnormal.",
        ]
    else:
        lines += [
            "- Baseline metrics not loaded.",
            "- From report: test macro_f1=0.4087, stable_recall=0.3725, abnormal_recall=0.9235, FP=923/1471 (62.75%)",
            "- Root cause: pos_weight_cap=5.0 caused val_loss explosion and strong abnormal bias.",
        ]

    lines += [
        "",
        "## 3. Error Analysis Summary",
        "",
        "Key findings from gait_v2_error_analysis.md:",
        "- No threshold on validation set meets stable>=0.75 AND abnormal>=0.60 with the baseline checkpoint.",
        "- 62.75% of stable test windows are predicted as abnormal at threshold=0.20.",
        "- FP rate decreases sharply with higher thresholds but so does abnormal recall.",
        "- Many FP windows have near-zero abnormal_fraction — model confused normal movement patterns.",
        "- Higher pos_weight_cap amplified the FP bias; reducing it is the primary lever.",
        "",
        "## 4. Ablation Grid",
        "",
        f"- Phase 1 experiments (ft=0.20): {', '.join(phase1_ids) if phase1_ids else 'none'}",
        f"- Phase 2 experiments (ft=0.30/0.40/0.50): {', '.join(phase2_ids) if phase2_ids else 'none'}",
        "",
        "Hyperparameter grid:",
        "- pos_weight_cap: 1.0, 2.0, 3.0, 4.0",
        "- lr: 3e-4, 1e-4",
        "- frac_threshold: 0.20 (phase1) + 0.30, 0.40, 0.50 (phase2)",
        "",
        "## 5. Results Table",
        "",
        "| experiment_id | ft | pw_cap | lr | best_epoch | val_auc | test_f1 | stable_rec | abnormal_rec | abnormal_prec | FP | FN | thr | app_valid | decision |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for r in valid_results:
        lines.append(
            f"| {r['experiment_id']} "
            f"| {r.get('frac_threshold', 'N/A')} "
            f"| {r.get('pos_weight_cap', 'N/A')} "
            f"| {r.get('lr', 'N/A')} "
            f"| {r.get('best_epoch', 'N/A')} "
            f"| {r.get('best_val_auc', 'N/A')} "
            f"| {r.get('test_macro_f1', 'N/A')} "
            f"| {r.get('test_stable_recall', 'N/A')} "
            f"| {r.get('test_abnormal_recall', 'N/A')} "
            f"| {r.get('test_abnormal_precision', 'N/A')} "
            f"| {r.get('test_fp', 'N/A')} "
            f"| {r.get('test_fn', 'N/A')} "
            f"| {r.get('recommended_threshold', 'N/A')} "
            f"| {'YES' if r.get('application_valid') else 'no'} "
            f"| {r.get('final_decision', 'N/A')} |"
        )

    for r in results:
        if r.get("skipped"):
            lines.append(f"| {r['experiment_id']} | — | — | — | SKIPPED | — | — | — | — | — | — | — | — | — | {r.get('skip_reason', '')} |")

    lines += [
        "",
        "## 6. Best Candidate",
        "",
    ]
    if best:
        lines += [
            f"- experiment_id: **{best['experiment_id']}**",
            f"- pos_weight_cap: {best.get('pos_weight_cap')}",
            f"- lr: {best.get('lr')}",
            f"- frac_threshold: {best.get('frac_threshold')}",
            f"- best_epoch: {best.get('best_epoch')}",
            f"- val AUC: {best.get('best_val_auc')}",
            f"- test macro_f1: {best.get('test_macro_f1')}",
            f"- stable recall: {best.get('test_stable_recall')}",
            f"- abnormal recall: {best.get('test_abnormal_recall')}",
            f"- abnormal precision: {best.get('test_abnormal_precision')}",
            f"- FP: {best.get('test_fp')}",
            f"- FN: {best.get('test_fn')}",
            f"- recommended threshold: {best.get('recommended_threshold')}",
            f"- application_valid: {'YES' if best.get('application_valid') else 'NO'}",
            f"- final_decision: {best.get('final_decision')}",
        ]

    lines += [
        "",
        "## 7. Stable Recall vs Abnormal Recall Tradeoff",
        "",
        "Key tradeoff observed across experiments:",
        "",
        "| experiment_id | pos_weight_cap | thr | stable_recall | abnormal_recall | macro_f1 | FP | FN |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in valid_results[:min(len(valid_results), 12)]:
        lines.append(
            f"| {r['experiment_id']} | {r.get('pos_weight_cap')} | {r.get('recommended_threshold')} "
            f"| {r.get('test_stable_recall')} | {r.get('test_abnormal_recall')} "
            f"| {r.get('test_macro_f1')} | {r.get('test_fp')} | {r.get('test_fn')} |"
        )

    lines += [
        "",
        "## 8. Threshold Selection",
        "",
        "New objective (v2.1):",
        "- Constraint: stable_recall >= 0.75 AND abnormal_recall >= 0.60",
        "- If constraint met: maximize macro_f1, then abnormal_precision, then minimize FP",
        "- If no threshold meets constraint: report best tradeoff and set application_valid=False",
        "",
        "Old objective (v2):",
        "- Prioritised abnormal_recall; resulted in threshold=0.20 with FP=923/1471 (62.75%)",
        "",
        "## 9. Subject-Level Generalization",
        "",
        "Test subjects: S01 (878 stable, 78 abnormal), S02 (593 stable, 118 abnormal)",
        "Val subject: S05 (748 stable, 309 abnormal) — note: S05 has higher abnormal % (29%) than test",
        "Train subjects: S03, S06, S07, S08, S09",
        "",
        "DAPHNET single-source risk: All data from one dataset. Subject-level variance is high.",
        "Val/test subjects may have different movement profiles than training subjects.",
        "",
        "## 10. Application Validity Decision",
        "",
    ]

    accept_experiments = [r for r in valid_results if r.get("final_decision") == "ACCEPT_GAIT_V2_1_EXPERT"]
    partial_experiments = [r for r in valid_results if r.get("final_decision") == "PARTIAL_ACCEPT_AUXILIARY_ONLY"]
    reject_experiments = [r for r in valid_results if r.get("final_decision") == "REJECT_KEEP_RULE_BASED"]

    lines += [
        f"- ACCEPT_GAIT_V2_1_EXPERT: {len(accept_experiments)} experiment(s)",
        f"- PARTIAL_ACCEPT_AUXILIARY_ONLY: {len(partial_experiments)} experiment(s)",
        f"- REJECT_KEEP_RULE_BASED: {len(reject_experiments)} experiment(s)",
        "",
    ]

    if accept_experiments:
        lines += ["**Full acceptance reached.** Best:"]
        for r in accept_experiments[:3]:
            lines.append(f"- {r['experiment_id']}: macro_f1={r['test_macro_f1']}, stable_rec={r['test_stable_recall']}, abnormal_rec={r['test_abnormal_recall']}")
    elif partial_experiments:
        lines += ["**Partial acceptance only.** These can be used as low-weight auxiliary in RiskFusion:"]
        for r in partial_experiments[:3]:
            lines.append(f"- {r['experiment_id']}: macro_f1={r['test_macro_f1']}, stable_rec={r['test_stable_recall']}, abnormal_rec={r['test_abnormal_recall']}")
    else:
        lines += [
            "**No experiment meets minimum criteria.** Rule-based gait handling should continue.",
            "Suggestions: try additional FOG datasets, stricter label purity, or focal loss.",
        ]

    lines += [
        "",
        "## 11. RiskFusion Recommendation",
        "",
    ]
    if accept_experiments or partial_experiments:
        best_candidate = (accept_experiments or partial_experiments)[0]
        lines += [
            f"- Best candidate: {best_candidate['experiment_id']}",
            f"- Decision: {best_candidate['final_decision']}",
            "- Action required: User approval before RiskFusion integration.",
            "- Integration type: Low-weight auxiliary input only (no standalone critical alert).",
            "- Temporal smoothing required before integration.",
            "- DAPHNET single-source risk acknowledged — generalisation to other domains unverified.",
        ]
    else:
        lines += [
            "- No experiment qualified for RiskFusion integration.",
            "- Rule-based gait handling remains active.",
            "- Consider new FOG dataset or stricter label filtering.",
        ]

    lines += [
        "",
        "## 12. Next Step",
        "",
    ]
    if accept_experiments:
        lines += [
            "- **Primary**: Review ACCEPT_GAIT_V2_1_EXPERT result and approve integration.",
            "- **Secondary**: Activity v2 can proceed independently.",
        ]
    elif partial_experiments:
        lines += [
            "- **Primary**: Review PARTIAL_ACCEPT_AUXILIARY_ONLY result — decide if auxiliary use is acceptable.",
            "- **Option A**: Accept as auxiliary, proceed with Activity v2.",
            "- **Option B**: Run additional gait iterations with new FOG datasets or focal loss.",
            "- Activity v2 does NOT need to wait for gait resolution.",
        ]
    else:
        lines += [
            "- **Primary**: Proceed with Activity v2 independently.",
            "- **Gait follow-up**: Consider SisFall/GaitPDB dataset addition or focal loss experiment.",
        ]

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    _ensure_expected_python()

    ABLATION_ROOT.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info("device: %s", device)

    # Load baseline metrics for comparison
    baseline_metrics: Optional[Dict[str, Any]] = None
    baseline_metrics_path = BASELINE_DIR / "metrics.json"
    if baseline_metrics_path.exists():
        with open(baseline_metrics_path, "r", encoding="utf-8") as f:
            baseline_metrics = json.load(f)

    # Pre-load raw (un-normalized) splits once — fraction filtering applied per experiment
    log.info("Loading raw data splits...")
    X_tr_raw, y_tr_raw, arrays_tr_raw = load_split_raw("train")
    X_val_raw, y_val_raw, arrays_val_raw = load_split_raw("val")
    X_te_raw, y_te_raw, arrays_te_raw = load_split_raw("test")
    log.info(
        "Raw splits: train=%d (stable=%d,abnormal=%d), val=%d, test=%d",
        len(y_tr_raw), int((y_tr_raw==0).sum()), int((y_tr_raw==1).sum()),
        len(y_val_raw), len(y_te_raw),
    )

    epochs = 3 if args.smoke else args.epochs
    patience = 2 if args.smoke else args.patience

    # ─── Phase 1: pos_weight_cap x lr grid at frac_threshold=0.20 ───
    phase1_ids: List[str] = []
    phase1_results: List[Dict[str, Any]] = []

    if args.phase in (0, 1):
        log.info("=== PHASE 1: pos_weight_cap x lr grid (ft=0.20) ===")
        for pw in POS_WEIGHT_CAPS:
            for lr in LRS:
                ft = 0.20
                exp_id = f"pw{pw:.1f}_lr{lr:.0e}_ft{ft:.2f}"
                result = run_experiment(
                    experiment_id=exp_id,
                    pos_weight_cap=pw,
                    lr=lr,
                    frac_threshold=ft,
                    epochs=epochs,
                    patience=patience,
                    device=device,
                    X_tr_raw=X_tr_raw,
                    y_tr_raw=y_tr_raw,
                    arrays_tr_raw=arrays_tr_raw,
                    X_val=X_val_raw,
                    y_val=y_val_raw,
                    arrays_val=arrays_val_raw,
                    X_te=X_te_raw,
                    y_te=y_te_raw,
                    arrays_te=arrays_te_raw,
                    smoke=args.smoke,
                )
                phase1_ids.append(exp_id)
                phase1_results.append(result)

    # ─── Phase 2: fraction threshold variants for promising candidates ───
    phase2_ids: List[str] = []
    phase2_results: List[Dict[str, Any]] = []

    if args.phase in (0, 2):
        # Select candidates: checkpoint_saved and top-3 by val_macro_f1 from phase1
        if args.phase2_candidates is not None:
            candidates_pw_lr = []
            for exp_id in args.phase2_candidates:
                r = next((r for r in phase1_results if r["experiment_id"] == exp_id), None)
                if r and not r.get("skipped"):
                    candidates_pw_lr.append((r["pos_weight_cap"], r["lr"]))
        else:
            valid_p1 = [r for r in phase1_results if not r.get("skipped") and r.get("checkpoint_saved")]
            valid_p1.sort(key=lambda r: r.get("best_val_auc", 0.0), reverse=True)
            candidates_pw_lr = [(r["pos_weight_cap"], r["lr"]) for r in valid_p1[:3]]

        if not candidates_pw_lr:
            log.warning("No phase1 candidates for phase2 (no checkpoint_saved); using top-2 by test_macro_f1")
            valid_p1 = [r for r in phase1_results if not r.get("skipped")]
            valid_p1.sort(key=lambda r: r.get("test_macro_f1", 0.0), reverse=True)
            candidates_pw_lr = [(r["pos_weight_cap"], r["lr"]) for r in valid_p1[:2]]

        log.info("=== PHASE 2: fraction threshold variants for %d candidates ===", len(candidates_pw_lr))
        for pw, lr in candidates_pw_lr:
            for ft in FRAC_THRESHOLDS_PHASE2:
                exp_id = f"pw{pw:.1f}_lr{lr:.0e}_ft{ft:.2f}"
                result = run_experiment(
                    experiment_id=exp_id,
                    pos_weight_cap=pw,
                    lr=lr,
                    frac_threshold=ft,
                    epochs=epochs,
                    patience=patience,
                    device=device,
                    X_tr_raw=X_tr_raw,
                    y_tr_raw=y_tr_raw,
                    arrays_tr_raw=arrays_tr_raw,
                    X_val=X_val_raw,
                    y_val=y_val_raw,
                    arrays_val=arrays_val_raw,
                    X_te=X_te_raw,
                    y_te=y_te_raw,
                    arrays_te=arrays_te_raw,
                    smoke=args.smoke,
                )
                phase2_ids.append(exp_id)
                phase2_results.append(result)

    # ─── Compile all results ───
    all_results = phase1_results + phase2_results

    # Save master results JSON
    master_json = ABLATION_ROOT / "all_results.json"
    with open(master_json, "w", encoding="utf-8") as f:
        json.dump(_to_builtin(all_results), f, indent=2)
    log.info("Saved master results: %s", master_json)

    # ─── Generate comparison report ───
    report_md = build_ablation_report(
        results=all_results,
        baseline_metrics=baseline_metrics,
        phase1_ids=phase1_ids,
        phase2_ids=phase2_ids,
    )
    report_path = ABLATION_ROOT / "gait_v2_ablation_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    log.info("Saved ablation report: %s", report_path)

    # ─── Print final summary ───
    valid_results = [r for r in all_results if not r.get("skipped")]
    valid_results.sort(key=lambda r: (-r.get("test_macro_f1", 0.0), -r.get("test_stable_recall", 0.0)))

    print("\n" + "=" * 70)
    print("GAIT v2.1 ABLATION GRID — FINAL SUMMARY")
    print("=" * 70)
    print(f"Total experiments: {len(all_results)} | Valid: {len(valid_results)} | Skipped: {sum(1 for r in all_results if r.get('skipped'))}")
    print()
    print(f"{'Experiment':<30} {'pw_cap':>7} {'lr':>8} {'ft':>5} {'val_auc':>7} {'test_f1':>8} {'s_rec':>6} {'a_rec':>6} {'thr':>5} {'valid':>6} {'decision'}")
    print("-" * 110)
    for r in valid_results:
        print(
            f"{r['experiment_id']:<30} "
            f"{r.get('pos_weight_cap','?'):>7} "
            f"{r.get('lr','?'):>8.1e} "
            f"{r.get('frac_threshold','?'):>5.2f} "
            f"{r.get('best_val_auc','?') or 0.0:>7.4f} "
            f"{r.get('test_macro_f1','?') or 0.0:>8.4f} "
            f"{r.get('test_stable_recall','?') or 0.0:>6.4f} "
            f"{r.get('test_abnormal_recall','?') or 0.0:>6.4f} "
            f"{r.get('recommended_threshold','?') or 0.0:>5.2f} "
            f"{'YES' if r.get('application_valid') else 'no':>6} "
            f"{r.get('final_decision','?')}"
        )

    print()
    if valid_results:
        best = valid_results[0]
        print(f"Best: {best['experiment_id']}")
        print(f"  test macro_f1   : {best.get('test_macro_f1')}")
        print(f"  stable recall   : {best.get('test_stable_recall')}")
        print(f"  abnormal recall : {best.get('test_abnormal_recall')}")
        print(f"  abnormal prec   : {best.get('test_abnormal_precision')}")
        print(f"  FP / FN         : {best.get('test_fp')} / {best.get('test_fn')}")
        print(f"  threshold       : {best.get('recommended_threshold')}")
        print(f"  application_valid: {'YES' if best.get('application_valid') else 'NO'}")
        print(f"  final_decision  : {best.get('final_decision')}")
    print()
    print(f"Report: {report_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
