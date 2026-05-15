"""
fall_expert_trainer.py
─────────────────────────────────────────────────────────────────────────────
Training loop for the Fall Detection Expert model.

Key design rules (to prevent collapse repeat):
  1. Checkpoint metric is fall_application_score, not just fall_recall.
  2. Hard collapse detection rejects any checkpoint where:
       - normal_recall < 0.40
       - fall_precision < 0.40
       - macro_f1 < 0.40
       - >90% of predictions are the same class
  3. best_model.pt is ONLY saved when checkpoint_valid=True.
  4. last_model.pt is saved every epoch regardless.
  5. No WeightedRandomSampler.
  6. No class weights passed to loss by default (use mild pos_weight only).
  7. near_fall windows must be excluded BEFORE the data is passed here
     (handled in the dataset loader).

fall_application_score =
    0.35 * fall_recall
  + 0.25 * fall_precision
  + 0.25 * macro_f1
  + 0.15 * normal_recall
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

log = logging.getLogger("healthalert.training.fall_expert")


# ─── Collapse detection ───────────────────────────────────────────────────────

COLLAPSE_THRESHOLDS = {
    "normal_recall_min": 0.40,
    "fall_precision_min": 0.40,
    "macro_f1_min": 0.40,
    "dominant_class_ratio_max": 0.90,
}


def is_collapse(metrics: Dict[str, float], pred_counts: Dict[int, int]) -> Tuple[bool, str]:
    """
    Returns (collapsed, reason).
    A checkpoint is considered collapsed if any hard threshold is violated.
    """
    total = sum(pred_counts.values()) or 1
    dominant_ratio = max(pred_counts.values(), default=0) / total

    checks = [
        (
            metrics.get("normal_recall", 0.0) < COLLAPSE_THRESHOLDS["normal_recall_min"],
            f"normal_recall={metrics.get('normal_recall', 0):.3f} < {COLLAPSE_THRESHOLDS['normal_recall_min']}",
        ),
        (
            metrics.get("fall_precision", 0.0) < COLLAPSE_THRESHOLDS["fall_precision_min"],
            f"fall_precision={metrics.get('fall_precision', 0):.3f} < {COLLAPSE_THRESHOLDS['fall_precision_min']}",
        ),
        (
            metrics.get("macro_f1", 0.0) < COLLAPSE_THRESHOLDS["macro_f1_min"],
            f"macro_f1={metrics.get('macro_f1', 0):.3f} < {COLLAPSE_THRESHOLDS['macro_f1_min']}",
        ),
        (
            dominant_ratio > COLLAPSE_THRESHOLDS["dominant_class_ratio_max"],
            f"dominant_class_ratio={dominant_ratio:.3f} > {COLLAPSE_THRESHOLDS['dominant_class_ratio_max']}",
        ),
    ]
    for failed, reason in checks:
        if failed:
            return True, reason
    return False, ""


def fall_application_score(metrics: Dict[str, float]) -> float:
    """Composite checkpoint metric designed to reject collapses."""
    return (
        0.35 * metrics.get("fall_recall", 0.0)
        + 0.25 * metrics.get("fall_precision", 0.0)
        + 0.25 * metrics.get("macro_f1", 0.0)
        + 0.15 * metrics.get("normal_recall", 0.0)
    )


# ─── Metrics computation ──────────────────────────────────────────────────────

def compute_binary_metrics(
    all_labels: np.ndarray,
    all_preds: np.ndarray,
) -> Dict[str, float]:
    """
    Compute per-class and macro metrics for binary fall classification.
    Labels: 0=normal, 1=fall
    """
    from sklearn.metrics import (
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )

    if len(all_labels) == 0:
        return {}

    eps = 1e-9
    cm = confusion_matrix(all_labels, all_preds, labels=[0, 1])

    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)

    fall_recall = tp / (tp + fn + eps)
    fall_precision = tp / (tp + fp + eps)
    normal_recall = tn / (tn + fp + eps)
    fall_f1 = f1_score(all_labels, all_preds, pos_label=1, zero_division=0)
    macro_f1 = f1_score(all_labels, all_preds, average="macro", zero_division=0)

    return {
        "fall_recall": float(fall_recall),
        "fall_precision": float(fall_precision),
        "normal_recall": float(normal_recall),
        "fall_f1": float(fall_f1),
        "macro_f1": float(macro_f1),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
    }


# ─── Trainer ─────────────────────────────────────────────────────────────────

class FallExpertTrainer:
    """
    Training loop for FallExpertCNN.

    Epoch flow:
      1. Forward pass → BCEWithLogitsLoss
      2. Compute validation metrics
      3. Check collapse → reject checkpoint if collapsed
      4. Save best_model.pt only if checkpoint_valid=True
      5. Always save last_model.pt
      6. Early stopping on fall_application_score
    """

    def __init__(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
        device: torch.device,
        out_dir: Path,
    ) -> None:
        self.model = model.to(device)
        self.device = device
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

        train_cfg = cfg.get("training", {})
        self.epochs = train_cfg.get("epochs", 30)
        self.grad_clip = train_cfg.get("gradient_clip", 1.0)
        self.patience = train_cfg.get("early_stopping_patience", 10)
        self.threshold = train_cfg.get("fall_threshold", 0.5)

        # mild positive class weight (fall=1) — NOT aggressive
        pos_weight_val = cfg.get("pos_weight", 2.0)
        pos_weight = torch.tensor([pos_weight_val], device=device)
        self.criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

        opt_cfg = cfg.get("optimizer", {})
        self.optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=opt_cfg.get("lr", 1e-3),
            weight_decay=opt_cfg.get("weight_decay", 1e-4),
        )

        sched_cfg = cfg.get("scheduler", {})
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer,
            T_max=self.epochs,
            eta_min=sched_cfg.get("eta_min", 1e-5),
        )

        self.best_score: float = -1.0
        self.patience_counter: int = 0
        self.history: list[Dict[str, Any]] = []

    # ── training epoch ────────────────────────────────────────────────────────
    def _train_epoch(self, loader: DataLoader) -> float:
        self.model.train()
        total_loss = 0.0
        for batch in loader:
            x, y = batch
            x = x.to(self.device, dtype=torch.float32)
            y = y.to(self.device, dtype=torch.float32)

            self.optimizer.zero_grad()
            out = self.model(x)
            loss = self.criterion(out["logit"], y)
            loss.backward()

            if self.grad_clip > 0:
                nn.utils.clip_grad_norm_(self.model.parameters(), self.grad_clip)
            self.optimizer.step()
            total_loss += loss.item()

        return total_loss / max(len(loader), 1)

    # ── validation epoch ──────────────────────────────────────────────────────
    def _val_epoch(
        self, loader: DataLoader
    ) -> Tuple[float, Dict[str, float], Dict[int, int]]:
        self.model.eval()
        total_loss = 0.0
        all_labels: list[int] = []
        all_preds: list[int] = []

        with torch.no_grad():
            for batch in loader:
                x, y = batch
                x = x.to(self.device, dtype=torch.float32)
                y = y.to(self.device, dtype=torch.float32)

                out = self.model(x)
                loss = self.criterion(out["logit"], y)
                total_loss += loss.item()

                preds = (out["fall_prob"] >= self.threshold).long().cpu().numpy()
                all_labels.extend(y.long().cpu().numpy().tolist())
                all_preds.extend(preds.tolist())

        metrics = compute_binary_metrics(
            np.array(all_labels), np.array(all_preds)
        )
        pred_counts: Dict[int, int] = {}
        for p in all_preds:
            pred_counts[p] = pred_counts.get(p, 0) + 1

        return total_loss / max(len(loader), 1), metrics, pred_counts

    # ── checkpoint save ───────────────────────────────────────────────────────
    def _save_checkpoint(
        self, epoch: int, metrics: Dict[str, float], is_best: bool
    ) -> None:
        state = {
            "epoch": epoch,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "metrics": metrics,
        }
        # Always save last_model.pt
        torch.save(state, self.out_dir / "last_model.pt")
        # Save best_model.pt ONLY if this is a valid best
        if is_best:
            torch.save(state, self.out_dir / "best_model.pt")
            log.info(f"  [CHECKPOINT] best_model.pt saved (epoch={epoch})")

    # ── main training loop ────────────────────────────────────────────────────
    def fit(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
    ) -> list[Dict[str, Any]]:
        log.info(f"FallExpertTrainer.fit() — {self.epochs} epochs max")

        best_app_score_for_patience: float = -1.0  # track improvement for early stopping

        for epoch in range(1, self.epochs + 1):
            train_loss = self._train_epoch(train_loader)
            val_loss, val_metrics, pred_counts = self._val_epoch(val_loader)
            self.scheduler.step()

            collapsed, collapse_reason = is_collapse(val_metrics, pred_counts)
            app_score = fall_application_score(val_metrics)
            checkpoint_valid = not collapsed and app_score > 0.0

            is_best = checkpoint_valid and app_score > self.best_score
            if is_best:
                self.best_score = app_score

            entry: Dict[str, Any] = {
                "epoch": epoch,
                "train_loss": round(train_loss, 5),
                "val_loss": round(val_loss, 5),
                "fall_application_score": round(app_score, 5),
                "checkpoint_valid": checkpoint_valid,
                "collapse_detected": collapsed,
                "collapse_reason": collapse_reason if collapsed else "",
                "is_best": is_best,
                "pred_distribution": pred_counts,
                **{k: round(v, 5) for k, v in val_metrics.items()},
            }
            self.history.append(entry)

            status = "BEST" if is_best else ("COLLAPSE" if collapsed else "ok")
            log.info(
                f"Epoch {epoch:03d}/{self.epochs} "
                f"| train_loss={train_loss:.4f} val_loss={val_loss:.4f} "
                f"| app_score={app_score:.4f} "
                f"| fall_recall={val_metrics.get('fall_recall', 0):.3f} "
                f"normal_recall={val_metrics.get('normal_recall', 0):.3f} "
                f"| [{status}]"
            )

            if collapsed:
                log.warning(f"  Collapse: {collapse_reason}")

            self._save_checkpoint(epoch, val_metrics, is_best)

            # Early stopping: track app_score improvement regardless of collapse.
            # This prevents premature stopping when the model is still learning
            # but hasn't yet cleared all collapse thresholds.
            if app_score > best_app_score_for_patience:
                best_app_score_for_patience = app_score
                self.patience_counter = 0
            else:
                self.patience_counter += 1

            if self.patience_counter >= self.patience:
                log.info(f"Early stopping at epoch {epoch} (no app_score improvement for {self.patience} epochs)")
                break

        # Save training history
        with open(self.out_dir / "training_history.json", "w") as f:
            json.dump(self.history, f, indent=2)
        log.info(f"Training history → {self.out_dir / 'training_history.json'}")

        return self.history
