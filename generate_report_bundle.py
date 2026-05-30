#!/usr/bin/env python3
"""
HealthAlert — Veri Eğitimi / Model Değerlendirme Rapor Paketi Üreticisi
========================================================================
Bu script mevcut eğitilmiş modelleri yükler, tüm görevler için kapsamlı
değerlendirme yapar ve rapora koyulabilir kalitede çıktı paketi üretir.

Çalıştırma:
    python generate_report_bundle.py

Çıktı:
    report_bundle/ klasörü altında tüm metrik, grafik, tablo ve metinler.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import warnings
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Headless backend for PNG generation
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
plt.rcParams.update({
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "figure.figsize": (10, 7),
    "figure.facecolor": "white",
})

import torch
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, classification_report,
    confusion_matrix, f1_score, matthews_corrcoef, cohen_kappa_score,
    precision_recall_curve, precision_score, recall_score,
    roc_auc_score, roc_curve, average_precision_score, mean_squared_error,
    mean_absolute_error, r2_score,
)

warnings.filterwarnings("ignore", category=UserWarning)

# ============================================================
# PATH SETUP
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent
HEALTHALERT_AI_ROOT = PROJECT_ROOT / "healthalert_final_ai"
sys.path.insert(0, str(HEALTHALERT_AI_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

BUNDLE_DIR = PROJECT_ROOT / "report_bundle"

# Sub-directories
SUMMARY_DIR   = BUNDLE_DIR / "00_summary"
METRICS_DIR   = BUNDLE_DIR / "01_metrics"
FIGURES_DIR   = BUNDLE_DIR / "02_figures"
CM_DIR        = BUNDLE_DIR / "03_confusion_matrices"
CURVES_DIR    = BUNDLE_DIR / "04_curves"
PRED_DIR      = BUNDLE_DIR / "05_predictions"
CKPT_DIR      = BUNDLE_DIR / "06_checkpoints_info"
SPLIT_DIR     = BUNDLE_DIR / "07_data_split"
REPORT_DIR    = BUNDLE_DIR / "08_report_text"
CONFIG_DIR    = BUNDLE_DIR / "09_configs_used"

ALL_DIRS = [SUMMARY_DIR, METRICS_DIR, FIGURES_DIR, CM_DIR, CURVES_DIR,
            PRED_DIR, CKPT_DIR, SPLIT_DIR, REPORT_DIR, CONFIG_DIR]


def ensure_dirs():
    """Rapor paketinin çıktı klasörlerini oluşturur."""
    for d in ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)


# ============================================================
# HELPERS
# ============================================================
def safe_metric(fn, *args, **kwargs):
    """Metrik hesaplama hatasını yakalayıp rapora güvenli varsayılan döndürür."""
    try:
        return float(fn(*args, **kwargs))
    except Exception:
        return float("nan")


def save_csv(path: Path, rows: List[Dict], fieldnames: List[str] = None):
    """Rapor verilerini CSV dosyasına yazar."""
    if not rows:
        return
    if fieldnames is None:
        # Collect ALL keys from ALL rows to handle heterogeneous dicts
        seen = set()
        ordered = []
        for row in rows:
            for k in row.keys():
                if k not in seen:
                    seen.add(k)
                    ordered.append(k)
        fieldnames = ordered
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def save_json(path: Path, data):
    """Rapor verilerini JSON dosyasına yazar."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def save_text(path: Path, text: str):
    """Rapor metnini hedef dosyaya yazar."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ============================================================
# PART A: Multi-Task Model Evaluation (healthalert_final_ai)
# ============================================================
def evaluate_multitask_model():
    """generate report bundle dosyasındaki backend yardımcı işlemini yürütür."""
    print("\n" + "=" * 70)
    print("  PART A: Multi-Task Model (HealthAlertModelV2) Evaluation")
    print("=" * 70)

    from src.utils.io import load_all_configs, load_checkpoint
    from src.utils.seed import set_seed, get_device
    from src.data.dataset_registry import build_registry, subject_wise_split
    from src.data.column_schema import standardize_records
    from src.data.base_dataset import HealthAlertDataset
    from src.data.preprocessing.scaler_pipeline import ModalityScaler
    from src.models.multitask_model_v2 import HealthAlertModelV2
    from src.training.losses import MultiTaskLoss
    from src.training.metrics import compute_all_metrics, calibrate_threshold

    config_dir = str(HEALTHALERT_AI_ROOT / "config")
    cfg = load_all_configs(config_dir)
    seed = cfg.get("project", {}).get("seed", 42)
    set_seed(seed)
    device = get_device("auto")
    print(f"  Device: {device}")

    # ── Load model ───────────────────────────────────────────────
    ckpt_path = PROJECT_ROOT / "outputs" / "models" / "best_final_fusion_model.pt"
    if not ckpt_path.exists():
        print(f"  [WARN] Checkpoint not found: {ckpt_path}")
        return None

    ckpt = load_checkpoint(str(ckpt_path), device=str(device))

    # Detect vitals_dim from checkpoint to avoid size mismatch
    vitals_weight_key = "vitals_mlp.mlp.0.weight"
    if vitals_weight_key in ckpt["model_state_dict"]:
        ckpt_vitals_dim = ckpt["model_state_dict"][vitals_weight_key].shape[1]
        current_dim = cfg.get("model", {}).get("vitals_mlp", {}).get("input_dim", 2)
        if ckpt_vitals_dim != current_dim:
            print(f"  [INFO] Overriding vitals_dim: config={current_dim} -> checkpoint={ckpt_vitals_dim}")
            from omegaconf import OmegaConf, open_dict
            with open_dict(cfg):
                cfg.model.vitals_mlp.input_dim = ckpt_vitals_dim

    model = HealthAlertModelV2(cfg)
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device)
    model.eval()

    n_params = sum(p.numel() for p in model.parameters())
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    ckpt_epoch = ckpt.get("epoch", "?")
    ckpt_stage = ckpt.get("stage", "?")
    ckpt_metrics = ckpt.get("metrics", {})

    print(f"  Model params: {n_params:,} (trainable: {n_trainable:,})")
    print(f"  Checkpoint epoch: {ckpt_epoch}, stage: {ckpt_stage}")

    # ── Load data ────────────────────────────────────────────────
    registry = build_registry(cfg)
    for name in list(registry.keys()):
        registry[name] = standardize_records(registry[name], name)

    all_records = []
    for name, recs in registry.items():
        all_records.extend(recs)

    split_cfg = cfg.get("splitting", {})
    train_data, val_data, test_data = subject_wise_split(
        all_records,
        train_ratio=split_cfg.get("train_ratio", 0.7),
        val_ratio=split_cfg.get("val_ratio", 0.15),
        test_ratio=split_cfg.get("test_ratio", 0.15),
        seed=seed,
    )

    train_subjects = sorted(set(r["subject_id"] for r in train_data))
    val_subjects = sorted(set(r["subject_id"] for r in val_data))
    test_subjects = sorted(set(r["subject_id"] for r in test_data))
    print(f"  Split: {len(train_subjects)} train, {len(val_subjects)} val, {len(test_subjects)} test subjects")
    print(f"  Records: {len(train_data)} train, {len(val_data)} val, {len(test_data)} test")

    signal_cfg = cfg.get("signal", {})
    window_size = signal_cfg.get("window_size", 200)
    stride = signal_cfg.get("window_stride", 50)

    # Fit scaler on train
    train_scaler = ModalityScaler()
    _ = HealthAlertDataset(
        train_data, window_size=window_size, stride=stride,
        normalize=True, scaler=train_scaler, fit_scaler_on_init=True,
    )

    # ── Calibrate thresholds on validation ───────────────────────
    val_ds = HealthAlertDataset(
        val_data, window_size=window_size, stride=stride,
        normalize=True, scaler=train_scaler, fit_scaler_on_init=False,
    )
    val_loader = torch.utils.data.DataLoader(val_ds, batch_size=64, shuffle=False, num_workers=0)

    # Check if model expects wider vitals than dataset provides
    ckpt_vitals_dim = cfg.get("model", {}).get("vitals_mlp", {}).get("input_dim", 2)

    def _pad_vitals_if_needed(batch, target_dim):
        """generate report bundle dosyasındaki backend yardımcı işlemini yürütür."""
        v = batch["vitals"]
        if v.shape[-1] < target_dim:
            pad = torch.zeros(*v.shape[:-1], target_dim - v.shape[-1], dtype=v.dtype, device=v.device)
            batch["vitals"] = torch.cat([v, pad], dim=-1)
        return batch

    val_out = {"fall": [], "instability": [], "quality": [], "risk": []}
    val_tgt = {"fall": [], "instability": [], "quality": [], "risk": []}
    with torch.no_grad():
        for batch in val_loader:
            batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in batch.items()}
            batch = _pad_vitals_if_needed(batch, ckpt_vitals_dim)
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

    # ── Evaluate on test set ─────────────────────────────────────
    test_ds = HealthAlertDataset(
        test_data, window_size=window_size, stride=stride,
        normalize=True, scaler=train_scaler, fit_scaler_on_init=False,
    )
    test_loader = torch.utils.data.DataLoader(test_ds, batch_size=64, shuffle=False, num_workers=0)
    print(f"  Test windows: {len(test_ds)}")

    all_out = {"fall": [], "instability": [], "quality": [], "risk": []}
    all_tgt = {"fall": [], "instability": [], "quality": [], "risk": []}
    criterion = MultiTaskLoss(cfg.get("loss", {}))
    total_loss = 0.0
    n_batches = 0

    with torch.no_grad():
        for batch in test_loader:
            batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in batch.items()}
            batch = _pad_vitals_if_needed(batch, ckpt_vitals_dim)
            outputs = model(batch)
            targets = {
                "fall_label": batch["fall_label"],
                "instability_label": batch["instability_label"],
                "quality_label": batch["quality_label"],
                "risk_label": batch["risk_label"],
            }
            loss, _ = criterion(outputs, targets)
            total_loss += loss.item()
            n_batches += 1

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

    test_loss = total_loss / max(n_batches, 1)

    # ── Save split info ──────────────────────────────────────────
    dataset_counts = Counter(r["dataset_name"] for r in all_records)
    train_dataset_counts = Counter(r["dataset_name"] for r in train_data)
    val_dataset_counts = Counter(r["dataset_name"] for r in val_data)
    test_dataset_counts = Counter(r["dataset_name"] for r in test_data)

    # Label distributions
    train_labels = Counter(r.get("label", -1) for r in train_data)
    val_labels = Counter(r.get("label", -1) for r in val_data)
    test_labels = Counter(r.get("label", -1) for r in test_data)

    split_info = {
        "total_records": len(all_records),
        "train_records": len(train_data),
        "val_records": len(val_data),
        "test_records": len(test_data),
        "train_subjects": train_subjects,
        "val_subjects": val_subjects,
        "test_subjects": test_subjects,
        "train_windows": len(HealthAlertDataset(
            train_data, window_size=window_size, stride=stride,
            normalize=True, scaler=train_scaler, fit_scaler_on_init=False,
        )),
        "val_windows": len(val_ds),
        "test_windows": len(test_ds),
        "dataset_counts": dict(dataset_counts),
        "train_dataset_counts": dict(train_dataset_counts),
        "val_dataset_counts": dict(val_dataset_counts),
        "test_dataset_counts": dict(test_dataset_counts),
        "train_labels": dict(train_labels),
        "val_labels": dict(val_labels),
        "test_labels": dict(test_labels),
        "split_strategy": "subject_wise",
        "train_ratio": split_cfg.get("train_ratio", 0.7),
        "val_ratio": split_cfg.get("val_ratio", 0.15),
        "test_ratio": split_cfg.get("test_ratio", 0.15),
        "seed": seed,
        "window_size": window_size,
        "stride": stride,
    }

    # Package checkpoint info
    ckpt_info = {
        "checkpoint_path": str(ckpt_path),
        "checkpoint_epoch": ckpt_epoch,
        "checkpoint_stage": ckpt_stage,
        "total_params": n_params,
        "trainable_params": n_trainable,
        "model_name": "HealthAlertModelV2",
        "architecture": "CRNN(IMU) + CNN1D(PPG) + VitalsMLP + HandcraftedMLP + FusionAttention + 4 Heads",
        "optimizer": cfg.get("optimizer", {}).get("name", "adamw"),
        "learning_rate": cfg.get("optimizer", {}).get("lr", 0.001),
        "weight_decay": cfg.get("optimizer", {}).get("weight_decay", 0.01),
        "scheduler": cfg.get("scheduler", {}).get("name", "cosine_annealing"),
        "batch_size": cfg.get("training", {}).get("batch_size", 64),
        "max_epochs": cfg.get("training", {}).get("epochs", 100),
        "early_stopping_patience": cfg.get("training", {}).get("early_stopping_patience", 15),
        "gradient_clip": cfg.get("training", {}).get("gradient_clip", 1.0),
        "loss_fall": "Focal Loss (α=0.75, γ=2.0, w=1.0)",
        "loss_instability": "BCE (pos_weight=5.0, w=0.5)",
        "loss_quality": "BCE (pos_weight=3.0, w=0.3)",
        "loss_risk": "MSE (w=0.4)",
        "augmentation": "IMU noise(0.02), scale(0.9-1.1), time_warp(0.1), mixup(0.2)",
        "calibrated_thresholds": calibrated,
    }

    return {
        "all_out": all_out,
        "all_tgt": all_tgt,
        "calibrated": calibrated,
        "test_loss": test_loss,
        "split_info": split_info,
        "ckpt_info": ckpt_info,
        "cfg": cfg,
        "val_out": val_out,
        "val_tgt": val_tgt,
    }


# ============================================================
# PART B: HIFD CRNN (Legacy) Training + Evaluation
# ============================================================
def run_hifd_crnn():
    """generate report bundle dosyasındaki backend yardımcı işlemini yürütür."""
    print("\n" + "=" * 70)
    print("  PART B: HIFD CRNN (Binary Fall Detection) Training")
    print("=" * 70)

    # Import from root src
    sys.path.insert(0, str(PROJECT_ROOT))
    from train_hifd_crnn_mat import (
        WindowCfg, make_windows, split_by_subject, compute_norm_stats,
        HIFDWindowDS, CRNN, eval_model_with_scores, compute_loader_loss,
        compute_metrics, count_parameters,
    )
    from torch.utils.data import DataLoader

    seed = 42
    torch.manual_seed(seed)
    np.random.seed(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    data_root = PROJECT_ROOT / "Data" / "HIFD"
    cfg = WindowCfg(fs=50, window_sec=2.0, stride_sec=0.5)
    windows, uniq_labels, win_len, stride_samples = make_windows(data_root, cfg)

    label2id = {name: i for i, name in enumerate(uniq_labels)}
    id2label = {i: name for name, i in label2id.items()}
    class_names = [id2label[i] for i in range(len(uniq_labels))]

    tr_w, va_w, te_w, tr_sub, va_sub, te_sub = split_by_subject(windows, seed=seed)
    print(f"  Classes: {class_names}")
    print(f"  Total windows: {len(windows)}")
    print(f"  Train: {len(tr_w)} | Val: {len(va_w)} | Test: {len(te_w)}")
    print(f"  Train subjects: {sorted(tr_sub)}")
    print(f"  Val subjects: {sorted(va_sub)}")
    print(f"  Test subjects: {sorted(te_sub)}")

    norm = compute_norm_stats(tr_w)
    train_ds = HIFDWindowDS(tr_w, label2id, norm)
    val_ds = HIFDWindowDS(va_w, label2id, norm)
    test_ds = HIFDWindowDS(te_w, label2id, norm) if te_w else None

    batch_size = 256
    epochs = 25
    lr = 1e-3

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=0) if test_ds else None

    model = CRNN(num_classes=len(uniq_labels)).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    crit = torch.nn.CrossEntropyLoss()
    n_params = count_parameters(model)

    best_f1 = -1.0
    train_losses, val_losses = [], []
    val_metrics_history = {"Accuracy": [], "BalancedAcc": [], "F1_macro": [], "MCC": []}
    best_epoch = 0

    print(f"  Model params: {n_params:,}")
    print(f"  Training {epochs} epochs...")

    for epoch in range(1, epochs + 1):
        model.train()
        total, n = 0.0, 0
        for ppg, imu, y in train_loader:
            ppg, imu, y = ppg.to(device), imu.to(device), y.to(device)
            opt.zero_grad()
            logits = model(ppg, imu)
            loss = crit(logits, y)
            loss.backward()
            opt.step()
            total += loss.item() * y.shape[0]
            n += y.shape[0]

        tr_loss = total / max(1, n)
        train_losses.append(tr_loss)
        va_loss = compute_loader_loss(model, val_loader, device, crit)
        val_losses.append(va_loss)

        y_true_v, y_pred_v, _ = eval_model_with_scores(model, val_loader, device, len(class_names))
        acc_v = accuracy_score(y_true_v, y_pred_v) if len(y_true_v) > 0 else 0
        bal_v = balanced_accuracy_score(y_true_v, y_pred_v) if len(y_true_v) > 0 else 0
        f1m_v = f1_score(y_true_v, y_pred_v, average="macro", zero_division=0)
        mcc_v = matthews_corrcoef(y_true_v, y_pred_v) if len(y_true_v) > 0 else 0

        val_metrics_history["Accuracy"].append(float(acc_v))
        val_metrics_history["BalancedAcc"].append(float(bal_v))
        val_metrics_history["F1_macro"].append(float(f1m_v))
        val_metrics_history["MCC"].append(float(mcc_v))

        if f1m_v > best_f1:
            best_f1 = f1m_v
            best_epoch = epoch
            torch.save(model.state_dict(), str(CKPT_DIR / "hifd_crnn_best.pt"))

        if epoch % 5 == 0 or epoch == epochs:
            print(f"    Epoch {epoch:02d}/{epochs} | trL={tr_loss:.4f} vaL={va_loss:.4f} | "
                  f"acc={acc_v:.3f} f1m={f1m_v:.3f} mcc={mcc_v:.3f}")

    # Load best and evaluate
    model.load_state_dict(torch.load(str(CKPT_DIR / "hifd_crnn_best.pt"), map_location=device, weights_only=True))

    if test_loader:
        y_true, y_pred, y_score = eval_model_with_scores(model, test_loader, device, len(class_names))
        eval_split = "test"
    else:
        y_true, y_pred, y_score = eval_model_with_scores(model, val_loader, device, len(class_names))
        eval_split = "val"

    final_metrics = compute_metrics(y_true, y_pred, y_score, class_names)

    return {
        "y_true": y_true,
        "y_pred": y_pred,
        "y_score": y_score,
        "class_names": class_names,
        "final_metrics": final_metrics,
        "train_losses": train_losses,
        "val_losses": val_losses,
        "val_metrics_history": val_metrics_history,
        "n_params": n_params,
        "best_epoch": best_epoch,
        "best_f1": best_f1,
        "eval_split": eval_split,
        "split_counts": {
            "train_windows": len(tr_w),
            "val_windows": len(va_w),
            "test_windows": len(te_w),
            "total_windows": len(windows),
        },
        "subjects": {
            "train": sorted(tr_sub),
            "val": sorted(va_sub),
            "test": sorted(te_sub),
        },
        "config": {
            "fs": 50, "window_sec": 2.0, "stride_sec": 0.5,
            "epochs": epochs, "batch_size": batch_size, "lr": lr,
            "seed": seed, "device": device,
        },
    }


# ============================================================
# GRAPH GENERATION FUNCTIONS
# ============================================================

def plot_confusion_matrix(y_true, y_pred, class_names, title, save_path, normalize=False):
    """Rapor paketinde kullanılacak ilgili grafiği dosyaya kaydeder."""
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names))))
    if normalize:
        row_sums = cm.sum(axis=1, keepdims=True)
        cm_display = cm.astype(float) / np.maximum(row_sums, 1)
        fmt = ".2f"
    else:
        cm_display = cm
        fmt = "d"

    fig, ax = plt.subplots(figsize=(8, 6.5))
    im = ax.imshow(cm_display, interpolation="nearest", cmap=plt.cm.Blues)
    plt.colorbar(im, ax=ax, fraction=0.046)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Tahmin (Predicted)", fontsize=12)
    ax.set_ylabel("Gerçek (Actual)", fontsize=12)
    ax.set_xticks(range(len(class_names)))
    ax.set_yticks(range(len(class_names)))
    ax.set_xticklabels(class_names, rotation=45, ha="right")
    ax.set_yticklabels(class_names)

    thresh = cm_display.max() / 2.0
    for i in range(cm_display.shape[0]):
        for j in range(cm_display.shape[1]):
            val = cm_display[i, j]
            txt = f"{val:{fmt}}" if not normalize else f"{val:.2f}\n({cm[i,j]})"
            ax.text(j, i, txt, ha="center", va="center",
                    color="white" if val > thresh else "black", fontsize=10)

    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


def plot_roc_curve(y_true, y_score, title, save_path, pos_label=1):
    """Rapor paketinde kullanılacak ilgili grafiği dosyaya kaydeder."""
    if y_score is None or len(np.unique(y_true)) < 2:
        return
    fpr, tpr, thresholds = roc_curve(y_true, y_score, pos_label=pos_label)
    auc_val = roc_auc_score(y_true, y_score)

    fig, ax = plt.subplots(figsize=(8, 7))
    ax.plot(fpr, tpr, "b-", linewidth=2, label=f"ROC (AUC = {auc_val:.4f})")
    ax.plot([0, 1], [0, 1], "k--", alpha=0.4, label="Random")
    ax.set_xlabel("False Positive Rate (1 - Specificity)")
    ax.set_ylabel("True Positive Rate (Sensitivity)")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="lower right", fontsize=11)
    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.02])
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


def plot_pr_curve(y_true, y_score, title, save_path, pos_label=1):
    """Rapor paketinde kullanılacak ilgili grafiği dosyaya kaydeder."""
    if y_score is None or len(np.unique(y_true)) < 2:
        return
    precision, recall, _ = precision_recall_curve(y_true, y_score, pos_label=pos_label)
    ap = average_precision_score(y_true, y_score)

    fig, ax = plt.subplots(figsize=(8, 7))
    ax.plot(recall, precision, "r-", linewidth=2, label=f"PR (AP = {ap:.4f})")
    baseline = y_true.sum() / len(y_true)
    ax.axhline(y=baseline, color="k", linestyle="--", alpha=0.4, label=f"Baseline ({baseline:.3f})")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="upper right", fontsize=11)
    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.05])
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


def plot_loss_curves(train_losses, val_losses, title, save_path):
    """Rapor paketinde kullanılacak ilgili grafiği dosyaya kaydeder."""
    epochs = np.arange(1, len(train_losses) + 1)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(epochs, train_losses, "b-o", markersize=3, label="Train Loss")
    if len(val_losses) == len(train_losses):
        ax.plot(epochs, val_losses, "r-o", markersize=3, label="Validation Loss")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Loss")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


def plot_metric_curves(val_metrics_history, title, save_path):
    """Rapor paketinde kullanılacak ilgili grafiği dosyaya kaydeder."""
    fig, ax = plt.subplots(figsize=(10, 6))
    epochs = None
    for key in ["Accuracy", "F1_macro", "MCC", "BalancedAcc"]:
        if key in val_metrics_history and val_metrics_history[key]:
            values = val_metrics_history[key]
            epochs = np.arange(1, len(values) + 1)
            ax.plot(epochs, values, "-o", markersize=3, label=f"Val {key}")
    if epochs is not None:
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Score")
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_ylim(0, 1.05)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


def plot_scatter_regression(y_true, y_pred, title, save_path):
    """Rapor paketinde kullanılacak ilgili grafiği dosyaya kaydeder."""
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.scatter(y_true, y_pred, alpha=0.3, s=10, c="steelblue")
    mn, mx = min(y_true.min(), y_pred.min()), max(y_true.max(), y_pred.max())
    ax.plot([mn, mx], [mn, mx], "r--", linewidth=2, label="Ideal (y=x)")
    ax.set_xlabel("Gerçek Risk Skoru (Actual)")
    ax.set_ylabel("Tahmin Risk Skoru (Predicted)")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


def plot_residuals(y_true, y_pred, title, save_path):
    """Rapor paketinde kullanılacak ilgili grafiği dosyaya kaydeder."""
    residuals = y_pred - y_true
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    axes[0].scatter(y_true, residuals, alpha=0.3, s=10, c="steelblue")
    axes[0].axhline(y=0, color="r", linestyle="--", linewidth=2)
    axes[0].set_xlabel("Gerçek Risk Skoru")
    axes[0].set_ylabel("Artık (Residual)")
    axes[0].set_title("Residual Plot")
    axes[0].grid(True, alpha=0.3)

    axes[1].hist(residuals, bins=50, color="steelblue", edgecolor="white", alpha=0.8)
    axes[1].axvline(x=0, color="r", linestyle="--", linewidth=2)
    axes[1].set_xlabel("Artık (Residual)")
    axes[1].set_ylabel("Frekans")
    axes[1].set_title("Hata Dağılımı (Error Distribution)")
    axes[1].grid(True, alpha=0.3)

    fig.suptitle(title, fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


def plot_class_distribution(split_info, save_path):
    """Rapor paketinde kullanılacak ilgili grafiği dosyaya kaydeder."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    label_map = {0: "ADL", 1: "Fall", 2: "Near-Fall", -1: "PPG Quality"}

    for idx, (split_name, label_dict) in enumerate([
        ("Train", split_info["train_labels"]),
        ("Validation", split_info["val_labels"]),
        ("Test", split_info["test_labels"]),
    ]):
        names = [label_map.get(int(k), str(k)) for k in label_dict.keys()]
        counts = list(label_dict.values())
        axes[idx].bar(names, counts, color=["#3498db", "#e74c3c", "#f39c12", "#2ecc71"][:len(names)],
                      edgecolor="white")
        axes[idx].set_title(f"{split_name} Set", fontweight="bold")
        axes[idx].set_ylabel("Kayıt Sayısı (Record Count)")
        for i, v in enumerate(counts):
            axes[idx].text(i, v + max(counts) * 0.01, str(v), ha="center", fontweight="bold")

    fig.suptitle("Veri Seti Etiket Dağılımı (Label Distribution by Split)", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


def plot_dataset_split_summary(split_info, save_path):
    """Rapor paketinde kullanılacak ilgili grafiği dosyaya kaydeder."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Records per split
    splits = ["Train", "Validation", "Test"]
    record_counts = [split_info["train_records"], split_info["val_records"], split_info["test_records"]]
    colors = ["#3498db", "#f39c12", "#e74c3c"]
    axes[0].bar(splits, record_counts, color=colors, edgecolor="white")
    axes[0].set_title("Kayıt Sayıları (Record Counts)", fontweight="bold")
    axes[0].set_ylabel("Kayıt")
    for i, v in enumerate(record_counts):
        axes[0].text(i, v + max(record_counts) * 0.01, str(v), ha="center", fontweight="bold")

    # Dataset composition
    datasets = list(split_info["dataset_counts"].keys())
    x = np.arange(len(datasets))
    width = 0.25
    tr_counts = [split_info["train_dataset_counts"].get(d, 0) for d in datasets]
    va_counts = [split_info["val_dataset_counts"].get(d, 0) for d in datasets]
    te_counts = [split_info["test_dataset_counts"].get(d, 0) for d in datasets]

    axes[1].bar(x - width, tr_counts, width, label="Train", color="#3498db")
    axes[1].bar(x, va_counts, width, label="Val", color="#f39c12")
    axes[1].bar(x + width, te_counts, width, label="Test", color="#e74c3c")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(datasets)
    axes[1].set_title("Veri Seti Bazlı Dağılım (Dataset Composition)", fontweight="bold")
    axes[1].set_ylabel("Kayıt")
    axes[1].legend()

    fig.suptitle("Veri Bölünmesi Özeti (Data Split Summary)", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


def plot_confidence_histogram(y_prob, y_true, title, save_path):
    """Rapor paketinde kullanılacak ilgili grafiği dosyaya kaydeder."""
    if y_prob is None or len(y_prob) == 0:
        return
    fig, ax = plt.subplots(figsize=(9, 6))

    pos_mask = y_true == 1
    neg_mask = y_true == 0

    if pos_mask.sum() > 0:
        ax.hist(y_prob[pos_mask], bins=50, alpha=0.6, color="#e74c3c", label="Pozitif (Actual=1)", edgecolor="white")
    if neg_mask.sum() > 0:
        ax.hist(y_prob[neg_mask], bins=50, alpha=0.6, color="#3498db", label="Negatif (Actual=0)", edgecolor="white")

    ax.axvline(x=0.5, color="k", linestyle="--", alpha=0.5, label="Threshold=0.5")
    ax.set_xlabel("Model Güven Olasılığı (Predicted Probability)")
    ax.set_ylabel("Frekans")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


def plot_threshold_analysis(y_true, y_score, task_name, save_path):
    """Rapor paketinde kullanılacak ilgili grafiği dosyaya kaydeder."""
    if y_score is None or len(np.unique(y_true)) < 2:
        return
    thresholds = np.linspace(0.05, 0.95, 100)
    f1s, precs, recs, specs, mccs = [], [], [], [], []

    for t in thresholds:
        preds = (y_score > t).astype(int)
        f1s.append(f1_score(y_true, preds, zero_division=0))
        precs.append(precision_score(y_true, preds, zero_division=0))
        recs.append(recall_score(y_true, preds, zero_division=0))
        cm = confusion_matrix(y_true, preds, labels=[0, 1])
        if cm.shape == (2, 2):
            tn, fp, fn, tp = cm.ravel()
            specs.append(tn / max(tn + fp, 1))
        else:
            specs.append(0)
        mccs.append(safe_metric(matthews_corrcoef, y_true, preds))

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(thresholds, f1s, "b-", linewidth=2, label="F1")
    ax.plot(thresholds, precs, "g--", linewidth=1.5, label="Precision")
    ax.plot(thresholds, recs, "r--", linewidth=1.5, label="Recall")
    ax.plot(thresholds, specs, "m--", linewidth=1.5, label="Specificity")
    ax.plot(thresholds, mccs, "c-", linewidth=1.5, label="MCC")
    ax.set_xlabel("Threshold")
    ax.set_ylabel("Score")
    ax.set_title(f"Threshold Analizi — {task_name}", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim([0, 1])
    ax.set_ylim([-0.1, 1.05])
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


def _get_metric(m, *keys, default=0):
    """İstenen veriyi ilgili kaynaktan okuyup çağırana döndürür."""
    for k in keys:
        if k in m:
            v = m[k]
            if isinstance(v, float) and np.isnan(v):
                return default
            return v
    return default


def plot_metrics_summary_bar(all_task_metrics, save_path):
    """Rapor paketinde kullanılacak ilgili grafiği dosyaya kaydeder."""
    tasks = list(all_task_metrics.keys())
    metric_keys = ["F1", "Precision", "Recall", "MCC", "AUC", "Specificity"]

    fig, ax = plt.subplots(figsize=(14, 7))
    x = np.arange(len(metric_keys))
    width = 0.8 / max(len(tasks), 1)
    colors = ["#3498db", "#e74c3c", "#2ecc71", "#9b59b6", "#f39c12"]

    for i, task in enumerate(tasks):
        m = all_task_metrics[task]
        vals = [
            _get_metric(m, "f1", "F1_macro", "F1_weighted"),
            _get_metric(m, "precision", "Precision_macro"),
            _get_metric(m, "recall", "Recall_macro", "sensitivity", "Sensitivity_pos"),
            _get_metric(m, "mcc", "MCC"),
            _get_metric(m, "auc", "ROC_AUC"),
            _get_metric(m, "specificity", "Specificity_neg"),
        ]
        bars = ax.bar(x + i * width, vals, width, label=task, color=colors[i % len(colors)])
        for bar, val in zip(bars, vals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                        f"{val:.2f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x + width * (len(tasks) - 1) / 2)
    ax.set_xticklabels(metric_keys, fontsize=11)
    ax.set_ylabel("Score")
    ax.set_title("Görev Bazlı Metrik Karşılaştırması (Task-wise Metrics Comparison)",
                 fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.set_ylim(0, 1.15)
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


# ============================================================
# METRIC COMPUTATION FOR MULTITASK
# ============================================================
def compute_full_binary_metrics(y_true, y_prob, threshold=0.5):
    """İlgili metrik veya risk değerini verilen girdilerden hesaplar."""
    y_pred = (y_prob > threshold).astype(int)
    metrics = {}
    metrics["accuracy"] = safe_metric(accuracy_score, y_true, y_pred)
    metrics["balanced_accuracy"] = safe_metric(balanced_accuracy_score, y_true, y_pred)
    metrics["precision"] = safe_metric(precision_score, y_true, y_pred, zero_division=0)
    metrics["recall"] = safe_metric(recall_score, y_true, y_pred, zero_division=0)
    metrics["f1"] = safe_metric(f1_score, y_true, y_pred, zero_division=0)
    metrics["macro_f1"] = safe_metric(f1_score, y_true, y_pred, average="macro", zero_division=0)
    metrics["weighted_f1"] = safe_metric(f1_score, y_true, y_pred, average="weighted", zero_division=0)
    metrics["mcc"] = safe_metric(matthews_corrcoef, y_true, y_pred)
    metrics["kappa"] = safe_metric(cohen_kappa_score, y_true, y_pred)

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    if cm.shape == (2, 2):
        tn, fp, fn, tp = cm.ravel()
        metrics["tp"] = int(tp)
        metrics["fp"] = int(fp)
        metrics["fn"] = int(fn)
        metrics["tn"] = int(tn)
        metrics["sensitivity"] = float(tp / max(tp + fn, 1))
        metrics["specificity"] = float(tn / max(tn + fp, 1))
        metrics["support_pos"] = int(tp + fn)
        metrics["support_neg"] = int(tn + fp)

    if y_prob is not None and len(np.unique(y_true)) > 1:
        metrics["auc"] = safe_metric(roc_auc_score, y_true, y_prob)
        metrics["pr_auc"] = safe_metric(average_precision_score, y_true, y_prob)

    metrics["threshold"] = threshold
    return metrics


def compute_full_regression_metrics(y_true, y_pred):
    """İlgili metrik veya risk değerini verilen girdilerden hesaplar."""
    metrics = {}
    metrics["mse"] = safe_metric(mean_squared_error, y_true, y_pred)
    metrics["rmse"] = float(np.sqrt(max(metrics["mse"], 0)))
    metrics["mae"] = safe_metric(mean_absolute_error, y_true, y_pred)
    metrics["r2"] = safe_metric(r2_score, y_true, y_pred)
    try:
        metrics["pearson_r"], metrics["pearson_p"] = pearsonr(y_true, y_pred)
        metrics["spearman_r"], metrics["spearman_p"] = spearmanr(y_true, y_pred)
    except Exception:
        metrics["pearson_r"] = metrics["pearson_p"] = float("nan")
        metrics["spearman_r"] = metrics["spearman_p"] = float("nan")
    return metrics


# ============================================================
# PREDICTION ANALYSIS
# ============================================================
def prediction_case_analysis(y_true, y_prob, threshold, task_name, n_samples=10):
    """generate report bundle dosyasındaki backend yardımcı işlemini yürütür."""
    y_pred = (y_prob > threshold).astype(int)
    cases = []

    # True positive examples
    tp_idx = np.where((y_true == 1) & (y_pred == 1))[0]
    for i in tp_idx[:n_samples]:
        cases.append({"sample": int(i), "true": 1, "pred": 1, "prob": round(float(y_prob[i]), 4),
                       "type": "True Positive", "task": task_name})

    # False negative (critical in health!)
    fn_idx = np.where((y_true == 1) & (y_pred == 0))[0]
    for i in fn_idx[:n_samples]:
        cases.append({"sample": int(i), "true": 1, "pred": 0, "prob": round(float(y_prob[i]), 4),
                       "type": "False Negative (KAÇIRILAN)", "task": task_name})

    # False positive
    fp_idx = np.where((y_true == 0) & (y_pred == 1))[0]
    for i in fp_idx[:n_samples]:
        cases.append({"sample": int(i), "true": 0, "pred": 1, "prob": round(float(y_prob[i]), 4),
                       "type": "False Positive", "task": task_name})

    # True negative
    tn_idx = np.where((y_true == 0) & (y_pred == 0))[0]
    for i in tn_idx[:n_samples]:
        cases.append({"sample": int(i), "true": 0, "pred": 0, "prob": round(float(y_prob[i]), 4),
                       "type": "True Negative", "task": task_name})

    # High confidence errors
    errors = np.where(y_true != y_pred)[0]
    if len(errors) > 0:
        max_prob_at_error = y_prob[errors]
        # Sort by most confident wrong prediction
        sorted_err = errors[np.argsort(-np.abs(max_prob_at_error - 0.5))]
        for i in sorted_err[:5]:
            cases.append({"sample": int(i), "true": int(y_true[i]), "pred": int(y_pred[i]),
                           "prob": round(float(y_prob[i]), 4),
                           "type": "Yüksek Güvenli Hata (High Confidence Error)", "task": task_name})

    return cases


# ============================================================
# CONFIG COPY
# ============================================================
def copy_configs():
    """generate report bundle dosyasındaki backend yardımcı işlemini yürütür."""
    config_dir = HEALTHALERT_AI_ROOT / "config"
    for yaml_file in config_dir.glob("*.yaml"):
        import shutil
        shutil.copy2(yaml_file, CONFIG_DIR / yaml_file.name)
    print("  Config files copied to report bundle.")


# ============================================================
# MAIN REPORT GENERATOR
# ============================================================
def generate_report_bundle():
    """Model değerlendirme çıktıları ve görsellerinden rapor paketini üretir."""
    print("\n" + "#" * 70)
    print("#  HealthAlert — Rapor Paketi Üretimi Başlıyor")
    print("#" * 70)

    ensure_dirs()
    copy_configs()

    # ── A. Multi-Task Model ──────────────────────────────────────
    mt_result = evaluate_multitask_model()

    # ── B. HIFD CRNN ─────────────────────────────────────────────
    hifd_result = run_hifd_crnn()

    all_task_summary = {}

    # ============================================================
    # GENERATE MULTITASK MODEL OUTPUTS
    # ============================================================
    if mt_result is not None:
        print("\n  Generating multi-task model report outputs...")
        all_out = mt_result["all_out"]
        all_tgt = mt_result["all_tgt"]
        calibrated = mt_result["calibrated"]
        split_info = mt_result["split_info"]
        ckpt_info = mt_result["ckpt_info"]

        # === CLASSIFICATION TASKS ===
        for task_name, display_name in [
            ("fall", "Düşme Tespiti (Fall Detection)"),
            ("instability", "Dengesizlik Tespiti (Instability Detection)"),
            ("quality", "PPG Kalite (PPG Quality)"),
        ]:
            y_prob = all_out[task_name]
            y_true = all_tgt[task_name].astype(int)
            threshold = calibrated.get(task_name, 0.5)

            if len(y_prob) == 0 or len(np.unique(y_true)) < 2:
                print(f"    [SKIP] {task_name}: insufficient data or single class")
                continue

            y_pred = (y_prob > threshold).astype(int)
            metrics = compute_full_binary_metrics(y_true, y_prob, threshold)
            all_task_summary[display_name] = metrics

            # Save metrics CSV
            save_csv(METRICS_DIR / f"task_metrics_{task_name}.csv",
                     [{"metric": k, "value": v} for k, v in sorted(metrics.items())])

            # Confusion Matrix
            plot_confusion_matrix(y_true, y_pred, ["Negatif (0)", "Pozitif (1)"],
                                  f"Confusion Matrix — {display_name}",
                                  CM_DIR / f"confusion_matrix_{task_name}.png")
            plot_confusion_matrix(y_true, y_pred, ["Negatif (0)", "Pozitif (1)"],
                                  f"Normalized Confusion Matrix — {display_name}",
                                  CM_DIR / f"confusion_matrix_{task_name}_normalized.png",
                                  normalize=True)

            # ROC Curve
            plot_roc_curve(y_true, y_prob, f"ROC Eğrisi — {display_name}",
                           CURVES_DIR / f"roc_curve_{task_name}.png")

            # PR Curve
            plot_pr_curve(y_true, y_prob, f"Precision-Recall Eğrisi — {display_name}",
                          CURVES_DIR / f"pr_curve_{task_name}.png")

            # Confidence Histogram
            plot_confidence_histogram(y_prob, y_true, f"Güven Dağılımı — {display_name}",
                                      FIGURES_DIR / f"confidence_hist_{task_name}.png")

            # Threshold Analysis
            plot_threshold_analysis(y_true, y_prob, display_name,
                                    CURVES_DIR / f"threshold_analysis_{task_name}.png")

            # Prediction case analysis
            cases = prediction_case_analysis(y_true, y_prob, threshold, task_name)
            save_csv(PRED_DIR / f"case_analysis_{task_name}.csv", cases)

            print(f"    {task_name}: F1={metrics['f1']:.4f} AUC={metrics.get('auc', 0):.4f} "
                  f"MCC={metrics['mcc']:.4f} Sens={metrics.get('sensitivity', 0):.4f}")

        # === RISK REGRESSION ===
        risk_pred = all_out["risk"]
        risk_true = all_tgt["risk"]
        if len(risk_pred) > 0:
            risk_metrics = compute_full_regression_metrics(risk_true, risk_pred)
            all_task_summary["Risk Skoru (Risk Score)"] = risk_metrics

            save_csv(METRICS_DIR / "task_metrics_risk.csv",
                     [{"metric": k, "value": v} for k, v in sorted(risk_metrics.items())])

            plot_scatter_regression(risk_true, risk_pred,
                                   "Risk Skoru — Tahmin vs Gerçek (Predicted vs Actual)",
                                   FIGURES_DIR / "regression_risk_scatter.png")
            plot_residuals(risk_true, risk_pred, "Risk Skoru — Artık Analizi (Residual Analysis)",
                           FIGURES_DIR / "regression_risk_residuals.png")

            print(f"    risk: MAE={risk_metrics['mae']:.4f} RMSE={risk_metrics['rmse']:.4f} "
                  f"R²={risk_metrics['r2']:.4f}")

        # === DATA SPLIT GRAPHICS ===
        plot_class_distribution(split_info, SPLIT_DIR / "class_distribution.png")
        plot_dataset_split_summary(split_info, SPLIT_DIR / "dataset_split_summary.png")

        # Save split info
        save_json(SPLIT_DIR / "split_info.json", split_info)
        split_rows = [
            {"set": "Train", "records": split_info["train_records"],
             "windows": split_info["train_windows"],
             "subjects": len(split_info["train_subjects"])},
            {"set": "Validation", "records": split_info["val_records"],
             "windows": split_info["val_windows"],
             "subjects": len(split_info["val_subjects"])},
            {"set": "Test", "records": split_info["test_records"],
             "windows": split_info["test_windows"],
             "subjects": len(split_info["test_subjects"])},
        ]
        save_csv(SPLIT_DIR / "split_summary.csv", split_rows)

        # Save checkpoint info
        save_json(CKPT_DIR / "multitask_checkpoint_info.json", ckpt_info)
        ckpt_rows = [{"parameter": k, "value": str(v)} for k, v in sorted(ckpt_info.items())]
        save_csv(CKPT_DIR / "multitask_checkpoint_info.csv", ckpt_rows)

        # Threshold comparison table
        threshold_rows = []
        for task in ["fall", "instability", "quality"]:
            y_true = all_tgt[task].astype(int)
            y_prob = all_out[task]
            if len(y_prob) == 0 or len(np.unique(y_true)) < 2:
                continue
            for t in [0.3, 0.4, 0.5, 0.6, 0.7]:
                preds = (y_prob > t).astype(int)
                threshold_rows.append({
                    "task": task,
                    "threshold": t,
                    "accuracy": round(accuracy_score(y_true, preds), 4),
                    "f1": round(f1_score(y_true, preds, zero_division=0), 4),
                    "precision": round(precision_score(y_true, preds, zero_division=0), 4),
                    "recall": round(recall_score(y_true, preds, zero_division=0), 4),
                    "mcc": round(safe_metric(matthews_corrcoef, y_true, preds), 4),
                })
        save_csv(METRICS_DIR / "threshold_comparison.csv", threshold_rows)

    # ============================================================
    # GENERATE HIFD CRNN OUTPUTS
    # ============================================================
    if hifd_result is not None:
        print("\n  Generating HIFD CRNN report outputs...")
        y_true = hifd_result["y_true"]
        y_pred = hifd_result["y_pred"]
        y_score = hifd_result["y_score"]
        class_names = hifd_result["class_names"]
        fm = hifd_result["final_metrics"]

        all_task_summary["HIFD CRNN (Fall Detection)"] = fm

        # Metrics CSV
        save_csv(METRICS_DIR / "task_metrics_hifd_crnn.csv",
                 [{"metric": k, "value": v} for k, v in sorted(fm.items())])

        # Confusion matrices
        plot_confusion_matrix(y_true, y_pred, class_names,
                              "Confusion Matrix — HIFD CRNN Fall Detection",
                              CM_DIR / "confusion_matrix_hifd_crnn.png")
        plot_confusion_matrix(y_true, y_pred, class_names,
                              "Normalized CM — HIFD CRNN",
                              CM_DIR / "confusion_matrix_hifd_crnn_normalized.png",
                              normalize=True)

        # ROC / PR (binary only)
        if y_score is not None and len(class_names) == 2:
            plot_roc_curve(y_true, y_score, "ROC — HIFD CRNN Fall Detection",
                           CURVES_DIR / "roc_curve_hifd_crnn.png")
            plot_pr_curve(y_true, y_score, "PR — HIFD CRNN Fall Detection",
                          CURVES_DIR / "pr_curve_hifd_crnn.png")
            plot_threshold_analysis(y_true, y_score, "HIFD CRNN",
                                    CURVES_DIR / "threshold_analysis_hifd_crnn.png")
            plot_confidence_histogram(y_score, y_true, "Güven Dağılımı — HIFD CRNN",
                                      FIGURES_DIR / "confidence_hist_hifd_crnn.png")

        # Loss & metric curves
        plot_loss_curves(hifd_result["train_losses"], hifd_result["val_losses"],
                         "HIFD CRNN — Loss Eğrileri (Train vs Val)",
                         FIGURES_DIR / "hifd_crnn_loss_curves.png")
        plot_metric_curves(hifd_result["val_metrics_history"],
                           "HIFD CRNN — Doğrulama Metrikleri (Val Metrics per Epoch)",
                           FIGURES_DIR / "hifd_crnn_val_metrics.png")

        # HIFD CRNN checkpoint info
        save_json(CKPT_DIR / "hifd_crnn_info.json", {
            "model": "CRNN (PPG-CNN + IMU-CNN + BiLSTM)",
            "trainable_params": hifd_result["n_params"],
            "best_epoch": hifd_result["best_epoch"],
            "best_val_f1_macro": hifd_result["best_f1"],
            "eval_split": hifd_result["eval_split"],
            "classes": class_names,
            "config": hifd_result["config"],
            "subjects": hifd_result["subjects"],
            "split_counts": hifd_result["split_counts"],
        })

    # ============================================================
    # SUMMARY METRICS TABLE (ALL TASKS)
    # ============================================================
    print("\n  Generating summary tables...")

    # Summary metrics CSV
    summary_rows = []
    for task_name, metrics in all_task_summary.items():
        row = {"task": task_name}
        row.update({k: round(v, 4) if isinstance(v, float) and not np.isnan(v) else v
                    for k, v in metrics.items()})
        summary_rows.append(row)
    save_csv(SUMMARY_DIR / "summary_metrics.csv", summary_rows)
    save_json(SUMMARY_DIR / "summary_metrics.json", all_task_summary)

    # Overall metrics comparison bar chart
    bar_metrics = {}
    for task_name, metrics in all_task_summary.items():
        if "f1" in metrics or "F1_macro" in metrics:
            bar_metrics[task_name] = metrics
    if bar_metrics:
        plot_metrics_summary_bar(bar_metrics, FIGURES_DIR / "overall_metrics_comparison.png")

    # ============================================================
    # REPORT TEXT — RAPORA KOYULMAYA HAZIR METİN
    # ============================================================
    report_lines = []
    report_lines.append("# HealthAlert — Model Değerlendirme Raporu")
    report_lines.append(f"\nRapor Tarihi: {time.strftime('%Y-%m-%d %H:%M')}")
    report_lines.append("")

    report_lines.append("## 1. Genel Bakış")
    report_lines.append("")
    report_lines.append("Bu rapor, HealthAlert projesinin AI/ML bileşenlerinin eğitim ve test "
                        "değerlendirme sonuçlarını içermektedir. İki ana model değerlendirilmiştir:")
    report_lines.append("")
    report_lines.append("1. **HealthAlertModelV2 (Multi-Task)**: 4 görevli çok modlu model "
                        "(Düşme Tespiti, Dengesizlik, PPG Kalite, Risk Skoru)")
    report_lines.append("2. **HIFD CRNN**: HIFD veri seti üzerinde eğitilmiş ikili düşme tespiti modeli")
    report_lines.append("")

    if mt_result:
        ckpt_info = mt_result["ckpt_info"]
        split_info = mt_result["split_info"]
        report_lines.append("## 2. Multi-Task Model Özeti")
        report_lines.append("")
        report_lines.append(f"- **Model**: {ckpt_info['model_name']}")
        report_lines.append(f"- **Mimari**: {ckpt_info['architecture']}")
        report_lines.append(f"- **Toplam Parametre**: {ckpt_info['total_params']:,}")
        report_lines.append(f"- **Eğitilebilir Parametre**: {ckpt_info['trainable_params']:,}")
        report_lines.append(f"- **Optimizer**: {ckpt_info['optimizer']} (lr={ckpt_info['learning_rate']})")
        report_lines.append(f"- **Scheduler**: {ckpt_info['scheduler']}")
        report_lines.append(f"- **Batch Size**: {ckpt_info['batch_size']}")
        report_lines.append(f"- **Checkpoint Epoch**: {ckpt_info['checkpoint_epoch']}")
        report_lines.append(f"- **Eğitim Aşaması**: {ckpt_info['checkpoint_stage']}")
        report_lines.append("")

        report_lines.append("### 2.1 Veri Bölünmesi")
        report_lines.append("")
        report_lines.append(f"- **Toplam Kayıt**: {split_info['total_records']}")
        report_lines.append(f"- **Train**: {split_info['train_records']} kayıt ({len(split_info['train_subjects'])} kişi)")
        report_lines.append(f"- **Validation**: {split_info['val_records']} kayıt ({len(split_info['val_subjects'])} kişi)")
        report_lines.append(f"- **Test**: {split_info['test_records']} kayıt ({len(split_info['test_subjects'])} kişi)")
        report_lines.append(f"- **Strateji**: Subject-wise split (veri sızıntısı önlendi)")
        report_lines.append(f"- **Pencere Boyutu**: {split_info['window_size']} örnek ({split_info['window_size']/50:.1f}s @ 50Hz)")
        report_lines.append(f"- **Adım (Stride)**: {split_info['stride']} örnek ({split_info['stride']/50:.1f}s)")
        report_lines.append("")

        report_lines.append("### 2.2 Görev Bazlı Test Sonuçları")
        report_lines.append("")

        # Table header
        report_lines.append("| Görev | F1 | Precision | Recall | MCC | AUC | Specificity |")
        report_lines.append("|-------|------|-----------|--------|------|------|-------------|")

        for task_name, metrics in all_task_summary.items():
            if "Risk" in task_name and "f1" not in metrics:
                continue
            f1_val = metrics.get("f1", metrics.get("F1_macro", "-"))
            prec = metrics.get("precision", metrics.get("Precision_macro", "-"))
            rec = metrics.get("recall", metrics.get("Recall_macro", "-"))
            mcc = metrics.get("mcc", metrics.get("MCC", "-"))
            auc = metrics.get("auc", metrics.get("ROC_AUC", "-"))
            spec = metrics.get("specificity", metrics.get("Specificity_neg", "-"))

            def fmt(v):
                """generate report bundle dosyasındaki backend yardımcı işlemini yürütür."""
                return f"{v:.4f}" if isinstance(v, (int, float)) and not (isinstance(v, float) and np.isnan(v)) else str(v)

            report_lines.append(f"| {task_name} | {fmt(f1_val)} | {fmt(prec)} | {fmt(rec)} | {fmt(mcc)} | {fmt(auc)} | {fmt(spec)} |")

        report_lines.append("")

        # Risk Score section
        if "Risk Skoru (Risk Score)" in all_task_summary:
            rm = all_task_summary["Risk Skoru (Risk Score)"]
            report_lines.append("### 2.3 Risk Skoru (Regression) Sonuçları")
            report_lines.append("")
            report_lines.append(f"| Metrik | Değer |")
            report_lines.append(f"|--------|-------|")
            report_lines.append(f"| MAE | {rm['mae']:.4f} |")
            report_lines.append(f"| MSE | {rm['mse']:.4f} |")
            report_lines.append(f"| RMSE | {rm['rmse']:.4f} |")
            report_lines.append(f"| R² | {rm['r2']:.4f} |")
            report_lines.append(f"| Pearson r | {rm.get('pearson_r', 'N/A')} |")
            report_lines.append(f"| Spearman ρ | {rm.get('spearman_r', 'N/A')} |")
            report_lines.append("")

    # HIFD CRNN section
    if hifd_result:
        report_lines.append("## 3. HIFD CRNN Model Sonuçları")
        report_lines.append("")
        fm = hifd_result["final_metrics"]
        report_lines.append(f"- **Model**: CRNN (PPG-CNN + IMU-CNN + BiLSTM)")
        report_lines.append(f"- **Parametre Sayısı**: {hifd_result['n_params']:,}")
        report_lines.append(f"- **En İyi Epoch**: {hifd_result['best_epoch']}")
        report_lines.append(f"- **Sınıflar**: {hifd_result['class_names']}")
        report_lines.append(f"- **Değerlendirme Seti**: {hifd_result['eval_split']}")
        report_lines.append("")

        report_lines.append("| Metrik | Değer |")
        report_lines.append("|--------|-------|")
        for k, v in sorted(fm.items()):
            vstr = f"{v:.4f}" if isinstance(v, float) else str(v)
            report_lines.append(f"| {k} | {vstr} |")
        report_lines.append("")

    # Technical commentary
    report_lines.append("## 4. Teknik Yorumlar")
    report_lines.append("")

    comments = []
    if mt_result and "Düşme Tespiti (Fall Detection)" in all_task_summary:
        fm = all_task_summary["Düşme Tespiti (Fall Detection)"]
        sens = fm.get("sensitivity", fm.get("recall", 0))
        spec = fm.get("specificity", 0)
        if sens > 0.8:
            comments.append(f"- **Düşme Tespiti**: Model yüksek sensitivity ({sens:.4f}) üretmiştir. "
                           "Bu, kritik düşme olaylarını kaçırmama açısından önemli bir avantaj sağlar. "
                           "Sağlık uygulamalarında false negative oranının düşük tutulması hayati önem taşır.")
        else:
            comments.append(f"- **Düşme Tespiti**: Sensitivity ({sens:.4f}) orta düzeydedir. "
                           "Klinik ortamda kullanım için threshold ayarlaması gerekebilir.")

        if fm.get("fp", 0) > fm.get("tp", 0):
            comments.append("- **Düşme Tespiti — False Positive**: False positive sayısı yüksektir. "
                           "Bu, kullanıcıya gereksiz alarm gönderilmesine yol açabilir. "
                           "Threshold yükseltilerek precision artırılabilir ancak recall düşebilir.")

    if mt_result and "Dengesizlik Tespiti (Instability Detection)" in all_task_summary:
        fm = all_task_summary["Dengesizlik Tespiti (Instability Detection)"]
        f1_val = fm.get("f1", 0)
        if f1_val < 0.7:
            comments.append(f"- **Dengesizlik Tespiti**: F1 değeri ({f1_val:.4f}) düşme tespitine göre daha düşüktür. "
                           "Bu görev için ground truth etiketler, düşme öncesi anlardan türetilmiş proxy label olduğundan, "
                           "etiket belirsizliği performansı sınırlamaktadır.")
        else:
            comments.append(f"- **Dengesizlik Tespiti**: F1={f1_val:.4f}. Kabul edilebilir düzeydedir.")

    if mt_result and "PPG Kalite (PPG Quality)" in all_task_summary:
        fm = all_task_summary["PPG Kalite (PPG Quality)"]
        f1_val = fm.get("f1", 0)
        if f1_val > 0.95:
            comments.append(f"- **PPG Kalite**: Mükemmel performans (F1={f1_val:.4f}). "
                           "BUT_PPG veri seti kalite etiketleri açık olduğundan model bu görevi yüksek doğrulukla öğrenmiştir. "
                           "Quality gate mekanizması güvenle kullanılabilir.")
        else:
            comments.append(f"- **PPG Kalite**: F1={f1_val:.4f}. PPG sinyal kalitesi değişkenliği performansı etkilemiştir.")

    if mt_result and "Risk Skoru (Risk Score)" in all_task_summary:
        rm = all_task_summary["Risk Skoru (Risk Score)"]
        mae = rm.get("mae", 1)
        comments.append(f"- **Risk Skoru**: MAE={mae:.4f}, RMSE={rm.get('rmse', 0):.4f}. "
                       "Risk etiketi proxy label (düşme + vital değerlerden türetilmiş) olduğundan, "
                       "hata dağılımı orta düzeydedir. Model genel risk eğilimini yakalamaktadır.")

    if hifd_result:
        fm = hifd_result["final_metrics"]
        f1m = fm.get("F1_macro", 0)
        mcc = fm.get("MCC", 0)
        comments.append(f"- **HIFD CRNN**: Macro F1={f1m:.4f}, MCC={mcc:.4f}. "
                       "Yalnızca HIFD veri seti üzerinde eğitilmiş ikili sınıflandırıcı. "
                       "Daha basit mimari olmasına rağmen düşme tespitinde tutarlı sonuçlar üretmektedir.")

    if not comments:
        comments.append("- Yeterli veri ile değerlendirme yapılamamıştır.")

    report_lines.extend(comments)
    report_lines.append("")

    report_lines.append("## 5. Confusion Matrix Yorumu")
    report_lines.append("")
    if mt_result and "Düşme Tespiti (Fall Detection)" in all_task_summary:
        fm = all_task_summary["Düşme Tespiti (Fall Detection)"]
        tp, fp = fm.get("tp", 0), fm.get("fp", 0)
        fn, tn = fm.get("fn", 0), fm.get("tn", 0)
        comments_cm = []
        if fp > tp * 0.3:
            comments_cm.append(f"- Düşme tespitinde {fp} false positive gözlenmiştir. "
                              "Bazı normal hareketler düşme olarak sınıflandırılmaktadır.")
        if fn > 0:
            comments_cm.append(f"- {fn} false negative durumda model gerçek düşmeyi tespit edememiştir. "
                              "Sağlık uygulamalarında bu kritik bir risktir.")
        if not comments_cm:
            comments_cm.append("- Confusion matrix dengeli bir performans göstermektedir.")
        report_lines.extend(comments_cm)
    report_lines.append("")

    report_lines.append("## 6. Öneriler")
    report_lines.append("")
    report_lines.append("1. Düşme tespiti için threshold optimizasyonu yapılarak precision-recall "
                        "dengesi klinik ihtiyaçlara göre ayarlanabilir.")
    report_lines.append("2. Dengesizlik tespiti için daha fazla etiketli veri veya "
                        "daha sofistike proxy label stratejisi geliştirilebilir.")
    report_lines.append("3. Modelin farklı yaş grupları/cinsiyet/fiziksel özellikler "
                        "üzerindeki performansı ayrıca incelenmelidir.")
    report_lines.append("4. Risk skoru hesaplaması için daha zengin temporal context "
                        "(daha uzun pencere) denenebilir.")
    report_lines.append("")

    report_lines.append("## 7. Dosya Listesi")
    report_lines.append("")
    report_lines.append("```")
    report_lines.append("report_bundle/")
    for d in ALL_DIRS:
        rel = d.relative_to(BUNDLE_DIR)
        report_lines.append(f"  {rel}/")
        if d.exists():
            for f in sorted(d.iterdir()):
                report_lines.append(f"    {f.name}")
    report_lines.append("```")

    report_text = "\n".join(report_lines)
    save_text(REPORT_DIR / "report_ready_summary.md", report_text)
    save_text(SUMMARY_DIR / "report_ready_summary.md", report_text)
    print(f"\n  Report text saved to {REPORT_DIR / 'report_ready_summary.md'}")

    # ============================================================
    # FINAL CONSOLE SUMMARY
    # ============================================================
    print("\n" + "=" * 70)
    print("  RAPOR PAKETİ TAMAMLANDI")
    print("=" * 70)
    print(f"\n  Klasör: {BUNDLE_DIR}")
    print()

    file_count = 0
    for d in ALL_DIRS:
        if d.exists():
            files = list(d.iterdir())
            file_count += len(files)
            print(f"  {d.relative_to(BUNDLE_DIR)}/  ({len(files)} dosya)")
            for f in sorted(files):
                print(f"    - {f.name}")

    print(f"\n  Toplam: {file_count} dosya uretildi.")
    print()

    # Quick summary of best results
    print("  == EN ONEMLI SONUCLAR ==")
    for task_name, metrics in all_task_summary.items():
        if "f1" in metrics:
            print(f"    {task_name}: F1={metrics['f1']:.4f}")
        elif "F1_macro" in metrics:
            print(f"    {task_name}: Macro F1={metrics['F1_macro']:.4f}")
        elif "rmse" in metrics:
            print(f"    {task_name}: RMSE={metrics['rmse']:.4f}")
    print()
    print("  RAPOR PAKETI BASARIYLA TAMAMLANDI.")


if __name__ == "__main__":
    generate_report_bundle()
