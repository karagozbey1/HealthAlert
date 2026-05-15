"""Prototype task-specific losses for HealthAlert.

Two strategies available per task:
1. focal_ce  — Focal cross-entropy (down-weights easy negatives, great for
               imbalanced multi-class like fall_detection)
2. weighted_ce — Standard cross-entropy with per-class inverse-frequency
                weights (default for other tasks)

The MultiTaskPrototypeLoss routes each batch to the correct task loss and
applies the task-specific loss_weight scaling.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F


class FocalCrossEntropyLoss(nn.Module):
    """Multi-class focal cross-entropy.

    References: Lin et al. 2017 (Focal Loss for Dense Object Detection)
    Adapted for multi-class with per-class weighting.

    Parameters
    ----------
    gamma:
        Focusing parameter.  Higher = more focus on hard examples.
    class_weights:
        Per-class weight tensor (device-matched at forward time).
    """

    def __init__(
        self,
        gamma: float = 2.0,
        class_weights: Optional[torch.Tensor] = None,
    ) -> None:
        super().__init__()
        self.gamma = gamma
        self.register_buffer("class_weights", class_weights)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        weights = self.class_weights
        if weights is not None:
            weights = weights.to(logits.device)

        ce = F.cross_entropy(logits, targets, weight=weights, reduction="none")
        probs = F.softmax(logits, dim=-1)
        pt = probs.gather(1, targets.unsqueeze(1)).squeeze(1)
        focal_weight = (1.0 - pt) ** self.gamma
        return (focal_weight * ce).mean()


class WeightedCELoss(nn.Module):
    """Standard cross-entropy with optional per-class weights."""

    def __init__(self, class_weights: Optional[torch.Tensor] = None) -> None:
        super().__init__()
        self.register_buffer("class_weights", class_weights)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        weights = self.class_weights
        if weights is not None:
            weights = weights.to(logits.device)
        return F.cross_entropy(logits, targets, weight=weights)


class MultiTaskPrototypeLoss(nn.Module):
    """Routes batches to per-task loss and applies task weight scaling.

    Parameters
    ----------
    tasks_cfg:
        Dict of task_name → task config dict (from prototype_training.yaml).
    task_datasets:
        Dict of task_name → TaskNpzDataset (to read class_weights from).
    disabled_tasks:
        Tasks that must not contribute to the loss (e.g. tremor_context).
    """

    def __init__(
        self,
        tasks_cfg: Dict,
        task_datasets: Dict,
        disabled_tasks: Optional[List[str]] = None,
    ) -> None:
        super().__init__()
        self.disabled_tasks = set(disabled_tasks or [])
        self._losses: Dict[str, nn.Module] = {}
        self._task_weights: Dict[str, float] = {}

        for task_name, cfg in tasks_cfg.items():
            if not cfg.get("enabled", True):
                continue  # skip disabled tasks

            ds = task_datasets.get(task_name)

            # Use manually specified weights from config if present; otherwise
            # fall back to dataset-computed inverse-frequency weights.
            manual_weights = cfg.get("class_weights", None)
            if manual_weights is not None:
                import torch as _torch
                cw = _torch.tensor(manual_weights, dtype=_torch.float32)
            else:
                cw = ds.class_weight_tensor() if ds is not None else None

            loss_type = cfg.get("loss_type", "weighted_ce")
            if loss_type == "focal_ce":
                self._losses[task_name] = FocalCrossEntropyLoss(
                    gamma=float(cfg.get("focal_gamma", 2.0)),
                    class_weights=cw,
                )
            else:
                self._losses[task_name] = WeightedCELoss(class_weights=cw)

            self._task_weights[task_name] = float(cfg.get("loss_weight", 1.0))

        # Log resolved loss weights for each task
        import logging as _logging
        _loss_logger = _logging.getLogger("healthalert.training.prototype_losses")
        for task_name, loss_fn in self._losses.items():
            cw_buf = getattr(loss_fn, "class_weights", None)
            if cw_buf is not None:
                cw_list = cw_buf.tolist()
                cw_str = ", ".join(f"class{i}={w:.4f}" for i, w in enumerate(cw_list))
            else:
                cw_str = "auto (dataset-computed)"
            _loss_logger.info(
                f"[{task_name}] loss_type={type(loss_fn).__name__} "
                f"task_weight={self._task_weights[task_name]:.2f} "
                f"class_weights=[{cw_str}]"
            )

        # Register as ModuleDict so parameters are tracked (buffers)
        self.loss_fns = nn.ModuleDict(self._losses)

    def forward(
        self, logits: torch.Tensor, targets: torch.Tensor, task: str
    ) -> torch.Tensor:
        """Compute weighted task loss.

        Parameters
        ----------
        logits:  (B, num_classes) raw model output for this task.
        targets: (B,)  class indices.
        task:    task name string.

        Returns
        -------
        Scalar loss tensor.
        """
        if task in self.disabled_tasks:
            raise RuntimeError(
                f"Task '{task}' is disabled — must not contribute to training loss. "
                "Check task_training_policy.yaml."
            )
        if task not in self.loss_fns:
            raise ValueError(f"No loss configured for task: {task!r}")

        loss = self.loss_fns[task](logits, targets)
        return loss * self._task_weights.get(task, 1.0)

    def active_tasks(self) -> List[str]:
        return list(self.loss_fns.keys())
