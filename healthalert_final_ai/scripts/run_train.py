"""Multi-stage training entry point for HealthAlert.

Usage:
    python scripts/run_train.py --config config/train.yaml
    python scripts/run_train.py --stage 2
    python scripts/run_train.py --stage all
"""

import sys
import argparse
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import torch
from torch.utils.data import DataLoader

from src.utils.io import load_all_configs
from src.utils.seed import set_seed, get_device
from src.utils.logger import setup_logger
from src.data.dataset_registry import build_registry, subject_wise_split
from src.data.column_schema import standardize_records
from src.data.base_dataset import HealthAlertDataset
from src.data.preprocessing.scaler_pipeline import ModalityScaler
from src.models.multitask_model_v2 import HealthAlertModelV2
from src.training.stage_trainer import (
    stage1_inspect,
    stage2_quality_pretrain,
    stage3_fall_instability_train,
    stage4_fusion_risk_train,
    stage5_joint_finetune,
)


def parse_args():
    parser = argparse.ArgumentParser(description="HealthAlert Multi-Stage Training")
    parser.add_argument("--config_dir", type=str, default=None, help="Config directory")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to a config file under config/ (for CLI compatibility)")
    parser.add_argument("--stage", type=str, default="all",
                        help="Stage to run: 1|2|3|4|5|all")
    parser.add_argument("--epochs", type=int, default=None, help="Override max epochs")
    parser.add_argument("--batch_size", type=int, default=None, help="Override batch size")
    parser.add_argument("--device", type=str, default="auto", help="Device")
    return parser.parse_args()


def _make_loaders(train_recs, val_recs, cfg, window_size, stride, batch_size, augment=True):
    """Create train/val DataLoaders from pre-split records."""
    aug_cfg = cfg.get("augmentation", {})
    train_scaler = ModalityScaler()
    train_ds = HealthAlertDataset(
        train_recs, window_size=window_size, stride=stride,
        normalize=True, augment=augment, augment_cfg=aug_cfg,
        scaler=train_scaler, fit_scaler_on_init=True,
    )
    val_ds = HealthAlertDataset(
        val_recs, window_size=window_size, stride=stride,
        normalize=True, augment=False,
        scaler=train_scaler, fit_scaler_on_init=False,
    )

    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True,
        num_workers=0, pin_memory=False, drop_last=True,
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False,
        num_workers=0,
    )
    return train_loader, val_loader


def main():
    args = parse_args()

    if args.config_dir:
        config_dir = args.config_dir
    elif args.config:
        config_dir = str(Path(args.config).resolve().parent)
    else:
        config_dir = str(PROJECT_ROOT / "config")
    cfg = load_all_configs(config_dir)

    if args.epochs is not None:
        cfg.training.epochs = int(args.epochs)
        cfg.training.quality_pretrain_epochs = int(args.epochs)
        cfg.training.fall_train_epochs = int(args.epochs)
        cfg.training.fusion_train_epochs = int(args.epochs)
        cfg.training.finetune_epochs = int(args.epochs)

    seed = cfg.get("project", {}).get("seed", 42)
    set_seed(seed)

    logger = setup_logger(
        "healthalert", level="INFO",
        log_file=str(Path(cfg.get("paths", {}).get("log_dir", "outputs/logs")) / "training.log"),
    )

    device = get_device(args.device)
    logger.info(f"Device: {device}")
    logger.info(f"Seed: {seed}")

    signal_cfg = cfg.get("signal", {})
    window_size = signal_cfg.get("window_size", 200)
    stride = signal_cfg.get("window_stride", 50)
    batch_size = args.batch_size or cfg.get("training", {}).get("batch_size", 64)

    stages = args.stage.lower()

    # ── Load data ────────────────────────────────────────────────
    logger.info("Loading datasets...")
    registry = build_registry(cfg)

    # Standardize all records
    for name in list(registry.keys()):
        registry[name] = standardize_records(registry[name], name)

    # ── Stage 1: Inspect ─────────────────────────────────────────
    if stages in ("1", "all"):
        stage1_inspect(registry, cfg)
        if stages == "1":
            return

    # ── Global subject-wise split (prevents cross-stage leakage) ─
    all_records = []
    for name, recs in registry.items():
        all_records.extend(recs)

    split_cfg = cfg.get("splitting", {})
    global_train, global_val, global_test = subject_wise_split(
        all_records,
        train_ratio=split_cfg.get("train_ratio", 0.7),
        val_ratio=split_cfg.get("val_ratio", 0.15),
        test_ratio=split_cfg.get("test_ratio", 0.15),
        seed=seed,
    )

    train_subjects = set(r["subject_id"] for r in global_train)
    val_subjects = set(r["subject_id"] for r in global_val)
    test_subjects = set(r["subject_id"] for r in global_test)
    logger.info(f"Global split: {len(train_subjects)} train, {len(val_subjects)} val, {len(test_subjects)} test subjects")
    assert not (train_subjects & val_subjects), "Train/Val subject overlap!"
    assert not (train_subjects & test_subjects), "Train/Test subject overlap!"
    assert not (val_subjects & test_subjects), "Val/Test subject overlap!"

    # ── Create model ─────────────────────────────────────────────
    model = HealthAlertModelV2(cfg)
    logger.info(f"Model parameters: {model.count_parameters():,}")

    # ── Stage 2: Quality pre-train ───────────────────────────────
    if stages in ("2", "all"):
        ppg_train = [r for r in global_train if r.get("dataset_name") == "BUT_PPG"]
        ppg_val = [r for r in global_val if r.get("dataset_name") == "BUT_PPG"]
        if ppg_train:
            train_loader, val_loader = _make_loaders(
                ppg_train, ppg_val, cfg, window_size, stride, batch_size, augment=False,
            )
            stage2_quality_pretrain(model, train_loader, val_loader, cfg, device)
        else:
            logger.warning("No BUT_PPG training data -- skipping Stage 2")
        if stages == "2":
            return

    # ── Stage 3: Fall / instability ──────────────────────────────
    if stages in ("3", "all"):
        fall_train = [r for r in global_train if r.get("dataset_name") in ("HIFD", "WEDA_FALL")]
        fall_val = [r for r in global_val if r.get("dataset_name") in ("HIFD", "WEDA_FALL")]
        if fall_train:
            train_loader, val_loader = _make_loaders(
                fall_train, fall_val, cfg, window_size, stride, batch_size,
            )
            stage3_fall_instability_train(model, train_loader, val_loader, cfg, device)
        else:
            logger.warning("No HIFD/WEDA_FALL training data -- skipping Stage 3")
        if stages == "3":
            return

    # ── Stage 4: Fusion + risk (encoders frozen) ─────────────────
    if stages in ("4", "all"):
        if global_train:
            train_loader, val_loader = _make_loaders(
                global_train, global_val, cfg, window_size, stride, batch_size,
            )
            stage4_fusion_risk_train(model, train_loader, val_loader, cfg, device)
        else:
            logger.warning("No data -- skipping Stage 4")
        if stages == "4":
            return

    # ── Stage 5: Joint fine-tune (all unfrozen, lower LR) ────────
    if stages in ("5", "all"):
        if global_train:
            train_loader, val_loader = _make_loaders(
                global_train, global_val, cfg, window_size, stride, batch_size,
            )
            stage5_joint_finetune(model, train_loader, val_loader, cfg, device)
        else:
            logger.warning("No data -- skipping Stage 5")

    logger.info("All stages complete.")


if __name__ == "__main__":
    main()
