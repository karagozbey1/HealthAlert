"""Evaluation script for HealthAlert.

Load a checkpoint and evaluate on the test set with per-task metrics report.

Usage:
    python scripts/run_eval.py --checkpoint outputs/models/best_final_fusion_model.pt
    python scripts/run_eval.py --checkpoint outputs/models/best_fall_model.pt
"""

import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import torch
import numpy as np
from torch.utils.data import DataLoader

from src.utils.io import load_all_configs, load_checkpoint
from src.utils.seed import set_seed, get_device
from src.utils.logger import setup_logger
from src.data.dataset_registry import build_registry, subject_wise_split
from src.data.column_schema import standardize_records
from src.data.base_dataset import HealthAlertDataset
from src.data.preprocessing.scaler_pipeline import ModalityScaler
from src.models.multitask_model_v2 import HealthAlertModelV2
from src.training.losses import MultiTaskLoss
from src.training.metrics import compute_all_metrics, generate_task_report, calibrate_threshold


def parse_args():
    parser = argparse.ArgumentParser(description="HealthAlert Evaluation")
    parser.add_argument("--checkpoint", type=str, required=True, help="Model checkpoint path")
    parser.add_argument("--config_dir", type=str, default=None, help="Config directory")
    parser.add_argument("--batch_size", type=int, default=64, help="Batch size")
    parser.add_argument("--device", type=str, default="auto", help="Device")
    return parser.parse_args()


def main():
    args = parse_args()

    config_dir = args.config_dir or str(PROJECT_ROOT / "config")
    cfg = load_all_configs(config_dir)

    seed = cfg.get("project", {}).get("seed", 42)
    set_seed(seed)

    logger = setup_logger("healthalert", level="INFO")
    device = get_device(args.device)

    print("\n" + "=" * 60)
    print("  HealthAlert — Model Evaluation")
    print("=" * 60)
    print(f"  Checkpoint: {args.checkpoint}")
    print(f"  Device: {device}")

    # Load model
    model = HealthAlertModelV2(cfg)
    ckpt = load_checkpoint(args.checkpoint, device=str(device))
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device)
    model.eval()

    logger.info(f"Loaded model from {args.checkpoint}")
    if "metrics" in ckpt:
        logger.info(f"Checkpoint metrics: {ckpt['metrics']}")

    # Load data
    registry = build_registry(cfg)
    for name in list(registry.keys()):
        registry[name] = standardize_records(registry[name], name)

    all_records = []
    for name, recs in registry.items():
        all_records.extend(recs)

    if not all_records:
        logger.error("No data loaded. Cannot evaluate.")
        return

    # Get train/val/test split (same global split as training)
    split_cfg = cfg.get("splitting", {})
    train_data, val_data, test_data = subject_wise_split(
        all_records,
        train_ratio=split_cfg.get("train_ratio", 0.7),
        val_ratio=split_cfg.get("val_ratio", 0.15),
        test_ratio=split_cfg.get("test_ratio", 0.15),
        seed=seed,
    )

    # Verify no overlap
    train_subjects = set(r["subject_id"] for r in train_data)
    val_subjects = set(r["subject_id"] for r in val_data)
    test_subjects = set(r["subject_id"] for r in test_data)
    assert not (train_subjects & test_subjects), "LEAKAGE: train/test subject overlap!"
    assert not (val_subjects & test_subjects), "LEAKAGE: val/test subject overlap!"
    print(f"  Train subjects: {len(train_subjects)}")
    print(f"  Val subjects:   {len(val_subjects)}")
    print(f"  Test subjects:  {len(test_subjects)}")

    if not test_data:
        logger.error("No test data after split.")
        return

    signal_cfg = cfg.get("signal", {})
    window_size = signal_cfg.get("window_size", 200)
    stride = signal_cfg.get("window_stride", 50)

    train_scaler = ModalityScaler()
    _ = HealthAlertDataset(
        train_data,
        window_size=window_size,
        stride=stride,
        normalize=True,
        scaler=train_scaler,
        fit_scaler_on_init=True,
    )

    # ── Calibrate thresholds on validation set ───────────────────
    val_ds = HealthAlertDataset(
        val_data,
        window_size=window_size,
        stride=stride,
        normalize=True,
        scaler=train_scaler,
        fit_scaler_on_init=False,
    )
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    val_out = {"fall": [], "instability": [], "quality": [], "risk": []}
    val_tgt = {"fall": [], "instability": [], "quality": [], "risk": []}
    with torch.no_grad():
        for batch in val_loader:
            batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v
                     for k, v in batch.items()}
            outputs = model(batch)
            val_out["fall"].append(torch.sigmoid(outputs["fall_logit"]).cpu().numpy())
            val_out["instability"].append(torch.sigmoid(outputs["instability_logit"]).cpu().numpy())
            val_out["quality"].append(torch.sigmoid(outputs["quality_logit"]).cpu().numpy())
            val_out["risk"].append(outputs["risk_score"].cpu().numpy())
            val_tgt["fall"].append(batch["fall_label"].cpu().numpy())
            val_tgt["instability"].append(batch["instability_label"].cpu().numpy())
            val_tgt["quality"].append(batch["quality_label"].cpu().numpy())
            val_tgt["risk"].append(batch["risk_label"].cpu().numpy())

    for k in val_out:
        val_out[k] = np.concatenate(val_out[k]) if val_out[k] else np.array([])
        val_tgt[k] = np.concatenate(val_tgt[k]) if val_tgt[k] else np.array([])

    calibrated = {}
    for task in ["fall", "instability", "quality"]:
        if len(val_out[task]) > 0 and len(np.unique(val_tgt[task])) > 1:
            t, s = calibrate_threshold(val_tgt[task].astype(int), val_out[task], objective="f1")
            calibrated[task] = t
            print(f"  Calibrated {task} threshold: {t:.3f} (val F1={s:.4f})")
        else:
            calibrated[task] = 0.5
    print()

    # ── Evaluate on test set ─────────────────────────────────────
    test_ds = HealthAlertDataset(
        test_data,
        window_size=window_size,
        stride=stride,
        normalize=True,
        scaler=train_scaler,
        fit_scaler_on_init=False,
    )
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False)

    logger.info(f"Test set: {len(test_ds)} windows")

    # Evaluate
    criterion = MultiTaskLoss(cfg.get("loss", {}))

    all_out = {"fall": [], "instability": [], "quality": [], "risk": []}
    all_tgt = {"fall": [], "instability": [], "quality": [], "risk": []}
    total_loss = 0.0
    n = 0

    with torch.no_grad():
        for batch in test_loader:
            batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v
                     for k, v in batch.items()}
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

    metrics = compute_all_metrics(all_out, all_tgt, calibrated_thresholds=calibrated)
    metrics["test_loss"] = total_loss / max(n, 1)

    report = generate_task_report(metrics)
    print(report)

    # Save report
    report_dir = Path(cfg.get("paths", {}).get("report_dir", "outputs/reports"))
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "evaluation_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
