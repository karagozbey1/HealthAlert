"""
train_fall_expert.py
─────────────────────────────────────────────────────────────────────────────
Phase 3 — Train the Fall Detection Expert (binary: normal=0, fall=1)

This is the FIRST expert trained in the hybrid redesign.
No multi-task. No PPG. IMU-only. near_fall excluded from training.

Design rules enforced here:
  - Only datasets allowed for fall_detection per hybrid_task_routing.yaml
  - near_fall windows (label=2) excluded from training, kept for holdout analysis
  - No WeightedRandomSampler
  - Checkpoint rejection if collapse detected
  - best_model.pt saved only when checkpoint_valid=True

Usage:
  cd healthalert_final_ai/
  python scripts/train_fall_expert.py
  python scripts/train_fall_expert.py --epochs 20 --device cpu --smoke

Output:
  outputs/hybrid_redesign/fall_expert/
    best_model.pt
    last_model.pt
    metrics.json
    training_history.json
    confusion_matrix.json
    prediction_distribution.json
    near_fall_holdout_analysis.json
    fall_expert_report.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import yaml
from torch.utils.data import DataLoader, TensorDataset

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.healthalert.models.fall_expert import build_fall_expert
from src.healthalert.training.fall_expert_trainer import FallExpertTrainer
from src.healthalert.evaluation.fall_expert_eval import evaluate_fall_expert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("healthalert.train_fall_expert")

ROUTING_CFG = PROJECT_ROOT / "config" / "hybrid_task_routing.yaml"
OUT_DIR = PROJECT_ROOT / "outputs" / "hybrid_redesign" / "fall_expert"
DATA_ROOT = PROJECT_ROOT / "data"
WINDOWED_DATASET_ROOT = PROJECT_ROOT / "outputs" / "windowed_dataset"

# ─── Constants ────────────────────────────────────────────────────────────────
LABEL_NORMAL = 0
LABEL_FALL = 1
LABEL_NEAR_FALL = 2


# ─── Routing check ────────────────────────────────────────────────────────────

def load_allowed_datasets() -> List[str]:
    with open(ROUTING_CFG, encoding="utf-8") as f:
        routing = yaml.safe_load(f)
    return routing.get("fall_detection", {}).get("allowed_datasets", [])


# ─── Data loading helpers ─────────────────────────────────────────────────────

# Primary consolidated NPZ location produced by the dataset preparation pipeline
FALL_DETECTION_NPZ_DIR = WINDOWED_DATASET_ROOT / "fall_detection"


def _find_consolidated_npz(split: str) -> Optional[Path]:
    """Return the consolidated fall_detection NPZ for `split` if it exists."""
    p = FALL_DETECTION_NPZ_DIR / f"{split}.npz"
    return p if p.exists() else None


def _find_npz_files(dataset_name: str, split: str) -> List[Path]:
    """Search for per-dataset NPZ files (fallback when consolidated NPZ is missing)."""
    candidates: List[Path] = []
    # outputs/windowed_dataset/<dataset>/<split>*.npz
    base = WINDOWED_DATASET_ROOT / dataset_name
    if base.exists():
        candidates.extend(base.glob(f"*{split}*.npz"))
        candidates.extend(base.glob(f"{split}*.npz"))
    # data/splits/<dataset>/<split>*.npz
    split_base = DATA_ROOT / "splits" / dataset_name
    if split_base.exists():
        candidates.extend(split_base.glob(f"*{split}*.npz"))
    # data/windowed/<dataset>/<split>*.npz
    win_base = DATA_ROOT / "windowed" / dataset_name
    if win_base.exists():
        candidates.extend(win_base.glob(f"*{split}*.npz"))
    return list(set(candidates))


def _load_npz_arrays(npz_path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """Load X (windows) and y (labels) from an NPZ file."""
    data = np.load(str(npz_path), allow_pickle=True)
    keys = list(data.keys())
    # X key
    x_key = next((k for k in ["X", "windows", "data", "imu", "x"] if k in keys), None)
    if x_key is None:
        raise ValueError(f"No known X key found in {npz_path}. Keys: {keys}")
    X = data[x_key].astype(np.float32)
    # y key
    y_key = next((k for k in ["y", "labels", "label", "Y"] if k in keys), None)
    if y_key is None:
        raise ValueError(f"No known y key found in {npz_path}. Keys: {keys}")
    y = data[y_key].flatten().astype(np.int64)
    return X, y


def _normalize_label(y: np.ndarray, label_map: Optional[Dict[int, int]] = None) -> np.ndarray:
    """Map label integers to normal=0, fall=1. Unknown labels are excluded later."""
    if label_map:
        mapped = np.full_like(y, fill_value=-1)
        for src, dst in label_map.items():
            mapped[y == src] = dst
        return mapped
    return y


def load_split_data(
    allowed_datasets: List[str],
    split: str,
    smoke: bool = False,
    exclude_sources: Optional[List[str]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Load all IMU windows for `split` from the prepared public-dataset NPZ files.

    Primary search: outputs/windowed_dataset/fall_detection/{split}.npz
    Fallback:       per-dataset NPZ files under outputs/windowed_dataset/<dataset>/

    Args:
        exclude_sources: dataset names (case-insensitive) to drop when loading
                         a consolidated NPZ that contains a ``metadata`` array.
    Returns:
      X: (N, channels, window_length) or (N, window_length, channels)  float32
      y: (N,)  int64 — 0=normal, 1=fall, 2=near_fall
    """
    import json as _json_local  # avoid shadowing module-level json import
    # ── 1. Consolidated NPZ (primary path) ──────────────────────────────────
    consolidated = _find_consolidated_npz(split)
    if consolidated is not None:
        log.info(f"  [{split}] Loading consolidated NPZ: {consolidated}")
        try:
            raw = np.load(str(consolidated), allow_pickle=True)
            X, y = _load_npz_arrays(consolidated)
            # ── Source filtering (e.g. exclude UMAFall) ───────────────────
            if exclude_sources and "metadata" in raw.files:
                excl_set = {s.lower() for s in exclude_sources}
                meta = raw["metadata"]
                keep = np.array(
                    [_json_local.loads(str(m))["dataset_name"].lower() not in excl_set
                     for m in meta],
                    dtype=bool,
                )
                n_before = len(y)
                X, y = X[keep], y[keep]
                n_excluded = n_before - int(keep.sum())
                log.info(
                    f"  [{split}] Source filter removed {n_excluded:,} windows from "
                    f"{exclude_sources} ({n_before:,} → {len(y):,})"
                )
            log.info(f"  [{split}] Loaded {X.shape} windows, {len(y)} labels")
            if smoke:
                idx = np.random.RandomState(42).permutation(len(y))[: min(2000, len(y))]
                X, y = X[idx], y[idx]
            return X, y
        except Exception as exc:
            log.warning(f"  [{split}] Failed to load consolidated NPZ: {exc}")

    # ── 2. Per-dataset NPZ fallback ─────────────────────────────────────────
    all_X: List[np.ndarray] = []
    all_y: List[np.ndarray] = []
    for ds_name in allowed_datasets:
        npz_files = _find_npz_files(ds_name, split)
        if not npz_files:
            log.debug(f"  [{split}] No NPZ found for dataset: {ds_name}")
            continue
        for npz_path in npz_files:
            try:
                X, y = _load_npz_arrays(npz_path)
                log.info(f"  [{split}] {ds_name}: {X.shape} from {npz_path.name}")
                all_X.append(X)
                all_y.append(y)
            except Exception as exc:
                log.warning(f"  [{split}] Failed to load {npz_path}: {exc}")

    if not all_X:
        return np.empty((0,), dtype=np.float32), np.empty((0,), dtype=np.int64)

    X_all = np.concatenate(all_X, axis=0)
    y_all = np.concatenate(all_y, axis=0)

    if smoke:
        idx = np.random.RandomState(42).permutation(len(y_all))[: min(2000, len(y_all))]
        X_all = X_all[idx]
        y_all = y_all[idx]

    return X_all, y_all


def prepare_tensors(
    X: np.ndarray,
    y: np.ndarray,
    exclude_near_fall: bool = True,
) -> Tuple[torch.Tensor, torch.Tensor, np.ndarray]:
    """
    Convert numpy arrays to torch tensors.
    Excludes near_fall (label=2) from training data.
    Returns (X_tensor, y_tensor, near_fall_X) where near_fall_X are the excluded windows.
    """
    near_fall_mask = y == LABEL_NEAR_FALL

    if exclude_near_fall:
        keep_mask = ~near_fall_mask
        X_used = X[keep_mask]
        y_used = y[keep_mask]
    else:
        X_used = X
        y_used = y

    # Only keep binary labels 0 and 1
    valid_mask = (y_used == LABEL_NORMAL) | (y_used == LABEL_FALL)
    X_used = X_used[valid_mask]
    y_used = y_used[valid_mask]

    # Ensure shape is (N, channels, window_length)
    if X_used.ndim == 2:
        X_used = X_used[:, np.newaxis, :]  # (N, 1, L)
    elif X_used.ndim == 3 and X_used.shape[1] > X_used.shape[2]:
        # (N, L, C) → (N, C, L)
        X_used = X_used.transpose(0, 2, 1)

    near_fall_X = X[near_fall_mask] if exclude_near_fall else np.empty((0,))

    X_t = torch.from_numpy(X_used.astype(np.float32))
    y_t = torch.from_numpy(y_used.astype(np.float32))
    return X_t, y_t, near_fall_X


def build_loader(X: torch.Tensor, y: torch.Tensor, batch_size: int, shuffle: bool) -> DataLoader:
    ds = TensorDataset(X, y)
    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle, num_workers=0, pin_memory=False)


# ─── Normalization ────────────────────────────────────────────────────────────

def normalize_imu(
    X_train: np.ndarray,
    X_val: np.ndarray,
    X_test: np.ndarray,
    clip_g: float = 50.0,
    out_dir: Optional[Path] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Clip IMU values to a physical range then z-score per channel using
    training-set statistics.  Statistics are saved to out_dir/imu_norm_stats.json
    so the same transform can be applied at inference time.

    Args:
        X_train / X_val / X_test: shape (N, window_length, channels)  — time-last NOT yet transposed
        clip_g: clip to ±clip_g before computing statistics (handles raw-ADC outliers)
        out_dir: if given, writes imu_norm_stats.json there
    """
    # 1. Clip extreme outlier values (sentinel / raw ADC counts)
    X_train = np.clip(X_train, -clip_g, clip_g)
    X_val   = np.clip(X_val,   -clip_g, clip_g)
    X_test  = np.clip(X_test,  -clip_g, clip_g)

    # 2. Per-channel statistics from training set: shape (1, 1, C)
    mean = X_train.mean(axis=(0, 1), keepdims=True)  # (1, L, C) → squeeze over N and L
    std  = X_train.std( axis=(0, 1), keepdims=True) + 1e-8

    X_train = (X_train - mean) / std
    X_val   = (X_val   - mean) / std
    X_test  = (X_test  - mean) / std

    log.info(
        f"IMU normalized — clip_g={clip_g}, "
        f"mean={mean.flatten().round(3).tolist()}, "
        f"std={std.flatten().round(3).tolist()}"
    )

    if out_dir is not None:
        import json as _json
        stats = {
            "clip_g": clip_g,
            "mean_per_channel": mean.flatten().tolist(),
            "std_per_channel": std.flatten().tolist(),
        }
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        with open(Path(out_dir) / "imu_norm_stats.json", "w") as f:
            _json.dump(stats, f, indent=2)

    return X_train, X_val, X_test


# ─── Synthetic fallback for smoke run when no real data available ─────────────

def _make_synthetic_data(n: int, channels: int, window_length: int, seed: int = 42) -> Tuple[np.ndarray, np.ndarray]:
    """Generate synthetic IMU windows for smoke-testing when no real data exists."""
    rng = np.random.RandomState(seed)
    X = rng.randn(n, channels, window_length).astype(np.float32)
    # 60% normal, 40% fall
    y = (rng.rand(n) > 0.6).astype(np.int64)
    # Make fall windows slightly more energetic
    fall_idx = y == 1
    X[fall_idx] *= 2.5
    return X, y


# ─── Main ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="HealthAlert Fall Expert Training")
    p.add_argument("--epochs", type=int, default=None)
    p.add_argument("--batch_size", type=int, default=64)
    p.add_argument("--device", type=str, default="auto")
    p.add_argument("--smoke", action="store_true", help="Smoke run (2000 windows max, 5 epochs)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--lr", type=float, default=None)
    p.add_argument(
        "--pos_weight", type=float, default=None,
        help="BCEWithLogitsLoss pos_weight for fall class. "
             "Default: auto-computed from training label counts (n_normal/n_fall), capped at 3.0. "
             "Set to 1.0 to disable class weighting.",
    )
    p.add_argument(
        "--out_dir", type=str, default=None,
        help="Override output directory. Default: outputs/hybrid_redesign/fall_expert/",
    )
    p.add_argument(
        "--exclude_sources", type=str, default=None,
        help="Comma-separated dataset names to exclude from consolidated NPZ loading "
             "(matched case-insensitively against metadata.dataset_name). "
             "Example: --exclude_sources UMAFall",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    # Resolve output directory
    _out_dir: Path = Path(args.out_dir) if args.out_dir else OUT_DIR
    _out_dir.mkdir(parents=True, exist_ok=True)

    # Resolve source exclusions
    _exclude_sources: List[str] = (
        [s.strip() for s in args.exclude_sources.split(",")]
        if args.exclude_sources else []
    )
    if _exclude_sources:
        log.info(f"Source exclusion active — will drop from consolidated NPZ: {_exclude_sources}")

    # Device
    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    log.info(f"Device: {device}")

    # Config
    epochs = args.epochs or (5 if args.smoke else 30)
    batch_size = args.batch_size

    trainer_cfg: Dict[str, Any] = {
        "training": {
            "epochs": epochs,
            "early_stopping_patience": 5 if args.smoke else 10,
            "gradient_clip": 1.0,
            "fall_threshold": 0.5,
        },
        "optimizer": {"lr": args.lr or 3e-4, "weight_decay": 1e-4},
        "scheduler": {"eta_min": 1e-5},
        "pos_weight": args.pos_weight,  # resolved after data load below
    }

    model_cfg: Dict[str, Any] = {
        "in_channels": 6,
        "cnn_channels": [32, 64, 128],
        "kernel_size": 5,
        "use_gru": True,
        "gru_hidden": 64,
        "dropout": 0.3,
        "window_length": 200,
    }

    # Allowed datasets
    allowed_datasets = load_allowed_datasets()
    log.info(f"Allowed datasets for fall_detection: {allowed_datasets}")

    # Load data
    log.info("Loading training data …")
    X_train, y_train = load_split_data(allowed_datasets, "train", smoke=args.smoke, exclude_sources=_exclude_sources)
    log.info(f"Loading validation data …")
    X_val, y_val = load_split_data(allowed_datasets, "val", smoke=args.smoke, exclude_sources=_exclude_sources)
    log.info(f"Loading test data …")
    X_test, y_test = load_split_data(allowed_datasets, "test", smoke=args.smoke, exclude_sources=_exclude_sources)

    # ── Fail loudly if no real data and not a smoke run ────────────────────
    if len(X_train) == 0:
        if not args.smoke:
            log.error(
                "\n"
                "═══════════════════════════════════════════════════════════════\n"
                "  FATAL: No prepared public-dataset NPZ files found.\n"
                "\n"
                "  Expected location:\n"
                f"    {FALL_DETECTION_NPZ_DIR / 'train.npz'}\n"
                f"    {FALL_DETECTION_NPZ_DIR / 'val.npz'}\n"
                f"    {FALL_DETECTION_NPZ_DIR / 'test.npz'}\n"
                "\n"
                "  Run the dataset preparation pipeline first:\n"
                "    python scripts/prepare_fall_expert_dataset.py\n"
                "\n"
                "  To run a structural smoke test with synthetic data:\n"
                "    python scripts/train_fall_expert.py --smoke\n"
                "═══════════════════════════════════════════════════════════════"
            )
            sys.exit(1)
        # Smoke run: synthetic fallback is allowed
        log.warning("No real training data found — using synthetic data for smoke test.")
        n_train = 1600
        n_val = 400
        n_test = 200
        X_train, y_train = _make_synthetic_data(n_train, 6, 200, seed=args.seed)
        X_val, y_val = _make_synthetic_data(n_val, 6, 200, seed=args.seed + 1)
        X_test, y_test = _make_synthetic_data(n_test, 6, 200, seed=args.seed + 2)
        log.info(f"  Synthetic train: {X_train.shape}, val: {X_val.shape}, test: {X_test.shape}")

    # Log class distribution
    for split_name, y_arr in [("train", y_train), ("val", y_val), ("test", y_test)]:
        if len(y_arr) == 0:
            continue
        unique, counts = np.unique(y_arr, return_counts=True)
        log.info(f"  {split_name} raw labels: {dict(zip(unique.tolist(), counts.tolist()))}")

    # ── Normalize IMU data ────────────────────────────────────────────────────
    # Required because some datasets store raw ADC counts / physical-unit data
    # at different scales.  Clip to ±50 g then z-score per channel using
    # training-set statistics.  Stats saved to OUT_DIR for inference reuse.
    if X_train.ndim == 3:
        # ensure shape is (N, L, C) before normalize (channels last)
        if X_train.shape[1] < X_train.shape[2]:
            # already (N, C, L) — transpose to (N, L, C) for normalization
            X_train = X_train.transpose(0, 2, 1)
            X_val   = X_val.transpose(0, 2, 1)
            X_test  = X_test.transpose(0, 2, 1)
    X_train, X_val, X_test = normalize_imu(X_train, X_val, X_test, clip_g=50.0, out_dir=_out_dir)

    # Prepare tensors (exclude near_fall from train/val)
    X_train_t, y_train_t, nf_train = prepare_tensors(X_train, y_train, exclude_near_fall=True)
    X_val_t, y_val_t, nf_val = prepare_tensors(X_val, y_val, exclude_near_fall=True)
    X_test_t, y_test_t, nf_test = prepare_tensors(X_test, y_test, exclude_near_fall=False)

    log.info(
        f"After exclusion — train: {len(y_train_t)}, val: {len(y_val_t)}, test: {len(y_test_t)}"
    )
    log.info(
        f"near_fall holdout — train: {len(nf_train)}, val: {len(nf_val)}, test: {len(nf_test)}"
    )

    if len(y_train_t) == 0:
        log.error("No training windows after preprocessing. Aborting.")
        sys.exit(1)

    # ── Resolve pos_weight from training label distribution ───────────────────
    # Compute n_normal / n_fall, then cap at [0.5, 3.0] to avoid extremes.
    # If user passed --pos_weight, use that directly.
    if trainer_cfg["pos_weight"] is None:
        y_np = y_train_t.numpy().astype(np.int64)
        n_normal = int((y_np == LABEL_NORMAL).sum())
        n_fall = int((y_np == LABEL_FALL).sum())
        if n_fall > 0:
            raw_pw = n_normal / n_fall
            # Cap at 1.0: do NOT upweight fall class beyond neutral.
            # Over-weighting fall causes FP cascade on val/test sets that
            # have a higher normal prevalence than the training set.
            # The calibrated bias in FallExpertCNN handles the class prior.
            computed_pw = float(np.clip(raw_pw, 0.5, 1.0))
        else:
            computed_pw = 1.0
        trainer_cfg["pos_weight"] = computed_pw
        log.info(
            f"pos_weight auto-computed: {raw_pw:.3f} (n_normal={n_normal}, n_fall={n_fall}) "
            f"→ capped at {computed_pw:.3f}"
        )
    else:
        log.info(f"pos_weight (user override): {trainer_cfg['pos_weight']}")

    # Adjust window_length from actual data
    actual_window_length = X_train_t.shape[-1]
    model_cfg["window_length"] = actual_window_length
    model_cfg["in_channels"] = X_train_t.shape[1]
    log.info(f"Model input: channels={model_cfg['in_channels']}, window_length={actual_window_length}")

    train_loader = build_loader(X_train_t, y_train_t, batch_size=batch_size, shuffle=True)
    val_loader = build_loader(X_val_t, y_val_t, batch_size=batch_size, shuffle=False)
    test_loader = build_loader(X_test_t, y_test_t, batch_size=batch_size, shuffle=False)

    # Near-fall holdout loader (test set only, if available)
    near_fall_loader: Optional[DataLoader] = None
    if len(nf_test) > 0:
        nf_X = torch.from_numpy(nf_test.astype(np.float32))
        if nf_X.ndim == 2:
            nf_X = nf_X.unsqueeze(1)
        elif nf_X.ndim == 3 and nf_X.shape[1] > nf_X.shape[2]:
            nf_X = nf_X.permute(0, 2, 1)
        nf_ds = TensorDataset(nf_X)
        near_fall_loader = DataLoader(nf_ds, batch_size=batch_size, shuffle=False)

    # Build model
    model = build_fall_expert(model_cfg)
    log.info(f"Model: {sum(p.numel() for p in model.parameters()):,} parameters")

    # Train
    _out_dir.mkdir(parents=True, exist_ok=True)
    trainer = FallExpertTrainer(model=model, cfg=trainer_cfg, device=device, out_dir=_out_dir)
    t0 = time.time()
    history = trainer.fit(train_loader, val_loader)
    elapsed = time.time() - t0
    log.info(f"Training complete in {elapsed:.1f}s")

    # Load best model for evaluation
    best_ckpt = _out_dir / "best_model.pt"
    if best_ckpt.exists():
        ckpt = torch.load(str(best_ckpt), map_location=device)
        model.load_state_dict(ckpt["model_state_dict"])
        log.info("Loaded best_model.pt for evaluation")
    else:
        log.warning("No valid best_model.pt found — evaluating last_model.pt state")

    # Evaluate
    dataset_info = {
        "allowed_datasets": allowed_datasets,
        "label_policy": "binary (normal=0, fall=1); near_fall excluded from training",
        "n_train": int(len(y_train_t)),
        "n_val": int(len(y_val_t)),
        "n_test": int(len(y_test_t)),
        "n_near_fall_excluded_train": int(len(nf_train)),
        "n_near_fall_holdout_test": int(len(nf_test)),
        "window_length": actual_window_length,
        "in_channels": model_cfg["in_channels"],
        "smoke_run": args.smoke,
    }

    results = evaluate_fall_expert(
        model=model,
        test_loader=test_loader,
        device=device,
        out_dir=_out_dir,
        threshold=0.5,
        near_fall_loader=near_fall_loader,
        dataset_info=dataset_info,
    )

    # Save dataset info alongside metrics
    with open(_out_dir / "dataset_info.json", "w") as f:
        json.dump(dataset_info, f, indent=2)

    log.info("=== Fall Expert Training Complete ===")
    log.info(f"  fall_recall       : {results['metrics'].get('fall_recall', '—')}")
    log.info(f"  fall_precision    : {results['metrics'].get('fall_precision', '—')}")
    log.info(f"  normal_recall     : {results['metrics'].get('normal_recall', '—')}")
    log.info(f"  macro_f1          : {results['metrics'].get('macro_f1', '—')}")
    log.info(f"  app_score         : {results['metrics'].get('fall_application_score', '—')}")
    log.info(f"  collapse_detected : {results['metrics'].get('collapse_detected', '—')}")
    log.info(f"  Output dir        : {_out_dir}")


if __name__ == "__main__":
    main()
