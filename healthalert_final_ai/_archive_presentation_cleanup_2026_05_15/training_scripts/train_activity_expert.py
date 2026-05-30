"""
train_activity_expert.py
─────────────────────────────────────────────────────────────────────────────
Phase 4 — Train Activity Context Expert

Classifies movement context (not health risk directly).
Output feeds RiskFusionEngine for contextual risk interpretation.

Data source: outputs/windowed_dataset/activity_context/{train,val,test}.npz
  - Only datasets allowed per hybrid_task_routing.yaml activity_context section
  - Fall (label=1) and near_fall (label=2) are EXCLUDED — not activity classes
  - Forbidden datasets (PPG-DaLiA, WildPPG, etc.) are filtered out
  - UMAFall allowed for activity_context (ADL/normal windows only — fall labels excluded)

Label remap (raw NPZ → contiguous activity class index):
  0 (normal)       → 0  normal
  3 (instability)  → 1  instability
  10 (walking)     → 2  walking
  11 (sitting)     → 3  sitting
  12 (standing)    → 4  standing
  13 (lying)       → 5  lying

Output: outputs/hybrid_redesign/activity_expert/
  best_model.pt, last_model.pt, metrics.json, training_history.json,
  confusion_matrix.json, prediction_distribution.json,
  per_class_metrics.json, source_breakdown.json, activity_expert_report.md

Usage:
  cd healthalert_final_ai/
  python scripts/train_activity_expert.py --device cpu
  python scripts/train_activity_expert.py --smoke   # fast test with synthetic
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import yaml
from torch.utils.data import DataLoader, TensorDataset

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.healthalert.models.activity_expert import build_activity_expert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("healthalert.train_activity_expert")

ROUTING_CFG = PROJECT_ROOT / "config" / "hybrid_task_routing.yaml"
OUT_DIR = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "activity_expert"
WINDOWED_NPZ_DIR = PROJECT_ROOT / "outputs" / "windowed_dataset" / "activity_context"

# ── Label policy ─────────────────────────────────────────────────────────────
# Raw NPZ label → contiguous class index.  Labels not in this map are dropped.
LABEL_REMAP: Dict[int, int] = {
    0:  0,   # normal
    3:  1,   # instability (SisFall near-fall risk context)
    10: 2,   # walking
    11: 3,   # sitting
    12: 4,   # standing
    13: 5,   # lying
}
# These labels must NEVER enter activity training
LABEL_HARD_EXCLUDE: set = {1, 2}  # fall, near_fall

ACTIVITY_CLASS_NAMES: List[str] = [
    "normal", "instability", "walking", "sitting", "standing", "lying"
]
NUM_CLASSES = len(ACTIVITY_CLASS_NAMES)  # 6


# ─── CLI ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train Activity Context Expert")
    p.add_argument("--epochs",      type=int,   default=30)
    p.add_argument("--batch_size",  type=int,   default=256)
    p.add_argument("--device",      type=str,   default="auto")
    p.add_argument("--lr",          type=float, default=3e-4)
    p.add_argument("--seed",        type=int,   default=42)
    p.add_argument("--smoke",       action="store_true",
                   help="Fast smoke-test with synthetic data (no real NPZ required)")
    p.add_argument("--out_dir",     type=str,   default=None,
                   help="Override default output directory")
    return p.parse_args()


# ─── Routing ─────────────────────────────────────────────────────────────────

def _norm_src(name: str) -> str:
    """Normalise source name for case-insensitive routing lookup."""
    return name.lower().replace("-", "_").replace(" ", "_").strip()


def load_routing() -> Tuple[set, set]:
    """Return (allowed_norm, forbidden_norm) source name sets for activity_context."""
    with open(ROUTING_CFG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ac = cfg.get("activity_context", {})
    allowed   = {_norm_src(s) for s in ac.get("allowed_datasets",  [])}
    forbidden = {_norm_src(s) for s in ac.get("forbidden_datasets", [])}
    return allowed, forbidden


# ─── Data loading ─────────────────────────────────────────────────────────────

def _make_synthetic(n: int, seed: int = 42) -> Tuple[np.ndarray, np.ndarray]:
    rng = np.random.RandomState(seed)
    X = rng.randn(n, 6, 200).astype(np.float32)
    y = rng.randint(0, NUM_CLASSES, size=n).astype(np.int64)
    return X, y


def load_activity_npz(
    split: str,
    allowed: set,
    forbidden: set,
    smoke: bool = False,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict]:
    """
    Load and filter one split from the activity_context consolidated NPZ.

    Returns:
        X:       (N, 6, 200) float32  — IMU windows, channels-first
        y:       (N,)        int64    — remapped activity class indices
        sources: (N,)        object   — source dataset name per window
        info:    dict        — audit counts
    """
    npz_path = WINDOWED_NPZ_DIR / f"{split}.npz"
    if not npz_path.exists():
        log.error(f"[{split}] NPZ not found: {npz_path}")
        sys.exit(1)

    raw = np.load(str(npz_path), allow_pickle=True)

    # ── IMU windows (N, 200, 6) → transpose to (N, 6, 200) ──────────────────
    imu_raw = raw["imu"].astype(np.float32)                 # (N, 200, 6)
    X_raw   = imu_raw.transpose(0, 2, 1)                    # (N, 6, 200)
    y_raw   = raw["labels"].flatten().astype(np.int64)
    meta    = raw["metadata"]

    n_total = len(y_raw)

    # ── Parse metadata → source names ───────────────────────────────────────
    src_names = np.empty(n_total, dtype=object)
    for i, m in enumerate(meta):
        try:
            d = json.loads(str(m)) if not isinstance(m, dict) else m
            src_names[i] = d.get("dataset_name", "unknown")
        except Exception:
            src_names[i] = "unknown"

    # ── Source filter ────────────────────────────────────────────────────────
    # Keep only if: source in allowed AND source not in forbidden
    src_norm = np.array([_norm_src(str(s)) for s in src_names])
    src_keep = np.array([
        (s in allowed) and (s not in forbidden)
        for s in src_norm
    ], dtype=bool)
    n_src_removed = int((~src_keep).sum())

    X_raw    = X_raw[src_keep]
    y_raw    = y_raw[src_keep]
    src_names = src_names[src_keep]

    # ── Label filter ─────────────────────────────────────────────────────────
    # Hard-exclude fall/near_fall, then keep only labels with a valid remap
    valid_labels = set(LABEL_REMAP.keys())
    lbl_keep = np.array([
        (int(lbl) not in LABEL_HARD_EXCLUDE) and (int(lbl) in valid_labels)
        for lbl in y_raw
    ], dtype=bool)
    n_lbl_removed = int((~lbl_keep).sum())

    X_raw    = X_raw[lbl_keep]
    y_raw    = y_raw[lbl_keep]
    src_names = src_names[lbl_keep]

    # ── Remap to contiguous class indices ────────────────────────────────────
    y_mapped = np.array([LABEL_REMAP[int(lbl)] for lbl in y_raw], dtype=np.int64)

    # ── Smoke subset ─────────────────────────────────────────────────────────
    if smoke:
        rng = np.random.RandomState(42)
        idx = rng.permutation(len(y_mapped))[:min(2000, len(y_mapped))]
        X_raw, y_mapped, src_names = X_raw[idx], y_mapped[idx], src_names[idx]

    # ── Build audit info ─────────────────────────────────────────────────────
    unique, counts = np.unique(y_mapped, return_counts=True)
    class_dist = {ACTIVITY_CLASS_NAMES[int(u)]: int(c)
                  for u, c in zip(unique, counts)}

    src_dist: Dict[str, int] = {}
    for s in src_names:
        src_dist[str(s)] = src_dist.get(str(s), 0) + 1

    info = {
        "n_total_in_npz": n_total,
        "n_removed_bad_source": n_src_removed,
        "n_removed_bad_label": n_lbl_removed,
        "n_final": len(y_mapped),
        "class_distribution": class_dist,
        "source_distribution": src_dist,
    }

    return X_raw, y_mapped, src_names, info


# ─── Class weights ────────────────────────────────────────────────────────────

def compute_class_weights(y: np.ndarray, n_classes: int) -> torch.Tensor:
    """Inverse-frequency class weights, clamped to [0.1, 10× median]."""
    counts = np.bincount(y, minlength=n_classes).astype(np.float64)
    counts = np.maximum(counts, 1)               # avoid zero-div
    inv_freq = 1.0 / counts
    inv_freq = inv_freq / inv_freq.sum() * n_classes  # normalise so mean ≈ 1
    median_w = float(np.median(inv_freq))
    inv_freq = np.clip(inv_freq, 0.1, max(median_w * 10.0, 1.0))
    return torch.tensor(inv_freq, dtype=torch.float32)


# ─── Checkpoint validity ──────────────────────────────────────────────────────

def _checkpoint_valid(
    logits: np.ndarray,
    targets: np.ndarray,
    val_loss: float,
    n_classes: int,
) -> Tuple[bool, str]:
    """Return (is_valid, reason_if_invalid)."""
    if not np.isfinite(val_loss):
        return False, f"val_loss is not finite: {val_loss}"
    preds = np.argmax(logits, axis=1)
    n_predicted = len(np.unique(preds))
    if n_predicted < 2:
        return False, f"collapse: only {n_predicted} class(es) predicted"
    # macro_f1 sanity — must be above random-chance floor (1/n_classes * 0.5)
    from sklearn.metrics import f1_score as _f1
    mf1 = float(_f1(targets, preds, average="macro", zero_division=0))
    if mf1 < (0.5 / n_classes):
        return False, f"macro_f1={mf1:.4f} below random-chance floor"
    return True, "ok"


# ─── Evaluation ───────────────────────────────────────────────────────────────

def run_eval(
    model: nn.Module,
    X: np.ndarray,
    y: np.ndarray,
    src_names: np.ndarray,
    device: torch.device,
    batch_size: int = 512,
    threshold_name: str = "test",
) -> Dict:
    """Full evaluation. Returns metrics dict."""
    from sklearn.metrics import (
        accuracy_score, f1_score,
        precision_recall_fscore_support, confusion_matrix as _cm,
    )

    model.eval()
    all_logits: List[np.ndarray] = []
    ds = TensorDataset(torch.from_numpy(X))
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False)
    with torch.no_grad():
        for (xb,) in loader:
            out = model(xb.to(device))
            all_logits.append(out["logits"].cpu().numpy())

    logits = np.concatenate(all_logits, axis=0)
    preds  = np.argmax(logits, axis=1)
    probs  = torch.softmax(torch.from_numpy(logits), dim=-1).numpy()

    accuracy    = float(accuracy_score(y, preds))
    macro_f1    = float(f1_score(y, preds, average="macro",    zero_division=0))
    weighted_f1 = float(f1_score(y, preds, average="weighted", zero_division=0))

    cm = _cm(y, preds, labels=list(range(NUM_CLASSES))).tolist()

    prec, rec, f1, sup = precision_recall_fscore_support(
        y, preds, labels=list(range(NUM_CLASSES)), zero_division=0
    )
    per_class = {
        ACTIVITY_CLASS_NAMES[i]: {
            "precision": float(prec[i]),
            "recall":    float(rec[i]),
            "f1":        float(f1[i]),
            "support":   int(sup[i]),
        }
        for i in range(NUM_CLASSES)
    }

    # Prediction distribution
    pred_dist = {
        ACTIVITY_CLASS_NAMES[i]: int((preds == i).sum())
        for i in range(NUM_CLASSES)
    }

    # Source breakdown
    src_breakdown: Dict[str, Dict] = {}
    for src in np.unique(src_names):
        mask = src_names == src
        ys, ps = y[mask], preds[mask]
        mf1_src = float(f1_score(ys, ps, average="macro", zero_division=0))
        src_breakdown[str(src)] = {
            "n": int(mask.sum()),
            "macro_f1": round(mf1_src, 4),
            "class_dist": {
                ACTIVITY_CLASS_NAMES[i]: int((ys == i).sum())
                for i in range(NUM_CLASSES) if (ys == i).sum() > 0
            },
        }

    return {
        "accuracy":     round(accuracy,    4),
        "macro_f1":     round(macro_f1,    4),
        "weighted_f1":  round(weighted_f1, 4),
        "per_class":    per_class,
        "confusion_matrix": cm,
        "prediction_distribution": pred_dist,
        "source_breakdown": src_breakdown,
        "logits":       logits,
        "preds":        preds,
    }


# ─── Report builder ───────────────────────────────────────────────────────────

def build_report(
    audit_tr: Dict,
    audit_val: Dict,
    audit_te: Dict,
    best_epoch: int,
    best_val_macro_f1: float,
    history: List[Dict],
    test_metrics: Dict,
    model_params: int,
    train_cfg: Dict,
    out_dir: Path,
    smoke: bool = False,
) -> str:
    cm = test_metrics["confusion_matrix"]
    pc = test_metrics["per_class"]
    pd_ = test_metrics["prediction_distribution"]
    sb = test_metrics["source_breakdown"]

    # acceptance criteria
    accepted = (
        test_metrics["macro_f1"] >= 0.55
        and test_metrics["accuracy"] >= 0.60
        and sum(1 for v in pc.values() if v["recall"] > 0.30) >= 3
    )
    proceed_ppg = accepted

    lines = [
        "# Activity Context Expert — Training Report",
        "",
        f"**Generated:** {__import__('datetime').date.today()}  ",
        f"**Output dir:** `{out_dir}`  ",
        "",
        "---",
        "",
        "## 1. Dataset Source Summary",
        "",
        "| Split | Total in NPZ | Removed (source) | Removed (label) | Used |",
        "|-------|-------------|-----------------|----------------|------|",
        f"| train | {audit_tr['n_total_in_npz']:,} | {audit_tr['n_removed_bad_source']:,} | {audit_tr['n_removed_bad_label']:,} | {audit_tr['n_final']:,} |",
        f"| val   | {audit_val['n_total_in_npz']:,} | {audit_val['n_removed_bad_source']:,} | {audit_val['n_removed_bad_label']:,} | {audit_val['n_final']:,} |",
        f"| test  | {audit_te['n_total_in_npz']:,} | {audit_te['n_removed_bad_source']:,} | {audit_te['n_removed_bad_label']:,} | {audit_te['n_final']:,} |",
        "",
        "**Allowed sources (per routing):** uci_har, unimib_shar, umafall, mobiact, sisfall  ",
        "**Forbidden sources removed:** ppg_dalia, wildppg, and any not in allowed list  ",
        "**Labels excluded:** fall (1), near_fall (2) — must not enter activity training  ",
        "",
        "## 2. Label Mapping",
        "",
        "| Raw label | Name | Activity class | Index |",
        "|-----------|------|----------------|-------|",
        "| 0 | normal | normal | 0 |",
        "| 3 | instability | instability | 1 |",
        "| 10 | walking | walking | 2 |",
        "| 11 | sitting | sitting | 3 |",
        "| 12 | standing | standing | 4 |",
        "| 13 | lying | lying | 5 |",
        "| 1 | fall | **EXCLUDED** | — |",
        "| 2 | near_fall | **EXCLUDED** | — |",
        "| 99 | unknown (WildPPG) | **EXCLUDED** (forbidden source) | — |",
        "",
        "## 3. Train / Val / Test Counts",
        "",
        f"- **Train:** {audit_tr['n_final']:,} windows",
        f"- **Val:**   {audit_val['n_final']:,} windows",
        f"- **Test:**  {audit_te['n_final']:,} windows",
        "",
        "## 4. Class Distribution",
        "",
        "### Train",
        "",
        "| Class | Count | % |",
        "|-------|-------|---|",
    ]
    tr_n = audit_tr["n_final"] or 1
    for cls, cnt in sorted(audit_tr["class_distribution"].items(), key=lambda x: -x[1]):
        lines.append(f"| {cls} | {cnt:,} | {100*cnt/tr_n:.1f}% |")

    lines += [
        "",
        "### Val",
        "",
        "| Class | Count | % |",
        "|-------|-------|---|",
    ]
    val_n = audit_val["n_final"] or 1
    for cls, cnt in sorted(audit_val["class_distribution"].items(), key=lambda x: -x[1]):
        lines.append(f"| {cls} | {cnt:,} | {100*cnt/val_n:.1f}% |")

    lines += [
        "",
        "## 5. Model Architecture",
        "",
        "**ActivityExpertCNN** (CNN1D + GRU + FC)  ",
        f"- Input: (batch, 6, 200) — 6-channel IMU, 4s windows @ 50Hz  ",
        f"- CNN: Conv1D × 3 (32→64→128 channels, k=5, MaxPool×3)  ",
        f"- GRU: hidden=64, 1 layer  ",
        f"- FC: 64 → {NUM_CLASSES} classes  ",
        f"- Output: softmax probabilities over {NUM_CLASSES} activity classes  ",
        f"- Parameters: {model_params:,}  ",
        "",
        "## 6. Training Config",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
    ]
    for k, v in train_cfg.items():
        lines.append(f"| {k} | {v} |")

    best_row = next((h for h in history if h["epoch"] == best_epoch), {})
    lines += [
        "",
        "## 7. Best Epoch",
        "",
        f"- **Best epoch:** {best_epoch}  ",
        f"- **Best val macro_f1:** {best_val_macro_f1:.4f}  ",
        f"- **Val loss at best:** {best_row.get('val_loss', '—')}  ",
        "",
        "## 8. Best macro_f1 (val)",
        "",
        f"**{best_val_macro_f1:.4f}**",
        "",
        "## 9. Test Accuracy",
        "",
        f"**{test_metrics['accuracy']:.4f}** ({test_metrics['accuracy']*100:.2f}%)",
        "",
        "## 10. Test macro_f1",
        "",
        f"**{test_metrics['macro_f1']:.4f}**",
        "",
        "## 11. Test weighted_f1",
        "",
        f"**{test_metrics['weighted_f1']:.4f}**",
        "",
        "## 12. Per-Class Precision / Recall / F1",
        "",
        "| Class | Precision | Recall | F1 | Support |",
        "|-------|-----------|--------|----|---------|",
    ]
    for cls, vals in pc.items():
        lines.append(
            f"| {cls} | {vals['precision']:.3f} | {vals['recall']:.3f} | {vals['f1']:.3f} | {vals['support']:,} |"
        )

    lines += [
        "",
        "## 13. Confusion Matrix",
        "",
        "Rows = actual, Columns = predicted  ",
        "",
        "| | " + " | ".join(ACTIVITY_CLASS_NAMES) + " |",
        "|---|" + "---|" * NUM_CLASSES,
    ]
    for i, row in enumerate(cm):
        lines.append("| " + ACTIVITY_CLASS_NAMES[i] + " | " + " | ".join(str(v) for v in row) + " |")

    lines += [
        "",
        "## 14. Prediction Distribution",
        "",
        "| Class | Predicted count |",
        "|-------|----------------|",
    ]
    for cls, cnt in pd_.items():
        lines.append(f"| {cls} | {cnt:,} |")

    lines += [
        "",
        "## 15. Dataset-Source Breakdown",
        "",
        "| Source | n | macro_f1 |",
        "|--------|---|----------|",
    ]
    for src, info in sorted(sb.items(), key=lambda x: -x[1]["n"]):
        lines.append(f"| {src} | {info['n']:,} | {info['macro_f1']:.3f} |")

    # identify weak classes
    weak = [cls for cls, v in pc.items() if v["recall"] < 0.40 and v["support"] > 0]
    lines += [
        "",
        "## 16. Failure Cases / Weak Classes",
        "",
    ]
    if weak:
        lines.append("Classes with recall < 0.40:")
        lines.append("")
        for cls in weak:
            v = pc[cls]
            lines.append(f"- **{cls}**: recall={v['recall']:.3f}, F1={v['f1']:.3f}, support={v['support']:,}")
    else:
        lines.append("No classes with recall < 0.40. All classes are reasonably well-covered.")

    lines += [
        "",
        "## 17. Activity Expert Acceptance",
        "",
        f"**Accepted: {'YES' if accepted else 'NO'}**",
        "",
        "Acceptance criteria:",
        f"- Test macro_f1 ≥ 0.55: {'✓' if test_metrics['macro_f1'] >= 0.55 else '✗'} ({test_metrics['macro_f1']:.4f})",
        f"- Test accuracy ≥ 0.60: {'✓' if test_metrics['accuracy'] >= 0.60 else '✗'} ({test_metrics['accuracy']:.4f})",
        f"- ≥ 3 classes with recall > 0.30: {'✓' if sum(1 for v in pc.values() if v['recall'] > 0.30) >= 3 else '✗'} ({sum(1 for v in pc.values() if v['recall'] > 0.30)} classes)",
        "",
        "## 18. Proceed to PPG Quality Expert",
        "",
        f"**{'YES — Activity Expert accepted, PPG Quality Expert training can proceed.' if proceed_ppg else 'NO — Activity Expert not yet accepted. Review results before proceeding.'}**",
        "",
        "---",
        "",
        "*Note: Activity Expert does NOT generate health alarms. It provides movement*",
        "*context to RiskFusionEngine (e.g., high fall_prob + lying → stronger risk signal).*",
        "",
        "---",
        "",
        "## 19. Normal/Instability Dominance Analysis",
        "",
    ]

    tr_normal = audit_tr["class_distribution"].get("normal", 0)
    tr_instability = audit_tr["class_distribution"].get("instability", 0)
    tr_dominant = tr_normal + tr_instability
    tr_adl = sum(
        audit_tr["class_distribution"].get(c, 0)
        for c in ["walking", "sitting", "standing", "lying"]
    )
    dom_pct = 100 * tr_dominant / max(audit_tr["n_final"], 1)
    adl_pct = 100 * tr_adl      / max(audit_tr["n_final"], 1)
    lines += [
        f"- **normal + instability**: {tr_dominant:,} windows ({dom_pct:.1f}% of train)",
        f"- **walking + sitting + standing + lying**: {tr_adl:,} windows ({adl_pct:.1f}% of train)",
        "",
    ]
    if dom_pct > 90:
        lines.append(
            f"⚠ **SEVERE IMBALANCE**: dominant classes are {dom_pct:.1f}% of train. "
            "ADL minority classes at high risk of being crushed. "
            "Class weights applied to compensate (see training config)."
        )
    else:
        lines.append(f"Imbalance within manageable range ({dom_pct:.1f}% dominant).")

    # Prediction distribution — how many predictions went to each class
    pred_normal = test_metrics["prediction_distribution"].get("normal", 0)
    pred_instability = test_metrics["prediction_distribution"].get("instability", 0)
    pred_dominant_total = pred_normal + pred_instability
    total_preds = sum(test_metrics["prediction_distribution"].values()) or 1
    pred_dom_pct = 100 * pred_dominant_total / total_preds
    lines += [
        "",
        "**Test prediction distribution (dominant classes):**",
        f"- normal predicted: {pred_normal:,} ({100*pred_normal/total_preds:.1f}% of all predictions)",
        f"- instability predicted: {pred_instability:,} ({100*pred_instability/total_preds:.1f}%)",
        f"- normal+instability total: {pred_dominant_total:,} ({pred_dom_pct:.1f}%)",
        "",
    ]
    if pred_dom_pct > 95:
        lines.append("🔴 **DOMINANT CLASS CRUSH CONFIRMED**: Model predicted normal/instability "
                     f"{pred_dom_pct:.1f}% of the time — rare ADL classes were NOT learned.")
    elif pred_dom_pct > 80:
        lines.append("🟡 **PARTIAL CRUSH**: Model heavily favours normal/instability. "
                     "ADL classes learned to some extent but under-predicted.")
    else:
        lines.append("🟢 **Prediction distribution healthy**: Model predicts across all classes.")

    # --- Section 20: Collapse Detection ---
    collapse_epochs = [h for h in history if h.get("n_pred_classes", 2) < 2]
    first_multi = next((h["epoch"] for h in history if h.get("n_pred_classes", 1) >= 2), None)
    lines += [
        "",
        "## 20. Model Collapse Detection",
        "",
        f"- Epochs with n_pred_cls=1 (single-class collapse): **{len(collapse_epochs)} / {len(history)}**",
        f"- First epoch predicting ≥ 2 classes: **{first_multi if first_multi else 'NEVER'}**",
        "",
    ]
    if len(collapse_epochs) == len(history):
        lines.append("🔴 **COMPLETE COLLAPSE**: The model never broke out of single-class prediction. "
                     "All epochs flagged as invalid. No best_model.pt was saved.")
    elif len(collapse_epochs) > len(history) // 2:
        lines.append(f"🟡 **PARTIAL COLLAPSE**: {len(collapse_epochs)}/{len(history)} epochs in collapse. "
                     "Model struggled to learn multi-class boundaries.")
    else:
        lines.append("🟢 **No collapse**: Model maintained multi-class predictions throughout training.")

    # Collapse epoch table (first 15 only)
    if history:
        lines += [
            "",
            "| Epoch | n_pred_cls | checkpoint_valid | val_macro_f1 |",
            "|-------|-----------|-----------------|--------------|"]
        for h in history[:15]:
            ckpt_str = "✓" if h.get("checkpoint_valid", False) else "✗"
            lines.append(
                f"| {h['epoch']:3d} | {h.get('n_pred_classes', '?'):10} | "
                f"{ckpt_str:16} | {h['val_macro_f1']:.4f} |"
            )
        if len(history) > 15:
            lines.append(f"| ... ({len(history)-15} more epochs) | | | |")

    # --- Section 21: ADL Class Learning Assessment ---
    adl_classes = ["walking", "sitting", "standing", "lying"]
    adl_learned   = [c for c in adl_classes if pc.get(c, {}).get("recall", 0) >= 0.30]
    adl_partial   = [c for c in adl_classes if 0.10 <= pc.get(c, {}).get("recall", 0) < 0.30]
    adl_not_learned = [c for c in adl_classes if pc.get(c, {}).get("recall", 0) < 0.10]

    lines += [
        "",
        "## 21. ADL Class Learning Assessment",
        "",
        "*(walking / sitting / standing / lying — source: UCI-HAR only)*",
        "",
        "| Class | Precision | Recall | F1 | Support | Status |",
        "|-------|-----------|--------|----|---------|--------|"]
    for c in adl_classes:
        v = pc.get(c, {})
        rec = v.get("recall", 0)
        status = ("🟢 LEARNED" if rec >= 0.30
                  else "🟡 PARTIAL" if rec >= 0.10
                  else "🔴 NOT LEARNED")
        lines.append(
            f"| {c} | {v.get('precision',0):.3f} | {v.get('recall',0):.3f} | "
            f"{v.get('f1',0):.3f} | {v.get('support',0):,} | {status} |"
        )

    lines.append("")
    if len(adl_learned) == 4:
        lines.append("🟢 **All 4 ADL classes LEARNED** (recall ≥ 0.30). Single-model approach viable.")
    elif len(adl_learned) >= 2:
        lines.append(f"🟡 **Partially learned**: {len(adl_learned)}/4 ADL classes have recall ≥ 0.30. "
                     f"Not learned: {', '.join(adl_not_learned)}.")
    else:
        lines.append(
            f"🔴 **ADL classes NOT LEARNED**: only {len(adl_learned)}/4 ADL classes have recall ≥ 0.30. "
            "Recommendation: split into Pure Activity Expert + Motion Instability Expert (see Section 24)."
        )

    # --- Section 22: Checkpoint Validity History ---
    valid_epochs = [h for h in history if h.get("checkpoint_valid", False)]
    lines += [
        "",
        "## 22. Checkpoint Validity",
        "",
        f"- Valid checkpoints (checkpoint_valid=True): **{len(valid_epochs)} / {len(history)}**",
        f"- best_model.pt saved: **{'YES — epoch ' + str(best_epoch) if best_epoch > 0 else 'NO (all epochs invalid)'}**",
        f"- best_val_macro_f1: **{f'{best_val_macro_f1:.4f}' if best_val_macro_f1 > 0 else 'N/A (never saved)'}**",
        "",
    ]
    if best_epoch == 0:
        lines.append(
            "⚠ **best_model.pt was NOT saved**. No epoch passed checkpoint validity checks "
            "(macro_f1 above floor AND ≥2 classes predicted AND finite val_loss). "
            "Evaluation used the last model state (which may be in collapse)."
        )
    else:
        lines.append(
            f"✓ best_model.pt saved at epoch {best_epoch} with val_macro_f1={best_val_macro_f1:.4f}."
        )

    # --- Section 23: Data Source Confirmation ---
    lines += [
        "",
        "## 23. Data Source Confirmation",
        "",
        f"- **Trained on real prepared public dataset NPZ: {'NO — SMOKE/SYNTHETIC MODE' if smoke else 'YES'}**",
        f"- NPZ directory: `outputs/windowed_dataset/activity_context/`",
        f"- Keys used: `imu` (N, 200, 6) — 4s windows, 6-channel IMU, 50Hz",
        f"- `features` key (flattened N×1400): NOT used",
        f"- `ppg` key: NOT used",
        f"- Fall (label=1) and near_fall (label=2): EXCLUDED before training",
        f"- Forbidden sources (PPG-DaLiA, WildPPG): EXCLUDED via routing",
        "",
    ]
    if smoke:
        lines.append("⚠ **THIS WAS A SMOKE TEST WITH SYNTHETIC DATA. Results are NOT valid for deployment.**")
    else:
        lines.append("✓ Real public dataset NPZ files were used. No synthetic data. "
                     "No live ESP32 sensor data used (inference only, per project rules).")

    # --- Section 24: Split Architecture Recommendation ---
    lines += [
        "",
        "## 24. Split Architecture Recommendation",
        "",
    ]
    if len(adl_learned) < 2 or len(collapse_epochs) == len(history):
        lines += [
            "**Recommendation: SPLIT the model into two separate experts.**",
            "",
            "Evidence:",
            f"- ADL classes learned: {len(adl_learned)}/4 (threshold: recall ≥ 0.30)",
            f"- Collapse epochs: {len(collapse_epochs)}/{len(history)}",
            f"- normal+instability dominate {dom_pct:.1f}% of training data",
            f"- ADL classes come exclusively from UCI-HAR (different sensor/protocol than UMAFall/SisFall)",
            "",
            "### Proposed Split",
            "",
            "**Option A — Pure Activity Expert** (walking / sitting / standing / lying / normal)",
            "- Dataset: UCI-HAR only (all 4 ADL classes + normal from UCI-HAR)",
            "- Remove instability (SisFall-specific, completely different domain)",
            "- Balanced 5-class problem with UCI-HAR data only",
            "",
            "**Option B — Motion Instability Expert** (normal vs instability)",
            "- Dataset: UMAFall + SisFall + UniMiB-SHAR (same sources as instability class)",
            "- Binary or 2-class: instability (risk signal) vs normal (background)",
            "- Feeds RiskFusionEngine as a separate instability risk score",
            "",
            "*Await user review and explicit decision before proceeding.*",
        ]
    else:
        lines += [
            "**Recommendation: KEEP single Activity Expert model.**",
            "",
            f"- ADL classes learned: {len(adl_learned)}/4 (recall ≥ 0.30): {', '.join(adl_learned)}",
            "- Single-model approach is viable with current architecture.",
            "- Monitor ADL recall in production; consider split if recall degrades.",
        ]

    lines += [
        "",
        "---",
        "",
        "*This report was auto-generated by train_activity_expert.py*",
    ]

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    _out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR
    _out_dir.mkdir(parents=True, exist_ok=True)

    device = (
        torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if args.device == "auto"
        else torch.device(args.device)
    )

    # ── Load routing ────────────────────────────────────────────────────────
    allowed, forbidden = load_routing()
    log.info(f"Allowed datasets for activity_context: {sorted(allowed)}")
    log.info(f"Forbidden datasets: {sorted(forbidden)}")

    # ── Load data ────────────────────────────────────────────────────────────
    if args.smoke:
        log.warning("SMOKE MODE — using synthetic data (no real NPZ required)")
        X_tr, y_tr = _make_synthetic(1600, seed=args.seed)
        X_v,  y_v  = _make_synthetic(400,  seed=args.seed + 1)
        X_te, y_te = _make_synthetic(400,  seed=args.seed + 2)
        src_tr = np.array(["synthetic"] * len(y_tr))
        src_v  = np.array(["synthetic"] * len(y_v))
        src_te = np.array(["synthetic"] * len(y_te))
        _dummy_info = lambda n: {
            "n_total_in_npz": n, "n_removed_bad_source": 0,
            "n_removed_bad_label": 0, "n_final": n,
            "class_distribution": {c: n // NUM_CLASSES for c in ACTIVITY_CLASS_NAMES},
            "source_distribution": {"synthetic": n},
        }
        audit_tr, audit_val, audit_te = _dummy_info(len(y_tr)), _dummy_info(len(y_v)), _dummy_info(len(y_te))
    else:
        log.info("Loading activity_context NPZ files...")
        X_tr, y_tr, src_tr, audit_tr  = load_activity_npz("train", allowed, forbidden)
        X_v,  y_v,  src_v,  audit_val = load_activity_npz("val",   allowed, forbidden)
        X_te, y_te, src_te, audit_te  = load_activity_npz("test",  allowed, forbidden)

    # ── Print audit ──────────────────────────────────────────────────────────
    log.info("=== DATASET AUDIT ===")
    for split_name, info in [("train", audit_tr), ("val", audit_val), ("test", audit_te)]:
        log.info(f"  [{split_name}] {info['n_total_in_npz']:,} in NPZ → "
                 f"removed {info['n_removed_bad_source']:,} (source) + "
                 f"{info['n_removed_bad_label']:,} (label) → {info['n_final']:,} used")
        log.info(f"    class dist: { {k: v for k, v in info['class_distribution'].items()} }")
        log.info(f"    sources:    { {k: v for k, v in sorted(info['source_distribution'].items(), key=lambda x: -x[1])} }")

    log.info(f"Label mapping: {LABEL_REMAP}")
    log.info(f"Activity classes: {ACTIVITY_CLASS_NAMES}")

    if not args.smoke:
        # Check for excluded label contamination assertion
        for split_name, y in [("train", y_tr), ("val", y_v), ("test", y_te)]:
            assert y.max() < NUM_CLASSES, \
                f"[{split_name}] y contains index {y.max()} >= NUM_CLASSES={NUM_CLASSES}"
            assert y.min() >= 0, f"[{split_name}] y contains negative index {y.min()}"

    # ── Per-channel IMU normalization (z-score, stats from training split only) ──────
    # X shape: (N, 6, 200). Compute mean/std over samples AND time axis.
    # This is critical for cross-dataset training — UMAFall, SisFall, UCI-HAR
    # have different sensor units/placements; without normalization the CNN
    # cannot learn shared features and collapses to single-class prediction.
    if not args.smoke:
        imu_mean = X_tr.mean(axis=(0, 2))          # (6,)
        imu_std  = X_tr.std(axis=(0, 2))           # (6,)
        imu_std  = np.maximum(imu_std, 1e-6)       # avoid zero-div
        log.info(f"IMU norm mean (per channel): {np.round(imu_mean, 4).tolist()}")
        log.info(f"IMU norm std  (per channel): {np.round(imu_std,  4).tolist()}")
        def _norm(X: np.ndarray) -> np.ndarray:
            return ((X - imu_mean[None, :, None]) / imu_std[None, :, None]).astype(np.float32)
        X_tr = _norm(X_tr)
        X_v  = _norm(X_v)
        X_te = _norm(X_te)
        norm_stats_dict = {
            "mean_per_channel": imu_mean.tolist(),
            "std_per_channel":  imu_std.tolist(),
            "n_channels": 6,
            "window_length": 200,
            "note": "z-score per channel, computed from training split only. Apply before inference."
        }
        with open(_out_dir / "imu_norm_stats.json", "w") as f:
            json.dump(norm_stats_dict, f, indent=2)
        log.info("Saved imu_norm_stats.json")
    else:
        imu_mean = np.zeros(6, dtype=np.float32)
        imu_std  = np.ones(6,  dtype=np.float32)
        log.info("SMOKE MODE — skipping normalization (synthetic data)")

    # ── Class weights ────────────────────────────────────────────────────────
    class_weights = compute_class_weights(y_tr, NUM_CLASSES).to(device)
    log.info(f"Class weights: { {ACTIVITY_CLASS_NAMES[i]: round(float(class_weights[i]), 3) for i in range(NUM_CLASSES)} }")

    # ── Model ────────────────────────────────────────────────────────────────
    model = build_activity_expert({
        "in_channels": 6,
        "window_length": 200,
        "num_classes": NUM_CLASSES,
    }).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    log.info(f"Model: ActivityExpertCNN — {n_params:,} parameters")

    # ── Optimiser / scheduler / loss ─────────────────────────────────────────
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimiser = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimiser, T_max=args.epochs, eta_min=1e-5
    )

    # ── DataLoaders ──────────────────────────────────────────────────────────
    train_ds = TensorDataset(torch.from_numpy(X_tr), torch.from_numpy(y_tr))
    val_ds   = TensorDataset(torch.from_numpy(X_v),  torch.from_numpy(y_v))
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,  drop_last=False)
    val_loader   = DataLoader(val_ds,   batch_size=args.batch_size, shuffle=False, drop_last=False)

    # ── Training loop ────────────────────────────────────────────────────────
    log.info(f"ActivityTrainer — {args.epochs} epochs max, device={device}")

    best_val_macro_f1   = -1.0
    best_epoch          = 0
    patience_counter    = 0
    PATIENCE            = 10
    history: List[Dict] = []

    t0 = time.time()
    for epoch in range(1, args.epochs + 1):
        # ── Train ────────────────────────────────────────────────────────────
        model.train()
        train_loss = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimiser.zero_grad()
            out  = model(xb)
            loss = criterion(out["logits"], yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            train_loss += loss.item()
        scheduler.step()
        train_loss /= max(len(train_loader), 1)

        # ── Validate ─────────────────────────────────────────────────────────
        model.eval()
        val_loss   = 0.0
        all_logits: List[np.ndarray] = []
        all_targets: List[np.ndarray] = []
        with torch.no_grad():
            for xb, yb in val_loader:
                out = model(xb.to(device))
                val_loss += criterion(out["logits"], yb.to(device)).item()
                all_logits.append(out["logits"].cpu().numpy())
                all_targets.append(yb.numpy())
        val_loss /= max(len(val_loader), 1)

        logits_np = np.concatenate(all_logits)
        targets_np = np.concatenate(all_targets)
        preds_np   = np.argmax(logits_np, axis=1)

        from sklearn.metrics import f1_score as _f1, accuracy_score as _acc
        val_macro_f1  = float(_f1(targets_np, preds_np, average="macro",    zero_division=0))
        val_weighted_f1 = float(_f1(targets_np, preds_np, average="weighted", zero_division=0))
        val_accuracy  = float(_acc(targets_np, preds_np))
        n_pred_classes = len(np.unique(preds_np))

        # ── Checkpoint validity ───────────────────────────────────────────────
        ckpt_valid, ckpt_reason = _checkpoint_valid(logits_np, targets_np, val_loss, NUM_CLASSES)

        # ── Save last_model.pt every epoch ───────────────────────────────────
        torch.save(
            {"model_state_dict": model.state_dict(),
             "epoch": epoch, "val_macro_f1": val_macro_f1},
            _out_dir / "last_model.pt",
        )

        # ── Save best_model.pt if valid and improved ──────────────────────────
        improved = ckpt_valid and (val_macro_f1 > best_val_macro_f1)
        if improved:
            best_val_macro_f1 = val_macro_f1
            best_epoch = epoch
            patience_counter = 0
            torch.save(
                {"model_state_dict": model.state_dict(),
                 "epoch": epoch, "val_macro_f1": val_macro_f1,
                 "activity_classes": ACTIVITY_CLASS_NAMES,
                 "label_remap": LABEL_REMAP},
                _out_dir / "best_model.pt",
            )
            ckpt_tag = "[BEST]"
        else:
            patience_counter += 1
            ckpt_tag = f"[ok, patience={patience_counter}/{PATIENCE}]"
            if not ckpt_valid:
                ckpt_tag = f"[SKIP:{ckpt_reason}]"

        log.info(
            f"Epoch {epoch:03d}/{args.epochs} | "
            f"train_loss={train_loss:.4f} val_loss={val_loss:.4f} | "
            f"macro_f1={val_macro_f1:.4f} acc={val_accuracy:.3f} | "
            f"n_pred_cls={n_pred_classes} | {ckpt_tag}"
        )

        history.append({
            "epoch":          epoch,
            "train_loss":     round(train_loss,     5),
            "val_loss":       round(val_loss,       5),
            "val_macro_f1":   round(val_macro_f1,   5),
            "val_weighted_f1":round(val_weighted_f1,5),
            "val_accuracy":   round(val_accuracy,   4),
            "n_pred_classes": n_pred_classes,
            "checkpoint_valid": ckpt_valid,
        })

        if patience_counter >= PATIENCE and not args.smoke:
            log.info(f"Early stopping triggered at epoch {epoch} (patience={PATIENCE})")
            break

    total_time = time.time() - t0
    log.info(f"Training complete in {total_time:.1f}s")

    # ── Load best model for evaluation ────────────────────────────────────────
    best_ckpt = _out_dir / "best_model.pt"
    if best_ckpt.exists():
        ckpt = torch.load(str(best_ckpt), map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model_state_dict"])
        log.info(f"Loaded best_model.pt (epoch={best_epoch}) for evaluation")
    else:
        log.warning("best_model.pt not saved (all epochs failed checkpoint validity). Using last model.")

    # ── Full test evaluation ──────────────────────────────────────────────────
    test_metrics = run_eval(model, X_te, y_te, src_te, device)

    # ── Save outputs ─────────────────────────────────────────────────────────
    # training_history.json
    with open(_out_dir / "training_history.json", "w") as f:
        json.dump(history, f, indent=2)

    # metrics.json
    metrics_out = {
        "accuracy":         test_metrics["accuracy"],
        "macro_f1":         test_metrics["macro_f1"],
        "weighted_f1":      test_metrics["weighted_f1"],
        "best_epoch":       best_epoch,
        "best_val_macro_f1": round(best_val_macro_f1, 5),
        "activity_classes": ACTIVITY_CLASS_NAMES,
        "label_remap":      {str(k): v for k, v in LABEL_REMAP.items()},
    }
    with open(_out_dir / "metrics.json", "w") as f:
        json.dump(metrics_out, f, indent=2)

    # confusion_matrix.json
    with open(_out_dir / "confusion_matrix.json", "w") as f:
        json.dump({
            "labels": ACTIVITY_CLASS_NAMES,
            "matrix": test_metrics["confusion_matrix"],
        }, f, indent=2)

    # prediction_distribution.json
    with open(_out_dir / "prediction_distribution.json", "w") as f:
        json.dump(test_metrics["prediction_distribution"], f, indent=2)

    # per_class_metrics.json
    with open(_out_dir / "per_class_metrics.json", "w") as f:
        json.dump(test_metrics["per_class"], f, indent=2)

    # source_breakdown.json
    with open(_out_dir / "source_breakdown.json", "w") as f:
        json.dump(test_metrics["source_breakdown"], f, indent=2)

    # activity_expert_report.md
    train_cfg = {
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "optimizer": "AdamW (weight_decay=1e-4)",
        "scheduler": f"CosineAnnealingLR (T_max={args.epochs}, eta_min=1e-5)",
        "loss": "CrossEntropyLoss (inverse-frequency class weights)",
        "early_stopping_patience": PATIENCE,
        "device": str(device),
        "seed": args.seed,
        "num_classes": NUM_CLASSES,
        "input_normalization": "z-score per channel (mean/std from train split)" if not args.smoke else "none (smoke mode)",
    }
    report_md = build_report(
        audit_tr, audit_val, audit_te,
        best_epoch, best_val_macro_f1,
        history, test_metrics,
        n_params, train_cfg, _out_dir,
        smoke=args.smoke,
    )
    with open(_out_dir / "activity_expert_report.md", "w", encoding="utf-8") as f:
        f.write(report_md)

    # ── Final summary ─────────────────────────────────────────────────────────
    log.info("=== Activity Expert Training Complete ===")
    log.info(f"  accuracy        : {test_metrics['accuracy']}")
    log.info(f"  macro_f1        : {test_metrics['macro_f1']}")
    log.info(f"  weighted_f1     : {test_metrics['weighted_f1']}")
    log.info(f"  best_epoch      : {best_epoch}")
    log.info(f"  best_val_macro_f1: {best_val_macro_f1:.5f}")
    log.info(f"  Output dir      : {_out_dir}")
    log.info("")
    log.info("Per-class test metrics:")
    for cls, vals in test_metrics["per_class"].items():
        log.info(f"  {cls:<15} prec={vals['precision']:.3f}  rec={vals['recall']:.3f}  f1={vals['f1']:.3f}  n={vals['support']:,}")


if __name__ == "__main__":
    main()

