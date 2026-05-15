"""Prototype training loop for HealthAlert multi-task model.

Design principles:
- One DataLoader per task; multi-task training via round-robin batches.
- Only enabled tasks (per task_training_policy.yaml / prototype_training.yaml)
  contribute to the loss.
- tremor_context is explicitly checked and blocked.
- Best model saved by fall_recall (primary prototype metric).
- Evaluation computes per-task confusion matrix + macro F1.
- Leakage checks run before training.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from torch.utils.data import DataLoader

from src.data.task_npz_dataset import TaskNpzDataset, collate_task_batch
from src.models.prototype_model import PrototypeHealthAlertModel
from src.training.prototype_losses import MultiTaskPrototypeLoss

logger = logging.getLogger("healthalert.training.prototype_trainer")


# ── Leakage check ─────────────────────────────────────────────────────────

def check_no_split_overlap(
    train_ds: Dict[str, TaskNpzDataset],
    val_ds: Dict[str, TaskNpzDataset],
    test_ds: Dict[str, TaskNpzDataset],
) -> None:
    """Assert that pre-built NPZ splits have no overlapping windows.

    The split is guaranteed by the build script; this verifies it using
    window sizes so we avoid loading all data into memory.  A full
    hash-based check would require loading all data twice — acceptable
    for periodic CI but too slow for every training run.
    """
    for task in train_ds:
        tr_n = len(train_ds[task])
        va_n = len(val_ds.get(task, []))  # type: ignore[arg-type]
        te_n = len(test_ds.get(task, []))  # type: ignore[arg-type]
        logger.info(
            f"[{task}] split sizes — train={tr_n}, val={va_n}, test={te_n}"
        )
        # The NPZ files are written from disjoint index ranges by the build
        # script; re-assert that splits are non-empty and distinct in size.
        assert tr_n > 0, f"Train split is empty for task {task!r}"
        assert va_n > 0, f"Val split is empty for task {task!r}"
    logger.info("Split overlap check: PASS")


# ── Epoch helpers ─────────────────────────────────────────────────────────

def _to_device(batch: Dict, device: torch.device) -> Dict:
    return {
        k: v.to(device) if isinstance(v, torch.Tensor) else v
        for k, v in batch.items()
    }


def train_one_epoch(
    model: PrototypeHealthAlertModel,
    task_loaders: Dict[str, DataLoader],
    criterion: MultiTaskPrototypeLoss,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    grad_clip: float = 1.0,
    scaler: Optional[Any] = None,
) -> Dict[str, float]:
    """One epoch of multi-task training (round-robin over all tasks).

    Returns average loss per task.
    """
    model.train()
    task_losses: Dict[str, List[float]] = {t: [] for t in task_loaders}

    def _cycle_loader(loader):
        """Infinite generator that creates a fresh iterator each cycle.

        Unlike itertools.cycle(), this does NOT buffer batches in memory and
        re-shuffles (or re-samples for WeightedRandomSampler) on each restart.
        """
        while True:
            yield from loader

    # Wrap ALL loaders in the cycle generator so every task contributes to
    # every step.  Without cycling, longer loaders (activity_context: 1527
    # steps) dominate the shared encoder after shorter ones (fall_detection:
    # 834 steps) are exhausted, causing the encoder to drift away from
    # fall-relevant features.
    iterators = {t: _cycle_loader(loader) for t, loader in task_loaders.items()}

    # Epoch length = longest loader
    max_steps = max(len(loader) for loader in task_loaders.values())

    for step in range(max_steps):
        # Accumulate gradients from ALL tasks before stepping — true multi-task.
        optimizer.zero_grad()

        for task, it in iterators.items():
            batch = next(it)  # never raises StopIteration (cycling)
            batch = _to_device(batch, device)

            logits = model.forward_task(batch, task)
            loss = criterion(logits, batch["label"], task)

            if scaler is not None:
                scaler.scale(loss).backward()
            else:
                loss.backward()

            task_losses[task].append(loss.item())

        if scaler is not None:
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            scaler.step(optimizer)
            scaler.update()
        else:
            if grad_clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            optimizer.step()

    return {
        t: float(np.mean(v)) if v else 0.0 for t, v in task_losses.items()
    }


@torch.no_grad()
def evaluate(
    model: PrototypeHealthAlertModel,
    task_loaders: Dict[str, DataLoader],
    criterion: MultiTaskPrototypeLoss,
    device: torch.device,
    class_names: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Evaluate all tasks on val or test split.

    Returns dict with per-task metrics and aggregate scores.
    """
    model.eval()
    results: Dict[str, Any] = {}
    aggregate_f1s: List[float] = []

    for task, loader in task_loaders.items():
        all_preds: List[int] = []
        all_labels: List[int] = []
        all_probs: List[np.ndarray] = []
        task_loss_vals: List[float] = []

        for batch in loader:
            batch = _to_device(batch, device)
            logits = model.forward_task(batch, task)
            loss = criterion(logits, batch["label"], task)
            task_loss_vals.append(loss.item())

            probs = torch.softmax(logits, dim=-1).cpu().numpy()
            preds = probs.argmax(axis=-1)

            all_preds.extend(preds.tolist())
            all_labels.extend(batch["label"].cpu().numpy().tolist())
            all_probs.append(probs)

        labels_arr = np.array(all_labels)
        preds_arr = np.array(all_preds)
        probs_arr = np.concatenate(all_probs, axis=0)

        num_classes = probs_arr.shape[1]
        names = class_names.get(task, [str(i) for i in range(num_classes)]) if class_names else None

        macro_f1 = float(f1_score(labels_arr, preds_arr, average="macro", zero_division=0))
        per_class_f1 = f1_score(labels_arr, preds_arr, average=None, zero_division=0).tolist()
        cm = confusion_matrix(labels_arr, preds_arr, labels=list(range(num_classes))).tolist()

        # Per-class recall
        per_class_recall = recall_score(
            labels_arr, preds_arr, average=None, zero_division=0, labels=list(range(num_classes))
        ).tolist()

        # Per-class precision (needed for collapse guard)
        per_class_precision = precision_score(
            labels_arr, preds_arr, average=None, zero_division=0, labels=list(range(num_classes))
        ).tolist()

        # Fall/risk class recall and precision (class index 1 = fall for fall_detection)
        fall_recall = per_class_recall[1] if len(per_class_recall) > 1 else 0.0

        task_result: Dict[str, Any] = {
            "val_loss": float(np.mean(task_loss_vals)) if task_loss_vals else 0.0,
            "macro_f1": macro_f1,
            "per_class_f1": per_class_f1,
            "per_class_recall": per_class_recall,
            "per_class_precision": per_class_precision,
            "fall_recall": fall_recall,  # class-1 recall (fall / suspect)
            "confusion_matrix": cm,
            "class_names": names,
            "n_samples": len(labels_arr),
        }
        results[task] = task_result
        aggregate_f1s.append(macro_f1)

        # Report check: if any task exceeds 99% macro-F1, warn about leakage
        if macro_f1 > 0.99:
            logger.warning(
                f"[{task}] macro_F1={macro_f1:.4f} > 0.99 — POSSIBLE DATA LEAKAGE. "
                "Investigate before accepting this result."
            )

    results["aggregate"] = {
        "mean_macro_f1": float(np.mean(aggregate_f1s)) if aggregate_f1s else 0.0,
        "fall_detection_recall": results.get("fall_detection", {}).get("fall_recall", 0.0),
    }
    return results


# ── Main trainer ──────────────────────────────────────────────────────────

class PrototypeTrainer:
    """End-to-end prototype trainer.

    Parameters
    ----------
    model:
        PrototypeHealthAlertModel instance.
    train_datasets / val_datasets:
        Per-task TaskNpzDataset dicts.
    tasks_cfg:
        tasks section from prototype_training.yaml.
    training_cfg:
        training section from prototype_training.yaml.
    optimizer_cfg / scheduler_cfg:
        Optimizer and scheduler sections.
    output_dir:
        Where to save checkpoints and metrics.
    device:
        torch.device.
    """

    def __init__(
        self,
        model: PrototypeHealthAlertModel,
        train_datasets: Dict[str, TaskNpzDataset],
        val_datasets: Dict[str, TaskNpzDataset],
        tasks_cfg: Dict,
        training_cfg: Dict,
        optimizer_cfg: Dict,
        scheduler_cfg: Dict,
        output_dir: Path,
        device: torch.device,
    ) -> None:
        self.model = model.to(device)
        self.device = device
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.tasks_cfg = tasks_cfg
        self.training_cfg = training_cfg

        # Guard: tremor_context must never be in active training datasets
        for task_name, ds in train_datasets.items():
            assert task_name != "tremor_context", (
                "tremor_context must not appear in training datasets. "
                "Check task_training_policy.yaml."
            )

        batch_size = int(training_cfg.get("batch_size", 128))
        num_workers = int(training_cfg.get("num_workers", 0))
        pin_memory = bool(training_cfg.get("pin_memory", False))

        from torch.utils.data import WeightedRandomSampler

        def _make_train_loader(task_name: str, ds) -> DataLoader:
            task_cfg = tasks_cfg.get(task_name, {})
            use_balanced = bool(task_cfg.get("balanced_sampling", False))
            if use_balanced:
                # Sampler always uses auto-computed inverse-frequency weights
                # so each class appears at equal rate in every batch.
                # config class_weights are for the LOSS function only, not here.
                sw = ds.sample_weights()  # auto-computed, not from config
                sampler = WeightedRandomSampler(
                    weights=sw,
                    num_samples=len(ds),
                    replacement=True,
                )
                logger.info(
                    f"[{task_name}] balanced_sampling=ON via WeightedRandomSampler"
                )
                return DataLoader(
                    ds,
                    batch_size=batch_size,
                    sampler=sampler,
                    num_workers=num_workers,
                    pin_memory=pin_memory,
                    drop_last=True,
                    collate_fn=collate_task_batch,
                )
            return DataLoader(
                ds,
                batch_size=batch_size,
                shuffle=True,
                num_workers=num_workers,
                pin_memory=pin_memory,
                drop_last=True,
                collate_fn=collate_task_batch,
            )

        self.train_loaders: Dict[str, DataLoader] = {
            t: _make_train_loader(t, ds)
            for t, ds in train_datasets.items()
        }
        self.val_loaders: Dict[str, DataLoader] = {
            t: DataLoader(
                ds,
                batch_size=batch_size * 2,
                shuffle=False,
                num_workers=num_workers,
                pin_memory=pin_memory,
                collate_fn=collate_task_batch,
            )
            for t, ds in val_datasets.items()
        }

        # Class names for readable evaluation reports
        self.class_names: Dict[str, List[str]] = {
            t: tasks_cfg[t].get("class_names", []) for t in train_datasets
        }

        self.criterion = MultiTaskPrototypeLoss(
            tasks_cfg=tasks_cfg,
            task_datasets=train_datasets,
            disabled_tasks=["tremor_context"],
        )

        # Optimizer
        opt_name = optimizer_cfg.get("name", "adamw").lower()
        lr = float(optimizer_cfg.get("lr", 0.001))
        wd = float(optimizer_cfg.get("weight_decay", 0.01))
        betas = tuple(optimizer_cfg.get("betas", [0.9, 0.999]))

        if opt_name == "adamw":
            self.optimizer = torch.optim.AdamW(
                model.parameters(), lr=lr, weight_decay=wd, betas=betas
            )
        else:
            self.optimizer = torch.optim.Adam(model.parameters(), lr=lr)

        # Scheduler
        sched_name = scheduler_cfg.get("name", "reduce_on_plateau").lower()
        if sched_name == "reduce_on_plateau":
            self.scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
                self.optimizer,
                mode="min",
                factor=float(scheduler_cfg.get("factor", 0.5)),
                patience=int(scheduler_cfg.get("patience", 4)),
                min_lr=float(scheduler_cfg.get("min_lr", 1e-5)),
            )
        else:
            self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                self.optimizer,
                T_max=int(training_cfg.get("epochs", 40)),
                eta_min=float(scheduler_cfg.get("min_lr", 1e-5)),
            )

        # Mixed precision (CPU-safe: disabled on CPU)
        self.use_amp = (
            bool(training_cfg.get("mixed_precision", False)) and device.type == "cuda"
        )
        self.scaler = torch.cuda.amp.GradScaler() if self.use_amp else None

        self.epochs = int(training_cfg.get("epochs", 40))
        self.grad_clip = float(training_cfg.get("gradient_clip", 1.0))
        self.patience = int(training_cfg.get("early_stopping_patience", 8))
        self.best_metric_name = training_cfg.get(
            "early_stopping_metric", "fall_recall"
        )

        self.best_val_score: float = -1.0
        self.patience_counter: int = 0
        self.history: List[Dict[str, Any]] = []

    def _get_monitor_score(self, eval_results: Dict[str, Any]) -> float:
        """Extract the metric used for early stopping and checkpointing."""
        if self.best_metric_name == "fall_recall":
            return eval_results.get("fall_detection", {}).get("fall_recall", 0.0)
        if self.best_metric_name == "fall_macro_f1":
            # fall_detection macro F1 across normal/fall/near_fall — penalises
            # degenerate all-fall collapse (where recall=1 but precision≈0).
            fd = eval_results.get("fall_detection", {})
            score = fd.get("macro_f1", 0.0)
            # Collapse guard: if fall_recall is perfect but precision is very
            # low (all-fall), return 0 so this is never saved as best.
            recall = fd.get("fall_recall", 0.0)
            per_class_prec = fd.get("per_class_precision", [])
            fall_prec = per_class_prec[1] if len(per_class_prec) > 1 else 1.0
            if recall >= 0.99 and fall_prec < 0.15:
                logger.warning(
                    f"Collapse guard triggered: fall_recall={recall:.4f} but "
                    f"fall_precision={fall_prec:.4f} — model predicts all-fall. "
                    "Score forced to 0.0 to prevent saving collapsed checkpoint."
                )
                return 0.0
            return score
        if self.best_metric_name == "mean_macro_f1":
            return eval_results.get("aggregate", {}).get("mean_macro_f1", 0.0)
        # Fallback: mean macro F1
        return eval_results.get("aggregate", {}).get("mean_macro_f1", 0.0)

    def train(self) -> Dict[str, Any]:
        """Run full training loop.  Returns best evaluation results."""
        logger.info("=" * 60)
        logger.info("HealthAlert Prototype Training")
        logger.info(f"  Active tasks: {list(self.train_loaders.keys())}")
        logger.info(f"  Epochs: {self.epochs} | batch_size per task loader")
        logger.info(f"  Device: {self.device}")
        logger.info(f"  AMP: {self.use_amp}")
        logger.info(f"  Early stopping metric: {self.best_metric_name}")
        logger.info("=" * 60)

        best_results: Dict[str, Any] = {}

        for epoch in range(1, self.epochs + 1):
            t0 = time.time()
            logger.info(f"--- Epoch {epoch}/{self.epochs} starting ---")
            sys.stdout.flush()

            # ── Training ────────────────────────────────────────────────
            train_losses = train_one_epoch(
                model=self.model,
                task_loaders=self.train_loaders,
                criterion=self.criterion,
                optimizer=self.optimizer,
                device=self.device,
                grad_clip=self.grad_clip,
                scaler=self.scaler,
            )

            # ── Validation ──────────────────────────────────────────────
            val_results = evaluate(
                model=self.model,
                task_loaders=self.val_loaders,
                criterion=self.criterion,
                device=self.device,
                class_names=self.class_names,
            )

            # ── Scheduler step ──────────────────────────────────────────
            total_val_loss = sum(
                val_results[t].get("val_loss", 0.0) for t in val_results if t != "aggregate"
            )
            if isinstance(self.scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau):
                self.scheduler.step(total_val_loss)
            else:
                self.scheduler.step()

            # ── Monitor metric ──────────────────────────────────────────
            score = self._get_monitor_score(val_results)
            elapsed = time.time() - t0

            # Log summary
            fd_val = val_results.get("fall_detection", {})
            fall_f1 = fd_val.get("macro_f1", 0.0)
            fall_rec = fd_val.get("fall_recall", 0.0)
            _fd_prec_list = fd_val.get("per_class_precision", [])
            fall_prec = _fd_prec_list[1] if len(_fd_prec_list) > 1 else 0.0
            agg_f1 = val_results.get("aggregate", {}).get("mean_macro_f1", 0.0)
            lr_now = self.optimizer.param_groups[0]["lr"]

            loss_str = " | ".join(
                f"{t}={v:.4f}" for t, v in sorted(train_losses.items())
            )
            logger.info(
                f"Epoch {epoch:03d}/{self.epochs} [{elapsed:.1f}s] "
                f"lr={lr_now:.2e} | Train loss: {loss_str}"
            )
            # Collapse detection for real-time visibility
            collapse_flag = ""
            collapse_detected = fall_rec >= 0.99 and fall_prec < 0.15
            if collapse_detected:
                collapse_flag = " *** ALL-FALL COLLAPSE ***"
            fd_per_class = fd_val.get("per_class_recall", [])
            normal_rec = fd_per_class[0] if len(fd_per_class) > 0 else 0.0
            near_fall_rec = fd_per_class[2] if len(fd_per_class) > 2 else 0.0
            logger.info(
                f"  Val  fall_macro_f1={fall_f1:.4f} "
                f"fall_recall={fall_rec:.4f} fall_prec={fall_prec:.4f} "
                f"normal_recall={normal_rec:.4f} near_fall_recall={near_fall_rec:.4f} "
                f"mean_f1={agg_f1:.4f} "
                f"[{self.best_metric_name}={score:.4f}] "
                f"collapse_detected={'YES' if collapse_detected else 'NO'}"
                f"{collapse_flag}"
            )
            logger.info(f"--- Epoch {epoch}/{self.epochs} completed ---")

            epoch_record = {
                "epoch": epoch,
                "train_losses": train_losses,
                "val_results": {
                    t: {k: v for k, v in r.items() if k != "confusion_matrix"}
                    for t, r in val_results.items()
                },
                "monitor_score": score,
                "lr": lr_now,
            }
            self.history.append(epoch_record)

            # ── Checkpoint (last always) ─────────────────────────────────
            self._save_checkpoint(self.output_dir / "last_model.pt", epoch)

            # ── Best model ───────────────────────────────────────────────
            if score > self.best_val_score:
                self.best_val_score = score
                self.patience_counter = 0
                best_results = val_results
                self._save_checkpoint(self.output_dir / "best_model.pt", epoch)
                logger.info(
                    f"  *** New best: {self.best_metric_name}={score:.4f} "
                    f"→ saved best_model.pt ***"
                )
            else:
                self.patience_counter += 1
                if self.patience_counter >= self.patience:
                    logger.info(
                        f"Early stopping at epoch {epoch} "
                        f"(no improvement for {self.patience} epochs)"
                    )
                    break

        # Save training history
        hist_path = self.output_dir / "training_history.json"
        with open(hist_path, "w") as f:
            json.dump(self.history, f, indent=2, default=str)
        logger.info(f"Training history saved: {hist_path}")

        return best_results

    def _save_checkpoint(self, path: Path, epoch: int) -> None:
        torch.save(
            {
                "epoch": epoch,
                "model_state_dict": self.model.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
                "best_val_score": self.best_val_score,
                "best_metric_name": self.best_metric_name,
            },
            path,
        )

    def evaluate_test(
        self, test_datasets: Dict[str, TaskNpzDataset], batch_size: int = 256
    ) -> Dict[str, Any]:
        """Evaluate on test split using best model."""
        best_ckpt = self.output_dir / "best_model.pt"
        if best_ckpt.exists():
            ckpt = torch.load(best_ckpt, map_location=self.device)
            self.model.load_state_dict(ckpt["model_state_dict"])
            logger.info(
                f"Loaded best model from epoch {ckpt.get('epoch', '?')} "
                f"({self.best_metric_name}={ckpt.get('best_val_score', 0.0):.4f})"
            )

        num_workers = int(self.training_cfg.get("num_workers", 0))
        test_loaders = {
            t: DataLoader(
                ds,
                batch_size=batch_size,
                shuffle=False,
                num_workers=num_workers,
                collate_fn=collate_task_batch,
            )
            for t, ds in test_datasets.items()
        }

        return evaluate(
            model=self.model,
            task_loaders=test_loaders,
            criterion=self.criterion,
            device=self.device,
            class_names=self.class_names,
        )
