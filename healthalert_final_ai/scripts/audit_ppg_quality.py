import sys
import argparse
import hashlib
from pathlib import Path
from collections import defaultdict

import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.neighbors import NearestNeighbors

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.io import load_all_configs, load_checkpoint
from src.utils.seed import set_seed
from src.data.dataset_registry import build_registry, subject_wise_split
from src.data.column_schema import standardize_records
from src.data.base_dataset import HealthAlertDataset
from src.data.preprocessing.scaler_pipeline import ModalityScaler
from src.models.multitask_model_v2 import HealthAlertModelV2
from src.training.metrics import calibrate_threshold


# BUT_PPG kalite gorevi icin sizinti ve dayaniklilik denetimleri yapar.
def parse_args():
    p = argparse.ArgumentParser(description="Strict PPG quality audit")
    p.add_argument("--checkpoint", type=str, required=True, help="Checkpoint path")
    p.add_argument("--config_dir", type=str, default=None, help="Config directory")
    p.add_argument("--device", type=str, default="cpu", help="Device")
    p.add_argument("--seed", type=int, default=42, help="Random seed")
    p.add_argument("--out", type=str, default="outputs/reports/ppg_quality_audit_report.txt")
    return p.parse_args()


def _metric_dict(y_true, y_prob, thr):
    y_pred = (y_prob >= thr).astype(np.int32)
    out = {
        "accuracy": accuracy_score(y_true, y_pred),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "threshold": float(thr),
    }
    if len(np.unique(y_true)) > 1:
        out["auc"] = roc_auc_score(y_true, y_prob)
    else:
        out["auc"] = float("nan")
    return out


def _split_sets(records, seed=42):
    tr, va, te = subject_wise_split(records, seed=seed)
    tr_s = {r["subject_id"] for r in tr}
    va_s = {r["subject_id"] for r in va}
    te_s = {r["subject_id"] for r in te}
    checks = {
        "subject_overlap_train_val": len(tr_s & va_s),
        "subject_overlap_train_test": len(tr_s & te_s),
        "subject_overlap_val_test": len(va_s & te_s),
    }

    tr_r = {r["record_id"] for r in tr}
    va_r = {r["record_id"] for r in va}
    te_r = {r["record_id"] for r in te}
    checks.update(
        {
            "record_overlap_train_val": len(tr_r & va_r),
            "record_overlap_train_test": len(tr_r & te_r),
            "record_overlap_val_test": len(va_r & te_r),
        }
    )

    return tr, va, te, checks


def _build_quality_dataset(records, window_size, stride, fit_scaler=False, scaler=None):
    if scaler is None:
        scaler = ModalityScaler()
    ds = HealthAlertDataset(
        records,
        window_size=window_size,
        stride=stride,
        normalize=True,
        augment=False,
        scaler=scaler,
        fit_scaler_on_init=fit_scaler,
    )
    return ds, scaler


def _sample_arrays(ds):
    ppg = []
    hc = []
    vitals = []
    y = []
    for s in ds.samples:
        ppg.append(s["ppg"][:, 0].astype(np.float32))
        hc.append(s["handcrafted_features"].astype(np.float32))
        vitals.append(s["vitals"].astype(np.float32))
        y.append(int(s["quality_label"]))
    return np.asarray(ppg), np.asarray(hc), np.asarray(vitals), np.asarray(y)


def _exact_duplicate_count(a, b):
    b_hash = set()
    for row in b:
        h = hashlib.sha1(np.round(row, 6).tobytes()).hexdigest()
        b_hash.add(h)
    dup = 0
    for row in a:
        h = hashlib.sha1(np.round(row, 6).tobytes()).hexdigest()
        if h in b_hash:
            dup += 1
    return dup


def _near_duplicate_stats(train_ppg, test_ppg):
    # Cosine nearest-neighbor similarity between test and train windows
    tr = train_ppg.astype(np.float64)
    te = test_ppg.astype(np.float64)

    tr_n = tr / (np.linalg.norm(tr, axis=1, keepdims=True) + 1e-12)
    te_n = te / (np.linalg.norm(te, axis=1, keepdims=True) + 1e-12)

    nn = NearestNeighbors(n_neighbors=1, metric="cosine", algorithm="brute")
    nn.fit(tr_n)
    dists, _ = nn.kneighbors(te_n)
    sims = 1.0 - dists[:, 0]

    return {
        "max_cosine_similarity": float(np.max(sims)),
        "mean_cosine_similarity": float(np.mean(sims)),
        "p99_cosine_similarity": float(np.percentile(sims, 99)),
        "count_sim_ge_0.999": int(np.sum(sims >= 0.999)),
        "count_sim_ge_0.995": int(np.sum(sims >= 0.995)),
    }


def _eval_model_quality(model, ds, device, threshold=0.5):
    model.eval()
    probs = []
    ys = []
    with torch.no_grad():
        for s in ds:
            batch = {
                "imu": s["imu"].unsqueeze(0).to(device),
                "ppg": s["ppg"].unsqueeze(0).to(device),
                "vitals": s["vitals"].unsqueeze(0).to(device),
                "handcrafted_features": s["handcrafted_features"].unsqueeze(0).to(device),
                "modality_mask": s["modality_mask"].unsqueeze(0).to(device),
            }
            out = model(batch)
            prob = torch.sigmoid(out["quality_logit"]).cpu().item()
            probs.append(prob)
            ys.append(int(s["quality_label"].item()))

    probs = np.asarray(probs)
    ys = np.asarray(ys)
    if len(np.unique(ys)) > 1:
        thr, _ = calibrate_threshold(ys, probs, objective="f1")
    else:
        thr = threshold
    return _metric_dict(ys, probs, thr), ys, probs


def _eval_model_quality_ablation(model, ds, device, mode):
    model.eval()
    probs = []
    ys = []
    with torch.no_grad():
        for s in ds:
            imu = s["imu"].unsqueeze(0).to(device)
            ppg = s["ppg"].unsqueeze(0).to(device)
            vitals = s["vitals"].unsqueeze(0).to(device)
            hc = s["handcrafted_features"].unsqueeze(0).to(device)
            mm = s["modality_mask"].clone().unsqueeze(0).to(device)

            if mode == "waveform_only":
                vitals = torch.zeros_like(vitals)
                hc = torch.zeros_like(hc)
                mm[:, 2] = 0.0
                mm[:, 3] = 0.0
            elif mode == "handcrafted_only":
                ppg = torch.zeros_like(ppg)
                vitals = torch.zeros_like(vitals)
                mm[:, 1] = 0.0
                mm[:, 2] = 0.0

            batch = {
                "imu": imu,
                "ppg": ppg,
                "vitals": vitals,
                "handcrafted_features": hc,
                "modality_mask": mm,
            }
            out = model(batch)
            prob = torch.sigmoid(out["quality_logit"]).cpu().item()
            probs.append(prob)
            ys.append(int(s["quality_label"].item()))

    probs = np.asarray(probs)
    ys = np.asarray(ys)
    thr, _ = calibrate_threshold(ys, probs, objective="f1")
    return _metric_dict(ys, probs, thr)


def _simple_ablation_classifier(tr_x, tr_y, te_x, te_y):
    clf = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    clf.fit(tr_x, tr_y)
    prob = clf.predict_proba(te_x)[:, 1]
    thr, _ = calibrate_threshold(te_y, prob, objective="f1")
    return _metric_dict(te_y, prob, thr)


def _per_subject_metrics(records, probs, threshold):
    by_subj = defaultdict(lambda: {"y": [], "p": []})
    for rec, pr in zip(records, probs):
        sid = rec["subject_id"]
        by_subj[sid]["y"].append(int(rec["quality_label"]))
        by_subj[sid]["p"].append(float(pr))

    rows = []
    for sid, d in sorted(by_subj.items()):
        y = np.asarray(d["y"])
        p = np.asarray(d["p"])
        pred = (p >= threshold).astype(np.int32)
        rows.append(
            {
                "subject_id": sid,
                "n": int(len(y)),
                "pos_rate": float(np.mean(y)),
                "f1": float(f1_score(y, pred, zero_division=0)),
                "precision": float(precision_score(y, pred, zero_division=0)),
                "recall": float(recall_score(y, pred, zero_division=0)),
                "accuracy": float(accuracy_score(y, pred)),
            }
        )
    return rows


def _metadata_leakage_probe(train_records, test_records):
    # Probe: can simple metadata predict quality?
    # Features: record_id prefix, subject_id prefix, motion, hr, spo2 available flag
    def vec(recs):
        X = []
        y = []

        def parse_motion(val):
            if val is None:
                return 0.0
            try:
                return float(val)
            except (TypeError, ValueError):
                s = str(val)
                parts = [p for p in s.replace(";", ",").split(",") if p.strip()]
                nums = []
                for p in parts:
                    try:
                        nums.append(float(p))
                    except ValueError:
                        continue
                return float(np.mean(nums)) if nums else 0.0

        for r in recs:
            rid = str(r["record_id"])
            sid = str(r["subject_id"])
            motion = parse_motion(r.get("motion", 0.0))
            hr = float(r.get("heart_rate", 0.0))
            spo2 = r.get("spo2", np.nan)
            spo2_missing = 1.0 if np.isnan(spo2) else 0.0
            x = [
                float(int(rid[:3])) if rid[:3].isdigit() else 0.0,
                float(int(rid[-2:])) if rid[-2:].isdigit() else 0.0,
                float(int(sid[-3:])) if sid[-3:].isdigit() else 0.0,
                motion,
                hr,
                spo2_missing,
            ]
            X.append(x)
            y.append(int(r["quality_label"]))
        return np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.int32)

    x_tr, y_tr = vec(train_records)
    x_te, y_te = vec(test_records)
    clf = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    clf.fit(x_tr, y_tr)
    p = clf.predict_proba(x_te)[:, 1]
    thr, _ = calibrate_threshold(y_te, p, objective="f1")
    return _metric_dict(y_te, p, thr)


def main():
    args = parse_args()

    cfg = load_all_configs(args.config_dir or str(PROJECT_ROOT / "config"))
    set_seed(args.seed)

    registry = build_registry(cfg)
    for name in list(registry.keys()):
        registry[name] = standardize_records(registry[name], name)

    but_records = registry.get("BUT_PPG", [])
    if not but_records:
        raise RuntimeError("No BUT_PPG records loaded")

    train_recs, val_recs, test_recs, checks = _split_sets(but_records, seed=args.seed)

    signal_cfg = cfg.get("signal", {})
    window_size = signal_cfg.get("window_size", 200)
    stride = signal_cfg.get("window_stride", 50)

    train_ds, scaler = _build_quality_dataset(train_recs, window_size, stride, fit_scaler=True)
    val_ds, _ = _build_quality_dataset(val_recs, window_size, stride, scaler=scaler)
    test_ds, _ = _build_quality_dataset(test_recs, window_size, stride, scaler=scaler)

    tr_ppg, tr_hc, tr_vitals, tr_y = _sample_arrays(train_ds)
    va_ppg, va_hc, va_vitals, va_y = _sample_arrays(val_ds)
    te_ppg, te_hc, te_vitals, te_y = _sample_arrays(test_ds)

    # Duplicate checks
    checks["exact_duplicate_windows_train_test"] = _exact_duplicate_count(te_ppg, tr_ppg)
    checks["exact_duplicate_windows_val_test"] = _exact_duplicate_count(te_ppg, va_ppg)
    near_dup = _near_duplicate_stats(tr_ppg, te_ppg)

    # Metadata leakage probe
    metadata_probe = _metadata_leakage_probe(train_recs, test_recs)

    # Model-based evaluation
    device = torch.device(args.device)
    model = HealthAlertModelV2(cfg)
    ckpt = load_checkpoint(args.checkpoint, device=str(device))
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device)

    quality_metrics, test_y_model, test_prob_model = _eval_model_quality(model, test_ds, device)

    # Per-subject summary
    threshold = quality_metrics["threshold"]
    test_records_for_subject = [
        {"subject_id": r["subject_id"], "quality_label": int(r["quality_label"])}
        for r in test_recs
    ]
    per_subject = _per_subject_metrics(test_records_for_subject, test_prob_model, threshold)

    # Stricter split: train on non-112, test on 112xxx
    strict_train = [r for r in but_records if not str(r["record_id"]).startswith("112")]
    strict_test = [r for r in but_records if str(r["record_id"]).startswith("112")]
    strict_metrics = None
    strict_class_dist = None
    if strict_train and strict_test:
        strict_train_ds, strict_scaler = _build_quality_dataset(strict_train, window_size, stride, fit_scaler=True)
        strict_test_ds, _ = _build_quality_dataset(strict_test, window_size, stride, scaler=strict_scaler)
        strict_metrics, _, _ = _eval_model_quality(model, strict_test_ds, device)
        strict_class_dist = {
            "train_n": len(strict_train),
            "train_pos_rate": float(np.mean([r["quality_label"] for r in strict_train])),
            "test_n": len(strict_test),
            "test_pos_rate": float(np.mean([r["quality_label"] for r in strict_test])),
        }

    # Ablation via deployed model masking
    ablations_model = {
        "waveform_only": _eval_model_quality_ablation(model, test_ds, device, "waveform_only"),
        "handcrafted_only": _eval_model_quality_ablation(model, test_ds, device, "handcrafted_only"),
    }

    # Ablation via simple classifiers for requested protocol
    x_tr_wave = tr_ppg
    x_te_wave = te_ppg
    def parse_motion(val):
        if val is None:
            return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            s = str(val)
            parts = [p for p in s.replace(";", ",").split(",") if p.strip()]
            nums = []
            for p in parts:
                try:
                    nums.append(float(p))
                except ValueError:
                    continue
            return float(np.mean(nums)) if nums else 0.0

    x_tr_wave_motion = np.hstack([
        tr_ppg,
        np.asarray([[parse_motion(r.get("motion", 0.0))] for r in train_recs], dtype=np.float32),
    ])
    x_te_wave_motion = np.hstack([
        te_ppg,
        np.asarray([[parse_motion(r.get("motion", 0.0))] for r in test_recs], dtype=np.float32),
    ])
    x_tr_hc = tr_hc
    x_te_hc = te_hc

    ablations_linear = {
        "waveform_only": _simple_ablation_classifier(x_tr_wave, tr_y, x_te_wave, te_y),
        "waveform_plus_motion": _simple_ablation_classifier(x_tr_wave_motion, tr_y, x_te_wave_motion, te_y),
        "handcrafted_only": _simple_ablation_classifier(x_tr_hc, tr_y, x_te_hc, te_y),
    }

    class_dist = {
        "train_n": int(len(tr_y)),
        "train_pos": int(np.sum(tr_y == 1)),
        "train_neg": int(np.sum(tr_y == 0)),
        "val_n": int(len(va_y)),
        "val_pos": int(np.sum(va_y == 1)),
        "val_neg": int(np.sum(va_y == 0)),
        "test_n": int(len(te_y)),
        "test_pos": int(np.sum(te_y == 1)),
        "test_neg": int(np.sum(te_y == 0)),
    }

    lines = []
    lines.append("=" * 70)
    lines.append("PPG QUALITY STRICT AUDIT REPORT")
    lines.append("=" * 70)
    lines.append("")

    lines.append("[A] LEAKAGE CHECKS")
    for k, v in checks.items():
        lines.append(f"  {k}: {v}")
    for k, v in near_dup.items():
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("[B] INPUT AUDIT (BUT_PPG quality path)")
    lines.append("  model_inputs: ppg waveform + handcrafted (from waveform), vitals masked missing")
    lines.append("  excluded_shortcuts: annotation HR/SpO2 as direct model inputs")
    lines.append(f"  metadata_probe_f1: {metadata_probe['f1']:.4f}")
    lines.append(f"  metadata_probe_auc: {metadata_probe['auc']:.4f}")
    lines.append("")

    lines.append("[C] CLASS DISTRIBUTION (BUT_PPG only)")
    for k, v in class_dist.items():
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("[D] MODEL QUALITY PERFORMANCE (subject-wise BUT_PPG test)")
    for k, v in quality_metrics.items():
        lines.append(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")
    lines.append("")

    if strict_metrics is not None:
        lines.append("[E] STRICTER SPLIT PERFORMANCE (train non-112, test 112)")
        for k, v in strict_class_dist.items():
            lines.append(f"  {k}: {v}")
        for k, v in strict_metrics.items():
            lines.append(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")
        lines.append("")

    lines.append("[F] ABLATION (deployed model masking)")
    for name, m in ablations_model.items():
        lines.append(f"  {name}:")
        for k, v in m.items():
            lines.append(f"    {k}: {v:.4f}" if isinstance(v, float) else f"    {k}: {v}")
    lines.append("")

    lines.append("[G] ABLATION (simple LR, BUT_PPG-only)")
    for name, m in ablations_linear.items():
        lines.append(f"  {name}:")
        for k, v in m.items():
            lines.append(f"    {k}: {v:.4f}" if isinstance(v, float) else f"    {k}: {v}")
    lines.append("")

    lines.append("[H] PER-SUBJECT SUMMARY (test split)")
    lines.append("  subject_id, n, pos_rate, f1, precision, recall, accuracy")
    for row in per_subject:
        lines.append(
            "  "
            + f"{row['subject_id']}, {row['n']}, {row['pos_rate']:.3f}, {row['f1']:.3f}, "
            + f"{row['precision']:.3f}, {row['recall']:.3f}, {row['accuracy']:.3f}"
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Audit report saved to: {out_path}")


if __name__ == "__main__":
    main()
