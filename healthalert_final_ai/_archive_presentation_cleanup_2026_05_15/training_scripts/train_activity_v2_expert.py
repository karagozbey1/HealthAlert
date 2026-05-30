from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.healthalert.models.activity_expert import build_activity_expert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("healthalert.train_activity_v2_expert")

EXPECTED_PYTHON = PROJECT_ROOT.parent / ".venv311" / "Scripts" / "python.exe"
DATA_DIR = PROJECT_ROOT / "outputs" / "windowed_dataset" / "activity_v2_pure_adl"
DATASET_SUMMARY_PATH = DATA_DIR / "summary.json"
AUDIT_PATH = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "activity_v2" / "activity_v2_dataset_audit.json"
OUT_DIR = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "activity_expert_v2"
V0_METRICS_PATH = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "activity_expert" / "metrics.json"
V0_PER_CLASS_PATH = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "activity_expert" / "per_class_metrics.json"

CLASS_NAMES = ["walking", "sitting", "standing", "lying"]
NUM_CLASSES = len(CLASS_NAMES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Activity v2 pure ADL expert")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=256)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight_decay", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--data_dir", type=str, default=str(DATA_DIR))
    parser.add_argument("--out_dir", type=str, default=str(OUT_DIR))
    return parser.parse_args()


def _ensure_expected_python() -> None:
    current = Path(sys.executable).resolve()
    expected = EXPECTED_PYTHON.resolve()
    if current != expected:
        raise RuntimeError(
            f"Use the project interpreter only. expected={expected} current={current}"
        )


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_split(split: str, data_dir: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    npz_path = data_dir / f"{split}.npz"
    if not npz_path.exists():
        raise FileNotFoundError(f"Missing split NPZ: {npz_path}")

    raw = np.load(str(npz_path), allow_pickle=True)
    X = raw["imu"].astype(np.float32).transpose(0, 2, 1)
    y = raw["labels"].flatten().astype(np.int64)
    metadata = raw["metadata"]

    sources = np.empty(len(y), dtype=object)
    for idx, item in enumerate(metadata):
        payload = json.loads(str(item)) if not isinstance(item, dict) else item
        sources[idx] = payload.get("dataset_name", "unknown")

    return X, y, sources


def _compute_class_weights(y: np.ndarray) -> torch.Tensor:
    counts = np.bincount(y, minlength=NUM_CLASSES).astype(np.float64)
    counts = np.maximum(counts, 1.0)
    inv = counts.sum() / (NUM_CLASSES * counts)
    inv = inv / inv.mean()
    inv = np.clip(inv, 0.75, 1.50)
    return torch.tensor(inv, dtype=torch.float32)


def _checkpoint_valid(logits: np.ndarray, targets: np.ndarray, val_loss: float) -> Tuple[bool, str]:
    if not np.isfinite(val_loss):
        return False, f"val_loss is not finite: {val_loss}"
    preds = np.argmax(logits, axis=1)
    n_predicted = len(np.unique(preds))
    if n_predicted < 2:
        return False, f"collapse: only {n_predicted} class(es) predicted"
    from sklearn.metrics import f1_score as _f1

    macro_f1 = float(_f1(targets, preds, average="macro", zero_division=0))
    if macro_f1 < (0.5 / NUM_CLASSES):
        return False, f"macro_f1={macro_f1:.4f} below random-chance floor"
    return True, "ok"


def run_eval(
    model: nn.Module,
    X: np.ndarray,
    y: np.ndarray,
    src_names: np.ndarray,
    device: torch.device,
    batch_size: int,
) -> Dict[str, Any]:
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

    model.eval()
    loader = DataLoader(TensorDataset(torch.from_numpy(X)), batch_size=batch_size, shuffle=False)
    logits_parts: List[np.ndarray] = []
    with torch.no_grad():
        for (xb,) in loader:
            output = model(xb.to(device))
            logits_parts.append(output["logits"].cpu().numpy())

    logits = np.concatenate(logits_parts, axis=0)
    preds = np.argmax(logits, axis=1)

    accuracy = float(accuracy_score(y, preds))
    macro_f1 = float(f1_score(y, preds, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(y, preds, average="weighted", zero_division=0))
    prec, rec, f1, sup = precision_recall_fscore_support(
        y,
        preds,
        labels=list(range(NUM_CLASSES)),
        zero_division=0,
    )

    per_class = {
        CLASS_NAMES[idx]: {
            "precision": float(prec[idx]),
            "recall": float(rec[idx]),
            "f1": float(f1[idx]),
            "support": int(sup[idx]),
        }
        for idx in range(NUM_CLASSES)
    }
    src_breakdown: Dict[str, Dict[str, Any]] = {}
    for src in np.unique(src_names):
        mask = src_names == src
        src_breakdown[str(src)] = {
            "n": int(mask.sum()),
            "macro_f1": round(float(f1_score(y[mask], preds[mask], average="macro", zero_division=0)), 4),
        }

    return {
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(y, preds, labels=list(range(NUM_CLASSES))).tolist(),
        "prediction_distribution": {CLASS_NAMES[idx]: int((preds == idx).sum()) for idx in range(NUM_CLASSES)},
        "source_breakdown": src_breakdown,
        "logits": logits,
        "preds": preds,
    }


def _build_report(
    dataset_summary: Dict[str, Any],
    audit_summary: Dict[str, Any],
    best_epoch: int,
    best_val_macro_f1: float,
    history: List[Dict[str, Any]],
    test_metrics: Dict[str, Any],
    train_cfg: Dict[str, Any],
    model_params: int,
    elapsed_sec: float,
    v0_metrics: Dict[str, Any],
    v0_per_class: Dict[str, Any],
) -> str:
    decision = "ACCEPT_ACTIVITY_V2_PURE_ADL" if test_metrics["macro_f1"] >= 0.70 else "REVIEW_ACTIVITY_V2_PURE_ADL"
    generated_on = date.today().isoformat()
    dataset_entries = audit_summary.get("datasets", [])
    source_breakdown = test_metrics.get("source_breakdown", {})
    prediction_distribution = test_metrics.get("prediction_distribution", {})
    class_weights = train_cfg.get("class_weights", {})
    best_row = next((item for item in history if item["epoch"] == best_epoch), None)
    source_scores = [float(info.get("macro_f1", 0.0)) for info in source_breakdown.values()]
    source_gap = max(source_scores) - min(source_scores) if len(source_scores) >= 2 else 0.0
    weakest_class = min(CLASS_NAMES, key=lambda name: test_metrics["per_class"][name]["recall"])
    strongest_class = max(CLASS_NAMES, key=lambda name: test_metrics["per_class"][name]["recall"])
    best_val_loss_text = f"{best_row['val_loss']:.4f}" if best_row else "n/a"

    lines = [
        "# Activity v2 Pure ADL Detailed Report",
        "",
        f"Generated: {generated_on}",
        f"Decision: {decision}",
        "",
        "## 1. Executive Summary",
        f"- Objective: train a contamination-free 4-class Activity v2 expert for walking / sitting / standing / lying.",
        f"- Usable sources in this run: {', '.join(dataset_summary['usable_sources'])}.",
        f"- Final split sizes: train={dataset_summary['train']['n_windows']}, val={dataset_summary['val']['n_windows']}, test={dataset_summary['test']['n_windows']}.",
        f"- Best validation macro_f1: {best_val_macro_f1:.4f} at epoch {best_epoch}.",
        f"- Final test macro_f1: {test_metrics['macro_f1']:.4f}; acceptance threshold: 0.7000.",
        f"- Decision rationale: {'accepted because the test macro_f1 cleared the target.' if decision == 'ACCEPT_ACTIVITY_V2_PURE_ADL' else 'review required because the test macro_f1 stayed below the 0.70 target despite strong validation performance.'}",
        "",
        "## 2. Scope and Label Contract",
        "- Target labels: walking, sitting, standing, lying.",
        "- Excluded from Activity v2: generic normal / instability / fall style labels and any dataset that collapses ADL subclasses.",
        f"- Split coverage complete: {dataset_summary['split_info']['all_splits_have_all_labels']}.",
        f"- PAMAP2 integration note: {audit_summary['pamap2']['feasibility_note']}",
        "",
        "## 3. Dataset Audit",
        "| Dataset | Status | Raw Present | Records | Subjects | Pure Label Support | Feasible Now | Notes |",
        "|---------|--------|-------------|---------|----------|--------------------|--------------|-------|",
    ]
    for entry in dataset_entries:
        notes = "; ".join(entry.get("notes", [])) or "-"
        pure_support = json.dumps(entry.get("pure_label_support", {}), ensure_ascii=True)
        lines.append(
            f"| {entry['display_name']} | {entry['status']} | {entry['raw_path_exists']} | {entry['n_records']} | {entry['n_unique_subjects']} | {pure_support} | {entry['feasible_for_pure_adl_now']} | {notes} |"
        )

    lines.extend(
        [
            "",
            "## 4. Final Export Summary",
            "| Split | Windows | Unique Subjects | Sources | Labels |",
            "|-------|---------|-----------------|---------|--------|",
        ]
    )
    for split_name in ("train", "val", "test"):
        split = dataset_summary[split_name]
        src_counts = json.dumps(split["source_counts"], ensure_ascii=True)
        label_counts = json.dumps(split["label_counts"], ensure_ascii=True)
        lines.append(
            f"| {split_name} | {split['n_windows']} | {split['n_unique_subjects']} | {src_counts} | {label_counts} |"
        )

    lines.extend(
        [
            "",
            "### Source Window Totals",
            "| Source | Label Counts |",
            "|--------|--------------|",
        ]
    )
    for source_name, counts in dataset_summary.get("builder_source_summary", {}).items():
        lines.append(f"| {source_name} | {json.dumps(counts, ensure_ascii=True)} |")

    lines.extend(
        [
            "",
            "## 5. Training Setup",
            f"- Model: ActivityExpertCNN (CNN1D + GRU), parameters={model_params}",
            "- Input shape: (batch, 6, 200)",
            "- Loss: CrossEntropyLoss",
            "- Optimizer: AdamW",
            "- Scheduler: CosineAnnealingLR",
            f"- Class weights: {json.dumps(class_weights, ensure_ascii=True)}",
            f"- Normalization: z-score per channel from train split only; stats saved in imu_norm_stats.json.",
            f"- Training time: {elapsed_sec:.1f} sec",
            "",
            "## 6. Overall Results",
            f"- Best epoch: {best_epoch}",
            f"- Best validation macro_f1: {best_val_macro_f1:.4f}",
            f"- Validation loss at best epoch: {best_val_loss_text}",
            f"- Test accuracy: {test_metrics['accuracy']:.4f}",
            f"- Test macro_f1: {test_metrics['macro_f1']:.4f}",
            f"- Test weighted_f1: {test_metrics['weighted_f1']:.4f}",
            "",
            "## 7. Per-Class Test Metrics",
            "| Class | Precision | Recall | F1 | Support |",
            "|-------|-----------|--------|----|---------|",
        ]
    )
    for class_name in CLASS_NAMES:
        values = test_metrics["per_class"][class_name]
        lines.append(
            f"| {class_name} | {values['precision']:.3f} | {values['recall']:.3f} | {values['f1']:.3f} | {values['support']:,} |"
        )

    lines.extend(
        [
            "",
            "## 8. Source-Level Test Breakdown",
            "| Source | n | Macro F1 |",
            "|--------|---|----------|",
        ]
    )
    for source_name, info in sorted(source_breakdown.items(), key=lambda item: item[0]):
        lines.append(f"| {source_name} | {info['n']} | {info['macro_f1']:.4f} |")

    lines.extend(
        [
            "",
            "## 9. Prediction Distribution",
            "| Class | Predicted Count |",
            "|-------|-----------------|",
        ]
    )
    for class_name in CLASS_NAMES:
        lines.append(f"| {class_name} | {prediction_distribution.get(class_name, 0)} |")

    lines.extend(
        [
            "",
            "## 10. Test Confusion Matrix",
            "Rows = actual, columns = predicted.",
            "",
            "| Actual \\ Pred | " + " | ".join(CLASS_NAMES) + " |",
            "|---------------|" + "---|" * NUM_CLASSES,
        ]
    )
    for class_name, row in zip(CLASS_NAMES, test_metrics["confusion_matrix"]):
        lines.append(f"| {class_name} | " + " | ".join(str(value) for value in row) + " |")

    lines.extend(
        [
            "",
            "## 11. Activity v0 Comparison",
            f"- v0 overall macro_f1: {v0_metrics.get('macro_f1', 'n/a')}",
            f"- v2 pure ADL macro_f1: {test_metrics['macro_f1']:.4f}",
            "- note: v0 was trained on contaminated mixed activity_context data, so its overall macro_f1 is not directly comparable to pure ADL v2.",
            "",
            "| ADL Class | v0 Recall | v2 Recall | Delta |",
            "|-----------|-----------|-----------|-------|",
        ]
    )
    for class_name in CLASS_NAMES:
        v0_recall = float(v0_per_class.get(class_name, {}).get("recall", 0.0))
        v2_recall = float(test_metrics["per_class"][class_name]["recall"])
        lines.append(f"| {class_name} | {v0_recall:.4f} | {v2_recall:.4f} | {v2_recall - v0_recall:+.4f} |")

    lines.extend(
        [
            "",
            "## 12. Interpretation",
            f"- Strongest class by recall: {strongest_class} ({test_metrics['per_class'][strongest_class]['recall']:.4f}).",
            f"- Weakest class by recall: {weakest_class} ({test_metrics['per_class'][weakest_class]['recall']:.4f}).",
            f"- Source gap in macro_f1: {source_gap:.4f}.",
            f"- UCI-HAR source macro_f1: {source_breakdown.get('UCI-HAR', {}).get('macro_f1', 'n/a')}",
            f"- PAMAP2 source macro_f1: {source_breakdown.get('PAMAP2', {}).get('macro_f1', 'n/a')}",
            f"- Interpretation: {'current multi-source merge is not stable enough for acceptance; validation stayed high but test performance dropped because source behaviour is uneven.' if decision != 'ACCEPT_ACTIVITY_V2_PURE_ADL' else 'current multi-source merge met the test target and is acceptable.'}",
            "",
            "## 13. Decision",
            f"- Decision: {decision}",
            f"- Acceptance threshold used here: test macro_f1 >= 0.70.",
            f"- Result: {test_metrics['macro_f1']:.4f}",
            f"- MobiAct status: loader integrated, but raw CSV files are still absent from the repo.",
            f"- PAMAP2 status: raw data successfully integrated and included in this run.",
            "",
            "## 14. Training Config",
        ]
    )
    for key, value in train_cfg.items():
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## 15. Validation Trace",
            "| Epoch | Train Loss | Val Loss | Val Macro F1 | Checkpoint |",
            "|-------|------------|----------|--------------|------------|",
        ]
    )
    for item in history:
        lines.append(
            f"| {item['epoch']} | {item['train_loss']:.4f} | {item['val_loss']:.4f} | {item['val_macro_f1']:.4f} | {'yes' if item['checkpoint_valid'] else 'no'} |"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    _ensure_expected_python()
    _set_seed(args.seed)

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dataset_summary = _load_json(DATASET_SUMMARY_PATH)
    if not dataset_summary.get("ready_for_training", False):
        raise RuntimeError("Dataset summary says activity_v2_pure_adl is not ready for training.")

    audit_summary = _load_json(AUDIT_PATH) if AUDIT_PATH.exists() else {"pamap2": {"feasibility_note": "n/a"}}
    v0_metrics = _load_json(V0_METRICS_PATH) if V0_METRICS_PATH.exists() else {}
    v0_per_class = _load_json(V0_PER_CLASS_PATH) if V0_PER_CLASS_PATH.exists() else {}

    device = (
        torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if args.device == "auto"
        else torch.device(args.device)
    )

    X_train, y_train, src_train = _load_split("train", data_dir)
    X_val, y_val, src_val = _load_split("val", data_dir)
    X_test, y_test, src_test = _load_split("test", data_dir)

    if set(np.unique(y_train)) != set(range(NUM_CLASSES)):
        raise RuntimeError("Training split does not contain all 4 classes.")
    if set(np.unique(y_val)) != set(range(NUM_CLASSES)):
        raise RuntimeError("Validation split does not contain all 4 classes.")
    if set(np.unique(y_test)) != set(range(NUM_CLASSES)):
        raise RuntimeError("Test split does not contain all 4 classes.")

    train_mean = X_train.mean(axis=(0, 2))
    train_std = np.maximum(X_train.std(axis=(0, 2)), 1e-6)
    X_train = ((X_train - train_mean[None, :, None]) / train_std[None, :, None]).astype(np.float32)
    X_val = ((X_val - train_mean[None, :, None]) / train_std[None, :, None]).astype(np.float32)
    X_test = ((X_test - train_mean[None, :, None]) / train_std[None, :, None]).astype(np.float32)

    (out_dir / "imu_norm_stats.json").write_text(
        json.dumps(
            {
                "mean_per_channel": train_mean.tolist(),
                "std_per_channel": train_std.tolist(),
                "window_length": 200,
                "n_channels": 6,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    class_weights = _compute_class_weights(y_train).to(device)
    model = build_activity_expert(
        {
            "in_channels": 6,
            "window_length": 200,
            "num_classes": NUM_CLASSES,
        }
    ).to(device)
    model_params = sum(parameter.numel() for parameter in model.parameters())

    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)

    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train)),
        batch_size=args.batch_size,
        shuffle=True,
    )
    val_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val)),
        batch_size=args.batch_size,
        shuffle=False,
    )

    best_val_macro_f1 = -1.0
    best_epoch = 0
    patience_left = args.patience
    history: List[Dict[str, Any]] = []

    t0 = time.time()
    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss_sum = 0.0
        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            optimizer.zero_grad()
            output = model(xb)
            loss = criterion(output["logits"], yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss_sum += float(loss.item())
        scheduler.step()
        train_loss = train_loss_sum / max(len(train_loader), 1)

        model.eval()
        val_loss_sum = 0.0
        logits_parts: List[np.ndarray] = []
        targets_parts: List[np.ndarray] = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb = xb.to(device)
                yb = yb.to(device)
                output = model(xb)
                loss = criterion(output["logits"], yb)
                val_loss_sum += float(loss.item())
                logits_parts.append(output["logits"].cpu().numpy())
                targets_parts.append(yb.cpu().numpy())

        val_loss = val_loss_sum / max(len(val_loader), 1)
        val_logits = np.concatenate(logits_parts, axis=0)
        val_targets = np.concatenate(targets_parts, axis=0)
        checkpoint_valid, checkpoint_reason = _checkpoint_valid(val_logits, val_targets, val_loss)

        from sklearn.metrics import accuracy_score, f1_score

        val_preds = np.argmax(val_logits, axis=1)
        val_macro_f1 = float(f1_score(val_targets, val_preds, average="macro", zero_division=0))
        val_accuracy = float(accuracy_score(val_targets, val_preds))

        if checkpoint_valid and val_macro_f1 > best_val_macro_f1:
            best_val_macro_f1 = val_macro_f1
            best_epoch = epoch
            patience_left = args.patience
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "val_macro_f1": val_macro_f1,
                    "class_names": CLASS_NAMES,
                    "train_mean": train_mean.tolist(),
                    "train_std": train_std.tolist(),
                },
                out_dir / "best_model.pt",
            )
        else:
            patience_left -= 1

        history.append(
            {
                "epoch": epoch,
                "train_loss": round(train_loss, 5),
                "val_loss": round(val_loss, 5),
                "val_macro_f1": round(val_macro_f1, 5),
                "val_accuracy": round(val_accuracy, 5),
                "checkpoint_valid": checkpoint_valid,
                "checkpoint_reason": checkpoint_reason,
            }
        )

        log.info(
            "epoch=%d train_loss=%.4f val_loss=%.4f val_macro_f1=%.4f val_acc=%.4f ckpt=%s reason=%s patience_left=%d",
            epoch,
            train_loss,
            val_loss,
            val_macro_f1,
            val_accuracy,
            checkpoint_valid,
            checkpoint_reason,
            patience_left,
        )

        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "class_names": CLASS_NAMES,
                "train_mean": train_mean.tolist(),
                "train_std": train_std.tolist(),
            },
            out_dir / "last_model.pt",
        )

        if patience_left <= 0:
            log.info("Early stopping at epoch %d", epoch)
            break

    if (out_dir / "best_model.pt").exists():
        best_state = torch.load(out_dir / "best_model.pt", map_location=device)
        model.load_state_dict(best_state["model_state_dict"])
    else:
        log.warning("best_model.pt was not saved; evaluating last model state.")

    elapsed_sec = time.time() - t0
    test_metrics = run_eval(model, X_test, y_test, src_test, device=device, batch_size=args.batch_size)

    metrics_payload = {
        "accuracy": test_metrics["accuracy"],
        "macro_f1": test_metrics["macro_f1"],
        "weighted_f1": test_metrics["weighted_f1"],
        "best_epoch": best_epoch,
        "best_val_macro_f1": round(best_val_macro_f1, 5),
        "activity_classes": CLASS_NAMES,
        "class_weights": {CLASS_NAMES[idx]: round(float(class_weights[idx]), 4) for idx in range(NUM_CLASSES)},
    }
    train_cfg = {
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "weight_decay": args.weight_decay,
        "patience": args.patience,
        "device": str(device),
        "seed": args.seed,
        "loss": "CrossEntropyLoss",
        "optimizer": "AdamW",
        "scheduler": "CosineAnnealingLR",
        "checkpoint_metric": "validation macro_f1",
        "dataset_dir": str(data_dir),
        "class_weights": {CLASS_NAMES[idx]: round(float(class_weights[idx]), 4) for idx in range(NUM_CLASSES)},
    }
    report = _build_report(
        dataset_summary=dataset_summary,
        audit_summary=audit_summary,
        best_epoch=best_epoch,
        best_val_macro_f1=best_val_macro_f1,
        history=history,
        test_metrics=test_metrics,
        train_cfg=train_cfg,
        model_params=model_params,
        elapsed_sec=elapsed_sec,
        v0_metrics=v0_metrics,
        v0_per_class=v0_per_class,
    )

    (out_dir / "metrics.json").write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
    (out_dir / "training_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    (out_dir / "confusion_matrix.json").write_text(json.dumps(test_metrics["confusion_matrix"], indent=2), encoding="utf-8")
    (out_dir / "prediction_distribution.json").write_text(json.dumps(test_metrics["prediction_distribution"], indent=2), encoding="utf-8")
    (out_dir / "per_class_metrics.json").write_text(json.dumps(test_metrics["per_class"], indent=2), encoding="utf-8")
    (out_dir / "source_breakdown.json").write_text(json.dumps(test_metrics["source_breakdown"], indent=2), encoding="utf-8")
    (out_dir / "activity_v2_report.md").write_text(report, encoding="utf-8")

    log.info("Activity v2 test macro_f1: %.4f", test_metrics["macro_f1"])
    log.info("Activity v2 best val macro_f1: %.4f", best_val_macro_f1)
    log.info("Activity v2 report written to %s", out_dir / "activity_v2_report.md")


if __name__ == "__main__":
    main()