"""Evaluation metrics for all tasks.

Includes standard classification metrics, MCC, macro-F1,
calibration confidence summary, threshold calibration,
risk-level ordinal evaluation, and per-task report generation.
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score,
    roc_auc_score, confusion_matrix, mean_squared_error,
    matthews_corrcoef, cohen_kappa_score, classification_report,
)

logger = logging.getLogger("healthalert.training.metrics")


def compute_binary_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: np.ndarray = None,
    prefix: str = "",
) -> Dict[str, float]:
    """Compute standard binary classification metrics.

    Args:
        y_true: Ground truth binary labels.
        y_pred: Predicted binary labels.
        y_prob: Predicted probabilities (for AUC).
        prefix: Prefix for metric names.

    Returns:
        Dict of metric_name → value.
    """
    metrics: Dict[str, float] = {}
    p = prefix + "_" if prefix else ""

    metrics[f"{p}accuracy"] = float(accuracy_score(y_true, y_pred))
    metrics[f"{p}f1"] = float(f1_score(y_true, y_pred, zero_division=0))
    metrics[f"{p}macro_f1"] = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    metrics[f"{p}precision"] = float(precision_score(y_true, y_pred, zero_division=0))
    metrics[f"{p}recall"] = float(recall_score(y_true, y_pred, zero_division=0))

    # Matthews Correlation Coefficient
    try:
        metrics[f"{p}mcc"] = float(matthews_corrcoef(y_true, y_pred))
    except Exception:
        metrics[f"{p}mcc"] = 0.0

    # AUC
    if y_prob is not None and len(np.unique(y_true)) > 1:
        try:
            metrics[f"{p}auc"] = float(roc_auc_score(y_true, y_prob))
        except ValueError:
            metrics[f"{p}auc"] = 0.0
    else:
        metrics[f"{p}auc"] = 0.0

    # Confusion matrix
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    if cm.shape == (2, 2):
        tn, fp, fn, tp = cm.ravel()
        metrics[f"{p}tn"] = int(tn)
        metrics[f"{p}fp"] = int(fp)
        metrics[f"{p}fn"] = int(fn)
        metrics[f"{p}tp"] = int(tp)
        metrics[f"{p}specificity"] = float(tn / (tn + fp + 1e-8))

    # Calibration confidence summary
    if y_prob is not None and len(y_prob) > 0:
        metrics[f"{p}conf_mean"] = float(np.mean(y_prob))
        metrics[f"{p}conf_std"] = float(np.std(y_prob))
        # Expected calibration: mean predicted prob of positives vs actual rate
        pos_mask = y_true == 1
        if pos_mask.sum() > 0:
            metrics[f"{p}conf_pos_mean"] = float(np.mean(y_prob[pos_mask]))
        neg_mask = y_true == 0
        if neg_mask.sum() > 0:
            metrics[f"{p}conf_neg_mean"] = float(np.mean(y_prob[neg_mask]))

    return metrics


def compute_regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    prefix: str = "",
) -> Dict[str, float]:
    """Compute regression metrics."""
    p = prefix + "_" if prefix else ""
    return {
        f"{p}mse": float(mean_squared_error(y_true, y_pred)),
        f"{p}rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        f"{p}mae": float(np.mean(np.abs(y_true - y_pred))),
    }


def compute_all_metrics(
    all_outputs: Dict[str, np.ndarray],
    all_targets: Dict[str, np.ndarray],
    threshold: float = 0.5,
    calibrated_thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """Compute metrics for all tasks.

    Args:
        all_outputs: Model outputs {task: predictions array}.
        all_targets: Ground truth {task: labels array}.
        threshold: Default threshold for binary classification.
        calibrated_thresholds: Per-task calibrated thresholds (overrides default).

    Returns:
        Flat dict of all metrics.
    """
    metrics: Dict[str, float] = {}
    if calibrated_thresholds is None:
        calibrated_thresholds = {}

    # Fall detection
    if "fall" in all_outputs and "fall" in all_targets and len(all_outputs["fall"]) > 0:
        fall_prob = all_outputs["fall"]
        t = calibrated_thresholds.get("fall", threshold)
        fall_pred = (fall_prob > t).astype(int)
        fall_true = all_targets["fall"].astype(int)
        metrics.update(compute_binary_metrics(fall_true, fall_pred, fall_prob, prefix="fall"))
        metrics["fall_threshold"] = t

    # Instability
    if "instability" in all_outputs and "instability" in all_targets and len(all_outputs["instability"]) > 0:
        inst_prob = all_outputs["instability"]
        t = calibrated_thresholds.get("instability", threshold)
        inst_pred = (inst_prob > t).astype(int)
        inst_true = all_targets["instability"].astype(int)
        metrics.update(compute_binary_metrics(inst_true, inst_pred, inst_prob, prefix="instability"))
        metrics["instability_threshold"] = t

    # Quality
    if "quality" in all_outputs and "quality" in all_targets and len(all_outputs["quality"]) > 0:
        q_prob = all_outputs["quality"]
        t = calibrated_thresholds.get("quality", threshold)
        q_pred = (q_prob > t).astype(int)
        q_true = all_targets["quality"].astype(int)
        metrics.update(compute_binary_metrics(q_true, q_pred, q_prob, prefix="quality"))
        metrics["quality_threshold"] = t

    # Risk score (regression)
    if "risk" in all_outputs and "risk" in all_targets and len(all_outputs["risk"]) > 0:
        metrics.update(compute_regression_metrics(
            all_targets["risk"], all_outputs["risk"], prefix="risk"
        ))
        # Risk-level ordinal evaluation
        metrics.update(compute_risk_level_metrics(
            all_targets["risk"], all_outputs["risk"], prefix="risk_level"
        ))

    return metrics


def calibrate_threshold(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    objective: str = "f1",
    n_steps: int = 200,
) -> Tuple[float, float]:
    """Find the optimal threshold on validation data.

    Args:
        y_true: Binary ground truth.
        y_prob: Predicted probabilities.
        objective: 'f1' or 'youden' (Youden's J = sens + spec - 1).
        n_steps: Number of threshold candidates.

    Returns:
        (best_threshold, best_score).
    """
    best_t, best_score = 0.5, 0.0
    for t in np.linspace(0.05, 0.95, n_steps):
        pred = (y_prob > t).astype(int)
        if objective == "f1":
            score = float(f1_score(y_true, pred, zero_division=0))
        else:  # youden
            tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
            sens = tp / max(tp + fn, 1)
            spec = tn / max(tn + fp, 1)
            score = sens + spec - 1.0
        if score > best_score:
            best_score = score
            best_t = float(t)
    return best_t, best_score


# ── Risk-level ordinal evaluation ────────────────────────────────────
RISK_LEVEL_NAMES = ["normal", "watch", "warning", "critical"]
RISK_LEVEL_THRESHOLDS = [0.0, 0.25, 0.50, 0.70]  # boundaries


def _risk_score_to_level(score: float) -> int:
    """Map continuous risk to ordinal level index. 0=normal..3=critical."""
    if score >= 0.70:
        return 3
    elif score >= 0.50:
        return 2
    elif score >= 0.25:
        return 1
    return 0


def compute_risk_level_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    prefix: str = "risk_level",
) -> Dict[str, float]:
    """Compute ordinal risk-level classification metrics.

    Both y_true and y_pred are continuous [0,1] risk scores.
    They are binned into ordinal levels first.
    """
    p = prefix + "_" if prefix else ""
    metrics: Dict[str, float] = {}

    true_levels = np.array([_risk_score_to_level(s) for s in y_true])
    pred_levels = np.array([_risk_score_to_level(s) for s in y_pred])

    n_classes = len(RISK_LEVEL_NAMES)
    labels = list(range(n_classes))

    metrics[f"{p}accuracy"] = float(accuracy_score(true_levels, pred_levels))
    metrics[f"{p}macro_f1"] = float(f1_score(true_levels, pred_levels, average="macro",
                                              labels=labels, zero_division=0))
    metrics[f"{p}weighted_f1"] = float(f1_score(true_levels, pred_levels, average="weighted",
                                                 labels=labels, zero_division=0))

    # Weighted kappa (ordinal-aware)
    try:
        metrics[f"{p}weighted_kappa"] = float(
            cohen_kappa_score(true_levels, pred_levels, weights="quadratic")
        )
    except Exception:
        metrics[f"{p}weighted_kappa"] = 0.0

    # Per-class precision/recall/f1
    for level_idx, level_name in enumerate(RISK_LEVEL_NAMES):
        mask_true = (true_levels == level_idx)
        mask_pred = (pred_levels == level_idx)
        tp = int((mask_true & mask_pred).sum())
        fp = int((~mask_true & mask_pred).sum())
        fn = int((mask_true & ~mask_pred).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-8) if (prec + rec) > 0 else 0.0
        metrics[f"{p}{level_name}_precision"] = float(prec)
        metrics[f"{p}{level_name}_recall"] = float(rec)
        metrics[f"{p}{level_name}_f1"] = float(f1)
        metrics[f"{p}{level_name}_support"] = int(mask_true.sum())

    # Confusion matrix (4x4)
    cm = confusion_matrix(true_levels, pred_levels, labels=labels)
    metrics[f"{p}confusion_matrix"] = cm.tolist()

    return metrics


def generate_task_report(metrics: Dict[str, float]) -> str:
    """Generate a formatted per-task metrics report.

    Returns a multi-line string suitable for logging or file output.
    """
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("  HealthAlert Evaluation Report")
    lines.append("=" * 60)

    task_prefixes = [
        ("Fall Detection", "fall_"),
        ("Instability Detection", "instability_"),
        ("PPG Quality", "quality_"),
        ("Risk Score (regression)", "risk_"),
        ("Risk Level (ordinal)", "risk_level_"),
    ]

    for task_name, prefix in task_prefixes:
        task_metrics = {k: v for k, v in metrics.items()
                        if k.startswith(prefix) and not isinstance(v, list)}
        if not task_metrics:
            continue
        lines.append(f"\n--- {task_name} ---")
        for k, v in sorted(task_metrics.items()):
            short_key = k[len(prefix):]
            if isinstance(v, float):
                lines.append(f"  {short_key:20s}: {v:.4f}")
            else:
                lines.append(f"  {short_key:20s}: {v}")

    # Risk-level confusion matrix
    cm_key = "risk_level_confusion_matrix"
    if cm_key in metrics:
        lines.append("\n--- Risk Level Confusion Matrix ---")
        lines.append(f"  {'':>10s}" + "".join(f"{n:>10s}" for n in RISK_LEVEL_NAMES))
        cm = metrics[cm_key]
        for i, row in enumerate(cm):
            lines.append(f"  {RISK_LEVEL_NAMES[i]:>10s}" + "".join(f"{v:>10d}" for v in row))

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)
