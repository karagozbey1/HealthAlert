"""
Fall Expert Threshold Sweep + Dataset-Source Breakdown + Error Analysis
Usage: python scripts/analyze_fall_expert_thresholds.py
Output: outputs/hybrid_redesign/fall_expert/threshold_analysis_report.md
         outputs/hybrid_redesign/fall_expert/threshold_analysis.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch

# ── project root on path ──────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from healthalert.models.fall_expert import FallExpertCNN  # noqa: E402

# ── paths ─────────────────────────────────────────────────────────────────────
OUT_DIR   = ROOT / "outputs" / "hybrid_redesign" / "fall_expert"
MODEL_PT  = OUT_DIR / "best_model.pt"
NORM_JSON = OUT_DIR / "imu_norm_stats.json"
TEST_NPZ  = ROOT / "outputs" / "windowed_dataset" / "fall_detection" / "test.npz"

THRESHOLDS = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]

# ── normalization ─────────────────────────────────────────────────────────────
def normalize_imu(x: np.ndarray, clip_g: float, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    x = np.clip(x, -clip_g, clip_g)
    return (x - mean) / (std + 1e-8)

# ── metrics helper ────────────────────────────────────────────────────────────
def binary_metrics(y_true, y_pred):
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    fall_recall    = tp / (tp + fn + 1e-9)
    fall_prec      = tp / (tp + fp + 1e-9)
    normal_recall  = tn / (tn + fp + 1e-9)
    fall_f1        = 2 * fall_prec * fall_recall / (fall_prec + fall_recall + 1e-9)
    normal_f1      = 2 * normal_recall * (tn / (tn + fn + 1e-9)) / (
                         normal_recall + (tn / (tn + fn + 1e-9)) + 1e-9)
    macro_f1       = (fall_f1 + normal_f1) / 2
    app_score      = (0.35 * fall_recall + 0.25 * fall_prec +
                      0.25 * macro_f1   + 0.15 * normal_recall)
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "fall_recall":    round(fall_recall,    5),
        "fall_precision": round(fall_prec,      5),
        "normal_recall":  round(normal_recall,  5),
        "fall_f1":        round(fall_f1,        5),
        "macro_f1":       round(macro_f1,       5),
        "app_score":      round(app_score,      5),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Fall Expert Threshold Sweep")
    ap.add_argument(
        "--model_dir", type=str, default=None,
        help="Directory containing best_model.pt and imu_norm_stats.json. "
             "Analysis outputs (threshold_analysis.json / .md) are also written here. "
             "Default: outputs/hybrid_redesign/fall_expert/",
    )
    ap.add_argument(
        "--exclude_sources", type=str, default=None,
        help="Comma-separated dataset names to exclude from test evaluation "
             "(e.g. --exclude_sources UMAFall)",
    )
    args = ap.parse_args()
    model_dir = Path(args.model_dir) if args.model_dir else OUT_DIR
    model_pt  = model_dir / "best_model.pt"
    norm_json = model_dir / "imu_norm_stats.json"
    exclude_src: list = (
        [s.strip() for s in args.exclude_sources.split(",")]
        if args.exclude_sources else []
    )

    # ── load norm stats ────────────────────────────────────────────────────────
    norm = json.loads(norm_json.read_text())
    clip_g = norm["clip_g"]
    mean   = np.array(norm["mean_per_channel"], dtype=np.float32)
    std    = np.array(norm["std_per_channel"],  dtype=np.float32)

    # ── load test NPZ ──────────────────────────────────────────────────────────
    print("Loading test NPZ …")
    data = np.load(str(TEST_NPZ), allow_pickle=True)
    imu_raw  = data["imu"].astype(np.float32)          # (N, 200, 6)
    labels   = data["labels"].astype(np.int64)          # (N,)
    metadata = data["metadata"]                          # (N,) JSON strings

    # ── parse metadata ─────────────────────────────────────────────────────────
    print("Parsing metadata …")
    sources = np.array([json.loads(m)["dataset_name"] for m in metadata])

    # ── exclude near_fall (label=2) ────────────────────────────────────────────
    mask    = labels != 2
    imu_raw = imu_raw[mask]
    labels  = labels[mask]
    sources = sources[mask]
    print(f"Test windows after near_fall exclusion: {len(labels)}")

    # ── exclude sources if requested ──────────────────────────────────────────
    if exclude_src:
        excl_set = {s.lower() for s in exclude_src}
        src_keep = np.array([s.lower() not in excl_set for s in sources], dtype=bool)
        n_before = len(labels)
        imu_raw = imu_raw[src_keep]
        labels  = labels[src_keep]
        sources = sources[src_keep]
        print(f"Source filter removed {n_before - src_keep.sum():,} windows from {exclude_src} "
              f"({n_before:,} → {len(labels):,})")

    unique_src, src_counts = np.unique(sources, return_counts=True)
    print("Sources:", dict(zip(unique_src, src_counts)))

    # ── normalize IMU ──────────────────────────────────────────────────────────
    imu_norm = normalize_imu(imu_raw, clip_g, mean, std)          # (N,200,6)
    X = torch.tensor(imu_norm.transpose(0, 2, 1), dtype=torch.float32)  # (N,6,200)

    # ── load model ─────────────────────────────────────────────────────────────
    print("Loading model …")
    ckpt = torch.load(str(model_pt), map_location="cpu", weights_only=False)
    model = FallExpertCNN(in_channels=6, window_length=200)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    # ── inference in batches ───────────────────────────────────────────────────
    print("Running inference …")
    batch_size = 512
    probs_list = []
    with torch.no_grad():
        for i in range(0, len(X), batch_size):
            batch = X[i:i + batch_size]
            out   = model(batch)
            prob  = torch.sigmoid(out["logit"]).squeeze(-1).cpu().numpy()
            probs_list.append(prob)
    probs = np.concatenate(probs_list)       # (N,)
    y_true = labels                           # 0=normal, 1=fall

    # ══════════════════════════════════════════════════════════════════════════
    # 1. THRESHOLD SWEEP
    # ══════════════════════════════════════════════════════════════════════════
    print("\n=== THRESHOLD SWEEP ===")
    sweep_rows = []
    for t in THRESHOLDS:
        y_pred = (probs >= t).astype(np.int64)
        m = binary_metrics(y_true, y_pred)
        m["threshold"] = t
        sweep_rows.append(m)
        print(f"  t={t:.2f} | fall_recall={m['fall_recall']:.4f} "
              f"fall_prec={m['fall_precision']:.4f} "
              f"normal_recall={m['normal_recall']:.4f} "
              f"macro_f1={m['macro_f1']:.4f} "
              f"FP={m['fp']} FN={m['fn']} "
              f"app={m['app_score']:.4f}")

    # ══════════════════════════════════════════════════════════════════════════
    # 2. DATASET-SOURCE BREAKDOWN (at threshold=0.40 and 0.50)
    # ══════════════════════════════════════════════════════════════════════════
    print("\n=== DATASET-SOURCE BREAKDOWN ===")
    breakdown = {}
    for src in sorted(unique_src):
        idx   = sources == src
        yt    = y_true[idx]
        pp    = probs[idx]
        n_tot = int(idx.sum())
        n_fall   = int((yt == 1).sum())
        n_normal = int((yt == 0).sum())
        row = {"n_total": n_tot, "n_fall": n_fall, "n_normal": n_normal}
        for t in [0.40, 0.50]:
            yp = (pp >= t).astype(np.int64)
            m  = binary_metrics(yt, yp)
            row[f"t{int(t*100)}"] = m
        breakdown[src] = row
        m40 = row["t40"]
        print(f"  {src:30s}  n={n_tot:6d} (fall={n_fall:5d} normal={n_normal:5d}) "
              f"| @0.40 rec={m40['fall_recall']:.3f} prec={m40['fall_precision']:.3f} "
              f"macro_f1={m40['macro_f1']:.3f} FN={m40['fn']} FP={m40['fp']}")

    # ══════════════════════════════════════════════════════════════════════════
    # 3. ERROR ANALYSIS
    # ══════════════════════════════════════════════════════════════════════════
    print("\n=== ERROR ANALYSIS (threshold=0.40) ===")
    T_ERR = 0.40
    y_pred_err = (probs >= T_ERR).astype(np.int64)

    fn_mask = (y_pred_err == 0) & (y_true == 1)   # missed falls
    fp_mask = (y_pred_err == 1) & (y_true == 0)   # false alarms

    # FN by source
    fn_by_src = {}
    for src in sorted(unique_src):
        n_fn     = int(((sources == src) & fn_mask).sum())
        n_fall_s = int(((sources == src) & (y_true == 1)).sum())
        fn_rate  = n_fn / (n_fall_s + 1e-9)
        fn_by_src[src] = {"fn": n_fn, "total_falls": n_fall_s, "fn_rate": round(fn_rate, 4)}

    # FP by source
    fp_by_src = {}
    for src in sorted(unique_src):
        n_fp       = int(((sources == src) & fp_mask).sum())
        n_normal_s = int(((sources == src) & (y_true == 0)).sum())
        fp_rate    = n_fp / (n_normal_s + 1e-9)
        fp_by_src[src] = {"fp": n_fp, "total_normals": n_normal_s, "fp_rate": round(fp_rate, 4)}

    print("  FN by source (threshold=0.40):")
    for src, v in sorted(fn_by_src.items(), key=lambda x: -x[1]["fn"]):
        print(f"    {src:30s}  FN={v['fn']:5d} / {v['total_falls']:5d} falls  "
              f"miss_rate={v['fn_rate']:.3f}")

    print("  FP by source (threshold=0.40):")
    for src, v in sorted(fp_by_src.items(), key=lambda x: -x[1]["fp"]):
        print(f"    {src:30s}  FP={v['fp']:5d} / {v['total_normals']:5d} normals  "
              f"fp_rate={v['fp_rate']:.3f}")

    # FN confidence distribution
    fn_probs = probs[fn_mask]
    fp_probs = probs[fp_mask]
    fn_prob_buckets = {
        "0.00-0.10": int((fn_probs < 0.10).sum()),
        "0.10-0.20": int(((fn_probs >= 0.10) & (fn_probs < 0.20)).sum()),
        "0.20-0.30": int(((fn_probs >= 0.20) & (fn_probs < 0.30)).sum()),
        "0.30-0.40": int(((fn_probs >= 0.30) & (fn_probs < 0.40)).sum()),
    }
    fp_prob_buckets = {
        "0.40-0.50": int(((fp_probs >= 0.40) & (fp_probs < 0.50)).sum()),
        "0.50-0.60": int(((fp_probs >= 0.50) & (fp_probs < 0.60)).sum()),
        "0.60-0.70": int(((fp_probs >= 0.60) & (fp_probs < 0.70)).sum()),
        "0.70-1.00": int((fp_probs >= 0.70).sum()),
    }
    print(f"\n  Total FN={fn_mask.sum()}, FP={fp_mask.sum()} at threshold=0.40")
    print("  FN probability distribution:", fn_prob_buckets)
    print("  FP probability distribution:", fp_prob_buckets)

    # ══════════════════════════════════════════════════════════════════════════
    # 4. BEST THRESHOLD RECOMMENDATION
    # ══════════════════════════════════════════════════════════════════════════
    # Find threshold that maximises app_score with fall_recall >= 0.70
    candidates = [(r["threshold"], r["app_score"], r["fall_recall"], r["macro_f1"])
                  for r in sweep_rows if r["fall_recall"] >= 0.70]
    if candidates:
        best = max(candidates, key=lambda x: x[1])
    else:
        best = max([(r["threshold"], r["app_score"], r["fall_recall"], r["macro_f1"])
                    for r in sweep_rows], key=lambda x: x[1])
    print(f"\n  Recommended threshold: {best[0]:.2f} "
          f"(app_score={best[1]:.4f}, fall_recall={best[2]:.4f}, macro_f1={best[3]:.4f})")

    # ══════════════════════════════════════════════════════════════════════════
    # SAVE JSON
    # ══════════════════════════════════════════════════════════════════════════
    report = {
        "threshold_sweep": sweep_rows,
        "dataset_breakdown": breakdown,
        "error_analysis": {
            "threshold": T_ERR,
            "total_fn": int(fn_mask.sum()),
            "total_fp": int(fp_mask.sum()),
            "fn_by_source": fn_by_src,
            "fp_by_source": fp_by_src,
            "fn_prob_buckets": fn_prob_buckets,
            "fp_prob_buckets": fp_prob_buckets,
        },
        "recommendation": {
            "threshold": best[0],
            "app_score": best[1],
            "fall_recall": best[2],
            "macro_f1": best[3],
        },
    }
    json_path = model_dir / "threshold_analysis.json"
    json_path.write_text(json.dumps(report, indent=2))
    print(f"\nJSON → {json_path}")

    # ══════════════════════════════════════════════════════════════════════════
    # SAVE MARKDOWN REPORT
    # ══════════════════════════════════════════════════════════════════════════
    lines = []
    lines.append("# Fall Expert — Threshold Analysis Report\n")
    lines.append(f"**Model checkpoint**: `best_model.pt` (epoch 23, val app_score=0.7902)  \n")
    lines.append(f"**Test set**: {len(y_true):,} windows (near_fall excluded)  \n")
    lines.append(f"**Date**: 2026-05-14  \n\n")

    lines.append("---\n\n## 1. Threshold Sweep\n\n")
    lines.append("| Threshold | fall_recall | fall_precision | normal_recall | macro_f1 | FP | FN | app_score |\n")
    lines.append("|-----------|-------------|----------------|---------------|----------|----|----|-----------|\n")
    for r in sweep_rows:
        marker = " ◄" if r["threshold"] == best[0] else ""
        lines.append(
            f"| {r['threshold']:.2f} "
            f"| {r['fall_recall']:.5f} "
            f"| {r['fall_precision']:.5f} "
            f"| {r['normal_recall']:.5f} "
            f"| {r['macro_f1']:.5f} "
            f"| {r['fp']:,} "
            f"| {r['fn']:,} "
            f"| {r['app_score']:.5f}{marker} |\n"
        )

    lines.append("\n---\n\n## 2. Dataset-Source Breakdown (threshold=0.40)\n\n")
    lines.append("| Dataset | n_total | n_fall | n_normal | fall_recall | fall_precision | normal_recall | macro_f1 | FN | FP |\n")
    lines.append("|---------|---------|--------|----------|-------------|----------------|---------------|----------|----|----|\n")
    for src in sorted(breakdown.keys()):
        v  = breakdown[src]
        m  = v["t40"]
        lines.append(
            f"| {src} "
            f"| {v['n_total']:,} "
            f"| {v['n_fall']:,} "
            f"| {v['n_normal']:,} "
            f"| {m['fall_recall']:.4f} "
            f"| {m['fall_precision']:.4f} "
            f"| {m['normal_recall']:.4f} "
            f"| {m['macro_f1']:.4f} "
            f"| {m['fn']:,} "
            f"| {m['fp']:,} |\n"
        )

    lines.append("\n### Confusion Matrices per Dataset (threshold=0.40)\n\n")
    for src in sorted(breakdown.keys()):
        v = breakdown[src]
        m = v["t40"]
        lines.append(f"**{src}** (n={v['n_total']:,})\n\n")
        lines.append("```\n")
        lines.append(f"              Pred Normal   Pred Fall\n")
        lines.append(f"Act Normal    {m['tn']:>10,}  {m['fp']:>9,}\n")
        lines.append(f"Act Fall      {m['fn']:>10,}  {m['tp']:>9,}\n")
        lines.append("```\n\n")

    lines.append("\n---\n\n## 3. Error Analysis (threshold=0.40)\n\n")
    err = report["error_analysis"]
    lines.append(f"**Total FN (missed falls)**: {err['total_fn']:,}  \n")
    lines.append(f"**Total FP (false alarms)**: {err['total_fp']:,}  \n\n")

    lines.append("### False Negatives by Source (falls the model missed)\n\n")
    lines.append("| Dataset | FN | Total Falls | Miss Rate |\n")
    lines.append("|---------|----|-----------|-----------|\n")
    for src, v in sorted(err["fn_by_source"].items(), key=lambda x: -x[1]["fn"]):
        lines.append(f"| {src} | {v['fn']:,} | {v['total_falls']:,} | {v['fn_rate']:.3f} |\n")

    lines.append("\n### False Positives by Source (normals misclassified as fall)\n\n")
    lines.append("| Dataset | FP | Total Normals | FP Rate |\n")
    lines.append("|---------|----|-----------|---------|\n")
    for src, v in sorted(err["fp_by_source"].items(), key=lambda x: -x[1]["fp"]):
        lines.append(f"| {src} | {v['fp']:,} | {v['total_normals']:,} | {v['fp_rate']:.3f} |\n")

    lines.append("\n### FN Probability Distribution\n\n")
    lines.append("*(These are falls where model assigned low probability — hardest misses)*\n\n")
    lines.append("| Prob Range | Count |\n|------------|-------|\n")
    for k, v in err["fn_prob_buckets"].items():
        lines.append(f"| {k} | {v:,} |\n")

    lines.append("\n### FP Probability Distribution\n\n")
    lines.append("*(These are normals where model assigned fall probability above threshold)*\n\n")
    lines.append("| Prob Range | Count |\n|------------|-------|\n")
    for k, v in err["fp_prob_buckets"].items():
        lines.append(f"| {k} | {v:,} |\n")

    lines.append("\n---\n\n## 4. Recommendation\n\n")
    rec = report["recommendation"]
    lines.append(f"**Recommended threshold**: `{rec['threshold']:.2f}`  \n")
    lines.append(f"- app_score: `{rec['app_score']:.5f}`  \n")
    lines.append(f"- fall_recall: `{rec['fall_recall']:.5f}`  \n")
    lines.append(f"- macro_f1: `{rec['macro_f1']:.5f}`  \n\n")

    # Write the recommendation narrative after analysis
    lines.append("*Threshold selection criteria: maximise app_score subject to fall_recall ≥ 0.70*  \n")

    md_path = model_dir / "threshold_analysis_report.md"
    md_path.write_text("".join(lines), encoding="utf-8")
    print(f"Markdown → {md_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
