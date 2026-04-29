"""Main training loop for HealthAlert multi-task model."""

import logging
import time
from typing import Dict, Optional, Tuple

import numpy as np
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from src.training.losses import MultiTaskLoss
from src.training.metrics import compute_all_metrics
from src.training.optim import build_optimizer, build_scheduler
from src.training.callbacks import EarlyStopping, ModelCheckpoint

logger = logging.getLogger("healthalert.training.trainer")


class Trainer:
    """Multi-task trainer for HealthAlert model."""

    def __init__(
        self,
        model: torch.nn.Module,
        cfg,
        device: torch.device,
    ):
        self.model = model.to(device)
        self.device = device
        self.cfg = cfg

        # Loss
        loss_cfg = cfg.get("loss", {})
        self.criterion = MultiTaskLoss(loss_cfg)

        # Optimizer & scheduler
        self.optimizer = build_optimizer(model, cfg.get("optimizer", {}))
        self.scheduler = build_scheduler(self.optimizer, cfg.get("scheduler", {}))

        # Callbacks
        train_cfg = cfg.get("training", {})
        self.early_stopping = EarlyStopping(
            patience=train_cfg.get("early_stopping_patience", 15),
            mode="max",
        )
        self.checkpoint = ModelCheckpoint(
            save_dir=cfg.get("paths", {}).get("model_dir", "outputs/models"),
            metric_name=train_cfg.get("save_best_metric", "fall_f1"),
        )

        self.gradient_clip = train_cfg.get("gradient_clip", 1.0)
        self.epochs = train_cfg.get("epochs", 100)

    def train_epoch(self, dataloader: DataLoader) -> Dict[str, float]:
        """Train for one epoch."""
        self.model.train()
        total_loss = 0
        loss_components = {}
        n_batches = 0

        for batch in tqdm(dataloader, desc="Training", leave=False):
            # Move to device
            batch = {k: v.to(self.device) if isinstance(v, torch.Tensor) else v
                     for k, v in batch.items()}

            self.optimizer.zero_grad()

            outputs = self.model(batch)

            targets = {
                "fall_label": batch["fall_label"],
                "instability_label": batch["instability_label"],
                "quality_label": batch["quality_label"],
                "risk_label": batch["risk_label"],
            }

            loss, losses = self.criterion(outputs, targets)

            loss.backward()

            if self.gradient_clip > 0:
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.gradient_clip
                )

            self.optimizer.step()

            total_loss += loss.item()
            for k, v in losses.items():
                loss_components[k] = loss_components.get(k, 0) + v.item()
            n_batches += 1

        avg_losses = {k: v / max(n_batches, 1) for k, v in loss_components.items()}
        avg_losses["total_avg"] = total_loss / max(n_batches, 1)
        return avg_losses

    @torch.no_grad()
    def evaluate(self, dataloader: DataLoader) -> Tuple[Dict[str, float], Dict[str, float]]:
        """Evaluate on validation/test set."""
        self.model.eval()
        all_outputs = {"fall": [], "instability": [], "quality": [], "risk": []}
        all_targets = {"fall": [], "instability": [], "quality": [], "risk": []}
        total_loss = 0
        n_batches = 0

        for batch in tqdm(dataloader, desc="Evaluating", leave=False):
            batch = {k: v.to(self.device) if isinstance(v, torch.Tensor) else v
                     for k, v in batch.items()}

            outputs = self.model(batch)
            targets = {
                "fall_label": batch["fall_label"],
                "instability_label": batch["instability_label"],
                "quality_label": batch["quality_label"],
                "risk_label": batch["risk_label"],
            }

            loss, _ = self.criterion(outputs, targets)
            total_loss += loss.item()
            n_batches += 1

            # Collect predictions
            all_outputs["fall"].append(torch.sigmoid(outputs["fall_logit"]).cpu().numpy())
            all_outputs["instability"].append(torch.sigmoid(outputs["instability_logit"]).cpu().numpy())
            all_outputs["quality"].append(torch.sigmoid(outputs["quality_logit"]).cpu().numpy())
            all_outputs["risk"].append(outputs["risk_score"].cpu().numpy())

            all_targets["fall"].append(batch["fall_label"].cpu().numpy())
            all_targets["instability"].append(batch["instability_label"].cpu().numpy())
            all_targets["quality"].append(batch["quality_label"].cpu().numpy())
            all_targets["risk"].append(batch["risk_label"].cpu().numpy())

        # Concatenate
        for k in all_outputs:
            all_outputs[k] = np.concatenate(all_outputs[k])
            all_targets[k] = np.concatenate(all_targets[k])

        metrics = compute_all_metrics(all_outputs, all_targets)
        metrics["val_loss"] = total_loss / max(n_batches, 1)

        return metrics, {"outputs": all_outputs, "targets": all_targets}

    def fit(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
    ) -> Dict[str, float]:
        """Full training loop."""
        logger.info(f"Starting training for {self.epochs} epochs")
        logger.info(f"Model parameters: {self.model.count_parameters():,}")

        best_metrics = {}

        for epoch in range(1, self.epochs + 1):
            t0 = time.time()

            # Train
            train_losses = self.train_epoch(train_loader)

            # Validate
            val_metrics, _ = self.evaluate(val_loader)

            # Scheduler step
            if self.scheduler is not None:
                if isinstance(self.scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau):
                    self.scheduler.step(val_metrics.get("fall_f1", 0))
                else:
                    self.scheduler.step()

            elapsed = time.time() - t0
            lr = self.optimizer.param_groups[0]["lr"]

            logger.info(
                f"Epoch {epoch:3d}/{self.epochs} | "
                f"loss={train_losses['total_avg']:.4f} | "
                f"val_fall_f1={val_metrics.get('fall_f1', 0):.4f} | "
                f"val_fall_auc={val_metrics.get('fall_auc', 0):.4f} | "
                f"lr={lr:.6f} | {elapsed:.1f}s"
            )

            # Checkpoint
            saved = self.checkpoint(val_metrics, self.model, self.optimizer, epoch)
            if saved:
                best_metrics = val_metrics.copy()

            # Early stopping
            monitor = val_metrics.get("fall_f1", 0)
            if self.early_stopping(monitor):
                break

        logger.info("Training complete")
        return best_metrics
