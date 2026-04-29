"""Multi-stage training pipeline for HealthAlert.

Five training stages:
    Stage 1: Data inspection & validation
    Stage 2: Quality head pre-training (BUT_PPG)
    Stage 3: IMU/fall/instability backbone (HIFD + WEDA_FALL)
    Stage 4: Fusion training with risk proxy head
    Stage 5: Final joint fine-tuning

Each stage produces a named checkpoint.
"""

import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from torch.utils.data import DataLoader

from src.training.losses import MultiTaskLoss
from src.training.metrics import compute_all_metrics
from src.training.optim import build_optimizer, build_scheduler
from src.training.callbacks import EarlyStopping, ModelCheckpoint
from src.utils.io import save_checkpoint

logger = logging.getLogger("healthalert.training.stage_trainer")


# ── Utility ──────────────────────────────────────────────────────────
def _to_device(batch: Dict, device: torch.device) -> Dict:
    return {
        k: v.to(device) if isinstance(v, torch.Tensor) else v
        for k, v in batch.items()
    }


def _train_one_epoch(
    model: torch.nn.Module,
    loader: DataLoader,
    criterion: MultiTaskLoss,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    gradient_clip: float = 1.0,
    active_tasks: Optional[List[str]] = None,
) -> Dict[str, float]:
    """Run one training epoch.

    Args:
        active_tasks: If set, only compute loss for these tasks.
            Options: 'fall', 'instability', 'quality', 'risk'.
    """
    model.train()
    total_loss = 0.0
    loss_components: Dict[str, float] = {}
    n = 0

    for batch in loader:
        batch = _to_device(batch, device)
        optimizer.zero_grad()

        outputs = model(batch)
        targets = {
            "fall_label": batch["fall_label"],
            "instability_label": batch["instability_label"],
            "quality_label": batch["quality_label"],
            "risk_label": batch["risk_label"],
        }

        loss, losses = criterion(outputs, targets, active_tasks=active_tasks)
        loss.backward()

        if gradient_clip > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), gradient_clip)

        optimizer.step()
        total_loss += loss.item()
        for k, v in losses.items():
            loss_components[k] = loss_components.get(k, 0) + v.item()
        n += 1

    return {k: v / max(n, 1) for k, v in loss_components.items()} | {
        "total_avg": total_loss / max(n, 1)
    }


@torch.no_grad()
def _evaluate(
    model: torch.nn.Module,
    loader: DataLoader,
    criterion: MultiTaskLoss,
    device: torch.device,
) -> Tuple[Dict[str, float], Dict]:
    """Evaluate on a data loader."""
    model.eval()
    all_out = {"fall": [], "instability": [], "quality": [], "risk": []}
    all_tgt = {"fall": [], "instability": [], "quality": [], "risk": []}
    total_loss = 0.0
    n = 0

    for batch in loader:
        batch = _to_device(batch, device)
        outputs = model(batch)
        targets = {
            "fall_label": batch["fall_label"],
            "instability_label": batch["instability_label"],
            "quality_label": batch["quality_label"],
            "risk_label": batch["risk_label"],
        }
        loss, _ = criterion(outputs, targets)
        total_loss += loss.item()
        n += 1

        all_out["fall"].append(torch.sigmoid(outputs["fall_logit"]).cpu().numpy())
        all_out["instability"].append(torch.sigmoid(outputs["instability_logit"]).cpu().numpy())
        all_out["quality"].append(torch.sigmoid(outputs["quality_logit"]).cpu().numpy())
        all_out["risk"].append(outputs["risk_score"].cpu().numpy())

        all_tgt["fall"].append(batch["fall_label"].cpu().numpy())
        all_tgt["instability"].append(batch["instability_label"].cpu().numpy())
        all_tgt["quality"].append(batch["quality_label"].cpu().numpy())
        all_tgt["risk"].append(batch["risk_label"].cpu().numpy())

    for k in all_out:
        all_out[k] = np.concatenate(all_out[k]) if all_out[k] else np.array([])
        all_tgt[k] = np.concatenate(all_tgt[k]) if all_tgt[k] else np.array([])

    metrics = compute_all_metrics(all_out, all_tgt)
    metrics["val_loss"] = total_loss / max(n, 1)
    return metrics, {"outputs": all_out, "targets": all_tgt}


def _run_stage(
    stage_name: str,
    model: torch.nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    cfg,
    device: torch.device,
    checkpoint_name: str,
    active_tasks: Optional[List[str]] = None,
    monitor_metric: str = "fall_f1",
    max_epochs: Optional[int] = None,
    lr_override: Optional[float] = None,
) -> Dict[str, float]:
    """Generic stage runner."""
    logger.info(f"\n{'='*60}")
    logger.info(f"  STAGE: {stage_name}")
    logger.info(f"{'='*60}")

    loss_cfg = cfg.get("loss", {})
    criterion = MultiTaskLoss(loss_cfg)

    opt_cfg = cfg.get("optimizer", {})
    if lr_override is not None:
        opt_cfg = dict(opt_cfg)
        opt_cfg["lr"] = lr_override
    optimizer = build_optimizer(model, opt_cfg)

    sched_cfg = cfg.get("scheduler", {})
    scheduler = build_scheduler(optimizer, sched_cfg)

    train_cfg = cfg.get("training", {})
    epochs = max_epochs or train_cfg.get("epochs", 50)
    grad_clip = train_cfg.get("gradient_clip", 1.0)
    patience = train_cfg.get("early_stopping_patience", 15)

    save_dir = Path(cfg.get("paths", {}).get("model_dir", "outputs/models"))
    save_dir.mkdir(parents=True, exist_ok=True)

    early_stop = EarlyStopping(patience=patience, mode="max")
    best_metrics: Dict[str, float] = {}
    best_score = -1.0

    for epoch in range(1, epochs + 1):
        t0 = time.time()

        train_losses = _train_one_epoch(
            model, train_loader, criterion, optimizer, device,
            gradient_clip=grad_clip, active_tasks=active_tasks,
        )

        val_metrics, _ = _evaluate(model, val_loader, criterion, device)

        if scheduler is not None:
            if isinstance(scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau):
                scheduler.step(val_metrics.get(monitor_metric, 0))
            else:
                scheduler.step()

        elapsed = time.time() - t0
        lr = optimizer.param_groups[0]["lr"]
        score = val_metrics.get(monitor_metric, 0)

        logger.info(
            f"[{stage_name}] Epoch {epoch:3d}/{epochs} | "
            f"loss={train_losses.get('total_avg', 0):.4f} | "
            f"{monitor_metric}={score:.4f} | lr={lr:.6f} | {elapsed:.1f}s"
        )

        if score > best_score:
            best_score = score
            best_metrics = val_metrics.copy()
            save_checkpoint(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "metrics": val_metrics,
                    "stage": stage_name,
                },
                save_dir / checkpoint_name,
            )
            logger.info(f"  New best {monitor_metric}={score:.4f} -> {checkpoint_name}")

        if early_stop(score):
            logger.info(f"  Early stopping at epoch {epoch}")
            break

    logger.info(f"[{stage_name}] Complete. Best {monitor_metric}={best_score:.4f}")
    return best_metrics


# ── Public stage runners ─────────────────────────────────────────────

def stage1_inspect(registry: Dict[str, list], cfg) -> None:
    """Stage 1: Data inspection and validation."""
    logger.info("\n" + "=" * 60)
    logger.info("  STAGE 1: Data Inspection")
    logger.info("=" * 60)

    for name, records in registry.items():
        logger.info(f"\n--- {name} ---")
        logger.info(f"  Total records: {len(records)}")
        if not records:
            continue

        subjects = set(r.get("subject_id", "") for r in records)
        logger.info(f"  Unique subjects: {len(subjects)}")

        labels = [r.get("label", -1) for r in records]
        from collections import Counter
        dist = Counter(labels)
        logger.info(f"  Label distribution: {dict(dist)}")

        if "data" in records[0] and hasattr(records[0]["data"], "shape"):
            sample = records[0]["data"]
            logger.info(f"  Sample shape: {sample.shape}")
            if hasattr(sample, "columns"):
                logger.info(f"  Columns: {list(sample.columns)}")

    logger.info("\nStage 1 complete.")


def stage2_quality_pretrain(
    model: torch.nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    cfg,
    device: torch.device,
) -> Dict[str, float]:
    """Stage 2: Pre-train quality head on BUT_PPG."""
    return _run_stage(
        stage_name="Stage2_QualityPretrain",
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        cfg=cfg,
        device=device,
        checkpoint_name="best_quality_model.pt",
        active_tasks=["quality"],
        monitor_metric="quality_f1",
        max_epochs=cfg.get("training", {}).get("quality_pretrain_epochs", 30),
    )


def stage3_fall_instability_train(
    model: torch.nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    cfg,
    device: torch.device,
) -> Dict[str, float]:
    """Stage 3: Train fall + instability on HIFD + WEDA_FALL."""
    return _run_stage(
        stage_name="Stage3_FallInstability",
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        cfg=cfg,
        device=device,
        checkpoint_name="best_fall_model.pt",
        active_tasks=["fall", "instability"],
        monitor_metric="fall_f1",
        max_epochs=cfg.get("training", {}).get("fall_train_epochs", 60),
    )


def stage4_fusion_risk_train(
    model: torch.nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    cfg,
    device: torch.device,
) -> Dict[str, float]:
    """Stage 4: Freeze encoders, train fusion + risk + all heads.

    Encoders (IMU, PPG) are frozen so fusion attention and task heads
    learn to combine already-useful representations without disrupting
    the encoder weights established in stages 2-3.
    """
    model.freeze_encoders()
    logger.info("[Stage4] Encoders FROZEN — training fusion + heads only")
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    n_total = sum(p.numel() for p in model.parameters())
    logger.info(f"[Stage4] Trainable: {n_trainable:,} / {n_total:,} parameters")

    return _run_stage(
        stage_name="Stage4_FusionRisk",
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        cfg=cfg,
        device=device,
        checkpoint_name="best_multitask_model.pt",
        active_tasks=["fall", "instability", "quality", "risk"],
        monitor_metric="fall_f1",
        max_epochs=cfg.get("training", {}).get("fusion_train_epochs", 50),
    )


def stage5_joint_finetune(
    model: torch.nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    cfg,
    device: torch.device,
) -> Dict[str, float]:
    """Stage 5: Unfreeze all, joint fine-tuning with lower LR.

    All parameters are unfrozen and trained together with a reduced
    learning rate (1/10 of base) so the whole model is refined jointly
    without catastrophic forgetting of earlier stages.
    """
    model.unfreeze_all()
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info(f"[Stage5] All parameters UNFROZEN — {n_trainable:,} trainable")

    # Override LR to 1/10 of base for fine-tuning
    finetune_cfg = dict(cfg)
    base_lr = cfg.get("optimizer", {}).get("lr", 0.001)
    finetune_lr = base_lr * 0.1
    logger.info(f"[Stage5] Fine-tune LR: {finetune_lr:.6f} (base={base_lr:.4f})")

    return _run_stage(
        stage_name="Stage5_JointFinetune",
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        cfg=cfg,
        device=device,
        checkpoint_name="best_final_fusion_model.pt",
        active_tasks=None,  # all tasks
        monitor_metric="fall_f1",
        max_epochs=cfg.get("training", {}).get("finetune_epochs", 40),
        lr_override=finetune_lr,
    )
