import sys
import argparse
import logging
from pathlib import Path

# Proje kokunu import yolu icine ekleyerek yerel paketleri acik hale getirir.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import torch
from torch.utils.data import DataLoader

from src.utils.io import load_all_configs
from src.utils.seed import set_seed, get_device
from src.utils.logger import setup_logger
from src.data.dataset_registry import build_registry, subject_wise_split
from src.data.base_dataset import HealthAlertDataset
from src.models.multitask_model import HealthAlertModel
from src.training.trainer import Trainer


# Tek asamali egitim betigi icin komut satiri seceneklerini okur.
def parse_args():
    parser = argparse.ArgumentParser(description="Train HealthAlert model")
    parser.add_argument("--config_dir", type=str, default=None, help="Config directory")
    parser.add_argument("--epochs", type=int, default=None, help="Override epochs")
    parser.add_argument("--batch_size", type=int, default=None, help="Override batch size")
    parser.add_argument("--lr", type=float, default=None, help="Override learning rate")
    parser.add_argument("--device", type=str, default="auto", help="Device")
    parser.add_argument("--max_subjects", type=int, default=None, help="Limit subjects")
    parser.add_argument("--debug", action="store_true", help="Debug mode (small dataset)")
    return parser.parse_args()


# Veriyi yukleyip temel modeli klasik egitim dongusunde calistirir.
def main():
    args = parse_args()

    # Ayarlari yukleyip komut satiri ustunden gelen degisiklikleri uygular.
    config_dir = args.config_dir or str(PROJECT_ROOT / "config")
    cfg = load_all_configs(config_dir)

    if args.epochs:
        cfg.training.epochs = args.epochs
    if args.batch_size:
        cfg.training.batch_size = args.batch_size
    if args.lr:
        cfg.optimizer.lr = args.lr

    # Tohum, logger ve cihaz secimini baslatir.
    seed = cfg.get("project", {}).get("seed", 42)
    set_seed(seed)

    logger = setup_logger(
        "healthalert",
        level=cfg.get("logging", {}).get("level", "INFO"),
        log_file=str(Path(cfg.paths.log_dir) / "training.log"),
    )

    device = get_device(args.device)
    logger.info(f"Device: {device}")
    logger.info(f"Seed: {seed}")

    logger.info("Loading datasets...")
    registry = build_registry(cfg)

    # Ana egitim omurgasina hareket veri setlerini dahil eder.
    train_records = []
    if "HIFD" in registry:
        train_records.extend(registry["HIFD"])
    if "WEDA_FALL" in registry:
        train_records.extend(registry["WEDA_FALL"])

    if not train_records:
        logger.error("No training records loaded. Check data paths.")
        sys.exit(1)

    # Denek bazli bolme ile egitim ve dogrulamayi ayirir.
    split_cfg = cfg.get("splitting", {})
    train_data, val_data, test_data = subject_wise_split(
        train_records,
        train_ratio=split_cfg.get("train_ratio", 0.7),
        val_ratio=split_cfg.get("val_ratio", 0.15),
        test_ratio=split_cfg.get("test_ratio", 0.15),
        seed=seed,
    )

    # PPG kalite gorevi icin BUT_PPG orneklerini egitim ve dogrulamaya ekler.
    if "BUT_PPG" in registry:
        ppg_records = registry["BUT_PPG"]
        n_ppg_train = int(len(ppg_records) * 0.7)
        train_data.extend(ppg_records[:n_ppg_train])
        val_data.extend(ppg_records[n_ppg_train:])

    # Pencereleme ve arttirma ayarlariyla veri setlerini kurar.
    signal_cfg = cfg.get("signal", {})
    window_size = signal_cfg.get("window_size", 200)
    stride = signal_cfg.get("window_stride", 50)
    aug_cfg = cfg.get("augmentation", {})

    train_dataset = HealthAlertDataset(
        train_data, window_size=window_size, stride=stride,
        normalize=True, augment=aug_cfg.get("enabled", True),
        augment_cfg=aug_cfg,
    )
    val_dataset = HealthAlertDataset(
        val_data, window_size=window_size, stride=stride,
        normalize=True, augment=False,
    )

    logger.info(f"Train: {len(train_dataset)} windows, Val: {len(val_dataset)} windows")

    # Veri yukleyicilerini batch ayarlariyla olusturur.
    train_cfg = cfg.get("training", {})
    train_loader = DataLoader(
        train_dataset,
        batch_size=train_cfg.get("batch_size", 64),
        shuffle=True,
        num_workers=min(train_cfg.get("num_workers", 4), 4),
        pin_memory=train_cfg.get("pin_memory", True),
        drop_last=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=train_cfg.get("batch_size", 64),
        shuffle=False,
        num_workers=min(train_cfg.get("num_workers", 4), 4),
    )

    model = HealthAlertModel(cfg)
    logger.info(f"Model parameters: {model.count_parameters():,}")

    trainer = Trainer(model, cfg, device)
    best_metrics = trainer.fit(train_loader, val_loader)

    # Ayrilan test bolmesi varsa son metriikleri ayrica hesaplar.
    if test_data:
        test_dataset = HealthAlertDataset(
            test_data, window_size=window_size, stride=stride, normalize=True
        )
        test_loader = DataLoader(test_dataset, batch_size=64, shuffle=False)
        test_metrics, _ = trainer.evaluate(test_loader)
        logger.info("=== TEST RESULTS ===")
        for k, v in sorted(test_metrics.items()):
            logger.info(f"  {k}: {v:.4f}")

    logger.info("Training complete!")
    return best_metrics


if __name__ == "__main__":
    main()
