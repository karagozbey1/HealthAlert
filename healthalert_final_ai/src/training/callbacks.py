"""Training callbacks for early stopping and checkpointing."""

import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("healthalert.training.callbacks")


class EarlyStopping:
    """Early stopping to prevent overfitting."""

    def __init__(self, patience: int = 15, mode: str = "max", min_delta: float = 1e-4):
        self.patience = patience
        self.mode = mode
        self.min_delta = min_delta
        self.counter = 0
        self.best_score = None
        self.should_stop = False

    def __call__(self, score: float) -> bool:
        if self.best_score is None:
            self.best_score = score
            return False

        if self.mode == "max":
            improved = score > self.best_score + self.min_delta
        else:
            improved = score < self.best_score - self.min_delta

        if improved:
            self.best_score = score
            self.counter = 0
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.should_stop = True
                logger.info(f"Early stopping triggered after {self.counter} epochs without improvement")
                return True

        return False


class ModelCheckpoint:
    """Save best model based on monitored metric."""

    def __init__(
        self,
        save_dir: str,
        metric_name: str = "val_f1_fall",
        mode: str = "max",
    ):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.metric_name = metric_name
        self.mode = mode
        self.best_score = None

    def __call__(self, metrics: Dict, model, optimizer, epoch: int) -> bool:
        """Check if current metrics are best and save if so."""
        import torch

        score = metrics.get(self.metric_name, 0)

        if self.best_score is None:
            is_best = True
        elif self.mode == "max":
            is_best = score > self.best_score
        else:
            is_best = score < self.best_score

        if is_best:
            self.best_score = score
            path = self.save_dir / "best_model.pt"
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "metrics": metrics,
                "best_score": self.best_score,
            }, str(path))
            logger.info(f"New best model saved: {self.metric_name}={score:.4f}")
            return True

        return False
