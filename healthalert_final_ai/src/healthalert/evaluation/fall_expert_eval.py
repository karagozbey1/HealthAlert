"""
fall_expert_eval.py
─────────────────────────────────────────────────────────────────────────────
Evaluation utilities for the Fall Detection Expert model.

Produces:
  - metrics.json
  - confusion_matrix.json
  - prediction_distribution.json
  - near_fall_holdout_analysis.json  (if near_fall test windows provided)
  - fall_expert_report.md
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import torch
from torch.utils.data import DataLoader

log = logging.getLogger("healthalert.evaluation.fall_expert")


def evaluate_fall_expert(
    model: torch.nn.Module,
    test_loader: DataLoader,
    device: torch.device,
    out_dir: Path,
    threshold: float = 0.5,
    near_fall_loader: Optional[DataLoader] = None,
    dataset_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run full evaluation on test set.
    Saves all artefacts to out_dir.
    Returns a results dict.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model.eval()
    all_labels: List[int] = []
    all_preds: List[int] = []
    all_probs: List[float] = []

    with torch.no_grad():
        for batch in test_loader:
            x, y = batch
            x = x.to(device, dtype=torch.float32)
            out = model(x)
            probs = out["fall_prob"].cpu().numpy()
            preds = (probs >= threshold).astype(int)
            all_probs.extend(probs.tolist())
            all_preds.extend(preds.tolist())
            all_labels.extend(y.numpy().astype(int).tolist())

    labels = np.array(all_labels)
    preds = np.array(all_preds)

    metrics = _compute_metrics(labels, preds, all_probs)
    cm = _confusion_matrix(labels, preds)
    pred_dist = _pred_distribution(preds, all_probs)

    # Save artefacts
    with open(out_dir / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    with open(out_dir / "confusion_matrix.json", "w") as f:
        json.dump(cm, f, indent=2)
    with open(out_dir / "prediction_distribution.json", "w") as f:
        json.dump(pred_dist, f, indent=2)

    # Near-fall holdout analysis
    near_fall_results: Optional[Dict[str, Any]] = None
    if near_fall_loader is not None:
        near_fall_results = _near_fall_holdout_analysis(model, near_fall_loader, device, threshold)
        with open(out_dir / "near_fall_holdout_analysis.json", "w") as f:
            json.dump(near_fall_results, f, indent=2)

    # Write markdown report
    _write_report(
        out_dir=out_dir,
        metrics=metrics,
        cm=cm,
        pred_dist=pred_dist,
        near_fall_results=near_fall_results,
        threshold=threshold,
        dataset_info=dataset_info,
    )

    log.info(f"Fall expert evaluation complete → {out_dir}")
    return {
        "metrics": metrics,
        "confusion_matrix": cm,
        "prediction_distribution": pred_dist,
        "near_fall_holdout": near_fall_results,
    }


def _compute_metrics(
    labels: np.ndarray, preds: np.ndarray, probs: List[float]
) -> Dict[str, Any]:
    from sklearn.metrics import (
        classification_report,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    eps = 1e-9
    from sklearn.metrics import confusion_matrix as sk_cm

    cm = sk_cm(labels, preds, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)

    fall_recall = tp / (tp + fn + eps)
    fall_precision = tp / (tp + fp + eps)
    normal_recall = tn / (tn + fp + eps)
    fall_f1 = f1_score(labels, preds, pos_label=1, zero_division=0)
    macro_f1 = f1_score(labels, preds, average="macro", zero_division=0)

    app_score = (
        0.35 * fall_recall
        + 0.25 * fall_precision
        + 0.25 * macro_f1
        + 0.15 * normal_recall
    )

    auc = None
    if len(np.unique(labels)) > 1:
        try:
            auc = float(roc_auc_score(labels, probs))
        except Exception:
            auc = None

    # Threshold analysis (0.3, 0.4, 0.5, 0.6, 0.7)
    threshold_analysis: List[Dict[str, Any]] = []
    for t in [0.3, 0.4, 0.5, 0.6, 0.7]:
        tp_preds = (np.array(probs) >= t).astype(int)
        threshold_analysis.append(
            {
                "threshold": t,
                "fall_recall": float(recall_score(labels, tp_preds, pos_label=1, zero_division=0)),
                "fall_precision": float(precision_score(labels, tp_preds, pos_label=1, zero_division=0)),
                "macro_f1": float(f1_score(labels, tp_preds, average="macro", zero_division=0)),
            }
        )

    return {
        "fall_recall": round(float(fall_recall), 5),
        "fall_precision": round(float(fall_precision), 5),
        "normal_recall": round(float(normal_recall), 5),
        "fall_f1": round(float(fall_f1), 5),
        "macro_f1": round(float(macro_f1), 5),
        "fall_application_score": round(float(app_score), 5),
        "roc_auc": round(auc, 5) if auc is not None else None,
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
        "total_samples": int(len(labels)),
        "threshold_used": 0.5,
        "threshold_analysis": threshold_analysis,
        "collapse_detected": bool(
            normal_recall < 0.40 or fall_precision < 0.40 or macro_f1 < 0.40
        ),
    }


def _confusion_matrix(labels: np.ndarray, preds: np.ndarray) -> Dict[str, Any]:
    from sklearn.metrics import confusion_matrix as sk_cm

    cm = sk_cm(labels, preds, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)
    return {
        "matrix": cm.tolist(),
        "labels": ["normal (0)", "fall (1)"],
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
    }


def _pred_distribution(preds: np.ndarray, probs: List[float]) -> Dict[str, Any]:
    probs_arr = np.array(probs)
    total = len(preds)
    n_fall = int((preds == 1).sum())
    n_normal = int((preds == 0).sum())
    return {
        "total": total,
        "predicted_fall": n_fall,
        "predicted_normal": n_normal,
        "pct_fall": round(n_fall / max(total, 1) * 100, 2),
        "pct_normal": round(n_normal / max(total, 1) * 100, 2),
        "prob_mean": round(float(probs_arr.mean()), 5),
        "prob_std": round(float(probs_arr.std()), 5),
        "prob_p25": round(float(np.percentile(probs_arr, 25)), 5),
        "prob_p50": round(float(np.percentile(probs_arr, 50)), 5),
        "prob_p75": round(float(np.percentile(probs_arr, 75)), 5),
    }


def _near_fall_holdout_analysis(
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
    threshold: float,
) -> Dict[str, Any]:
    """Analyze how the fall expert treats near_fall windows (excluded from training)."""
    model.eval()
    probs: List[float] = []
    preds: List[int] = []

    with torch.no_grad():
        for batch in loader:
            x = batch[0] if isinstance(batch, (list, tuple)) else batch
            x = x.to(device, dtype=torch.float32)
            out = model(x)
            p = out["fall_prob"].cpu().numpy()
            probs.extend(p.tolist())
            preds.extend((p >= threshold).astype(int).tolist())

    if not probs:
        return {"n_near_fall_windows": 0, "note": "no near_fall windows provided"}

    probs_arr = np.array(probs)
    return {
        "n_near_fall_windows": len(probs),
        "predicted_as_fall_pct": round(float((np.array(preds) == 1).mean() * 100), 2),
        "predicted_as_normal_pct": round(float((np.array(preds) == 0).mean() * 100), 2),
        "mean_fall_prob": round(float(probs_arr.mean()), 5),
        "std_fall_prob": round(float(probs_arr.std()), 5),
        "interpretation": (
            "near_fall windows show elevated fall probability — "
            "use as risk-band signal, not hard fall classification"
        ),
    }


def _write_report(
    out_dir: Path,
    metrics: Dict[str, Any],
    cm: Dict[str, Any],
    pred_dist: Dict[str, Any],
    near_fall_results: Optional[Dict[str, Any]],
    threshold: float,
    dataset_info: Optional[Dict[str, Any]],
) -> None:
    lines: List[str] = []
    lines.append("# Fall Expert — Evaluation Report")
    lines.append("")

    if dataset_info:
        lines.append("## Dataset Info")
        for k, v in dataset_info.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")

    lines.append("## Key Metrics")
    lines.append(f"- **fall_recall**: {metrics['fall_recall']:.4f}")
    lines.append(f"- **fall_precision**: {metrics['fall_precision']:.4f}")
    lines.append(f"- **normal_recall**: {metrics['normal_recall']:.4f}")
    lines.append(f"- **fall_f1**: {metrics['fall_f1']:.4f}")
    lines.append(f"- **macro_f1**: {metrics['macro_f1']:.4f}")
    lines.append(f"- **fall_application_score**: {metrics['fall_application_score']:.4f}")
    if metrics.get("roc_auc") is not None:
        lines.append(f"- **ROC AUC**: {metrics['roc_auc']:.4f}")
    lines.append(f"- **collapse_detected**: {metrics['collapse_detected']}")
    lines.append("")

    lines.append("## Confusion Matrix")
    lines.append("```")
    lines.append(f"           Predicted Normal  Predicted Fall")
    lines.append(f"True Normal      {cm['tn']:6d}          {cm['fp']:6d}")
    lines.append(f"True Fall        {cm['fn']:6d}          {cm['tp']:6d}")
    lines.append("```")
    lines.append(f"- TP={cm['tp']}, FP={cm['fp']}, TN={cm['tn']}, FN={cm['fn']}")
    lines.append("")

    lines.append("## Prediction Distribution")
    lines.append(f"- Total samples: {pred_dist['total']}")
    lines.append(f"- Predicted fall: {pred_dist['predicted_fall']} ({pred_dist['pct_fall']}%)")
    lines.append(f"- Predicted normal: {pred_dist['predicted_normal']} ({pred_dist['pct_normal']}%)")
    lines.append(f"- Mean fall probability: {pred_dist['prob_mean']:.4f} ± {pred_dist['prob_std']:.4f}")
    lines.append("")

    lines.append("## Threshold Analysis")
    lines.append("| Threshold | fall_recall | fall_precision | macro_f1 |")
    lines.append("|-----------|-------------|----------------|----------|")
    for ta in metrics.get("threshold_analysis", []):
        lines.append(
            f"| {ta['threshold']} | {ta['fall_recall']:.4f} | {ta['fall_precision']:.4f} | {ta['macro_f1']:.4f} |"
        )
    lines.append("")

    if near_fall_results:
        lines.append("## Near-Fall Holdout Analysis")
        lines.append(f"- Near-fall windows evaluated: {near_fall_results.get('n_near_fall_windows', 0)}")
        lines.append(f"- Predicted as fall: {near_fall_results.get('predicted_as_fall_pct', '—')}%")
        lines.append(f"- Predicted as normal: {near_fall_results.get('predicted_as_normal_pct', '—')}%")
        lines.append(f"- Mean fall probability: {near_fall_results.get('mean_fall_prob', '—')}")
        lines.append(f"- Interpretation: {near_fall_results.get('interpretation', '')}")
        lines.append("")

    lines.append("## Application Usability")
    collapsed = metrics.get("collapse_detected", False)
    app_score = metrics.get("fall_application_score", 0.0)
    if collapsed:
        lines.append("**⚠ MODEL NOT APPLICATION-USABLE — collapse detected.**")
        lines.append("Do not deploy this checkpoint. Recheck data pipeline and training config.")
    elif app_score >= 0.60:
        lines.append("**✓ Model is application-usable.** fall_application_score ≥ 0.60.")
    else:
        lines.append(
            f"**⚠ Model marginal** — fall_application_score={app_score:.4f}. "
            "Consider more training epochs or dataset review."
        )
    lines.append("")
    lines.append("---")
    lines.append("_Generated by healthalert.evaluation.fall_expert_eval_")

    with open(out_dir / "fall_expert_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    log.info(f"Report → {out_dir / 'fall_expert_report.md'}")
