"""Inference demo for HealthAlert prototype model.

Usage:
    python scripts/infer_prototype.py
    python scripts/infer_prototype.py --model outputs/prototype_model/best_model.pt
    python scripts/infer_prototype.py --scenario fall
    python scripts/infer_prototype.py --npz outputs/windowed_dataset/fall_detection/test.npz --n 5

Scenarios (synthetic):
    normal           — normal daily activity
    walking          — walking, low risk
    fall             — simulated fall event
    near_fall        — stumble / balance recovery
    gait_instability — irregular gait (elderly pattern)
    poor_ppg         — motion artifact degrading PPG
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.inference.prototype_predictor import PrototypePredictor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("healthalert.infer_prototype")


# ── Synthetic window generators ───────────────────────────────────────────

def _gen_normal(rng: np.random.Generator) -> tuple:
    """Normal standing/resting activity."""
    imu = rng.normal(0.0, 0.05, (200, 6)).astype(np.float32)
    imu[:, 2] += 9.81  # gravity on Z axis
    ppg = (np.sin(np.linspace(0, 4 * np.pi, 200)) * 300 + 1000).reshape(200, 1).astype(np.float32)
    ppg += rng.normal(0, 20, (200, 1)).astype(np.float32)
    vitals = {"hr_bpm": 68.0, "spo2_pct": 98.0}
    return imu, ppg, vitals


def _gen_walking(rng: np.random.Generator) -> tuple:
    """Walking with periodic gait."""
    t = np.linspace(0, 4 * np.pi, 200)
    imu = rng.normal(0.0, 0.3, (200, 6)).astype(np.float32)
    imu[:, 0] += (np.sin(2 * t) * 0.8).astype(np.float32)
    imu[:, 2] += (9.81 + np.sin(t) * 0.5).astype(np.float32)
    ppg = (np.sin(np.linspace(0, 8 * np.pi, 200)) * 200 + 900).reshape(200, 1).astype(np.float32)
    ppg += rng.normal(0, 40, (200, 1)).astype(np.float32)
    vitals = {"hr_bpm": 88.0, "spo2_pct": 97.5}
    return imu, ppg, vitals


def _gen_fall(rng: np.random.Generator) -> tuple:
    """Simulated fall: impact spike + sudden stillness."""
    imu = rng.normal(0.0, 0.2, (200, 6)).astype(np.float32)
    imu[:, 2] += 9.81
    # Impact spike at sample 100
    spike_start = 90
    imu[spike_start: spike_start + 10, 0] += rng.uniform(8.0, 15.0, 10).astype(np.float32)
    imu[spike_start: spike_start + 10, 2] += rng.uniform(-10.0, -5.0, 10).astype(np.float32)
    # Post-impact floor stillness (very low variance)
    imu[spike_start + 10:, :] = rng.normal(0.0, 0.01, (200 - spike_start - 10, 6)).astype(np.float32)
    ppg = np.zeros((200, 1), dtype=np.float32)  # PPG absent (no contact)
    vitals = {"hr_bpm": 95.0, "spo2_pct": 97.0}
    return imu, ppg, vitals


def _gen_near_fall(rng: np.random.Generator) -> tuple:
    """Near-fall: irregular jerk + recovery."""
    imu = rng.normal(0.0, 0.15, (200, 6)).astype(np.float32)
    imu[:, 2] += 9.81
    # Recovery jerk at sample 70
    imu[60:80, 0] += rng.uniform(3.0, 6.0, 20).astype(np.float32)
    imu[60:80, 1] += rng.uniform(-4.0, 4.0, 20).astype(np.float32)
    ppg = (np.sin(np.linspace(0, 4 * np.pi, 200)) * 250 + 950).reshape(200, 1).astype(np.float32)
    ppg += rng.normal(0, 60, (200, 1)).astype(np.float32)
    vitals = {"hr_bpm": 105.0, "spo2_pct": 96.5}
    return imu, ppg, vitals


def _gen_gait_instability(rng: np.random.Generator) -> tuple:
    """Irregular gait pattern (shuffling, asymmetric)."""
    t = np.linspace(0, 4 * np.pi, 200)
    imu = rng.normal(0.0, 0.4, (200, 6)).astype(np.float32)
    imu[:, 0] += (np.sin(1.3 * t + rng.uniform(0, np.pi)) * 0.6).astype(np.float32)
    imu[:, 2] += 9.81 + rng.normal(0, 0.3, 200).astype(np.float32)
    ppg = (np.sin(np.linspace(0, 6 * np.pi, 200)) * 150 + 850).reshape(200, 1).astype(np.float32)
    ppg += rng.normal(0, 80, (200, 1)).astype(np.float32)
    vitals = {"hr_bpm": 78.0, "spo2_pct": 96.0}
    return imu, ppg, vitals


def _gen_poor_ppg(rng: np.random.Generator) -> tuple:
    """Motion artifact — PPG heavily corrupted."""
    imu = rng.normal(0.0, 1.5, (200, 6)).astype(np.float32)
    imu[:, 2] += 9.81
    # Noise-dominated PPG (poor contact)
    ppg = rng.normal(500, 300, (200, 1)).astype(np.float32)
    vitals = {"hr_bpm": 72.0, "spo2_pct": 97.0}
    return imu, ppg, vitals


_SCENARIO_GEN = {
    "normal":           _gen_normal,
    "walking":          _gen_walking,
    "fall":             _gen_fall,
    "near_fall":        _gen_near_fall,
    "gait_instability": _gen_gait_instability,
    "poor_ppg":         _gen_poor_ppg,
}


# ── Pretty printer ────────────────────────────────────────────────────────

def _risk_emoji(level: str) -> str:
    return {"normal": "✓", "caution": "⚠", "high_risk": "🔶", "critical": "🔴"}.get(level, "?")


def print_result(scenario: str, result: dict) -> None:
    risk = result["risk_level"]
    emoji = _risk_emoji(risk)
    print(f"\n{'='*60}")
    print(f"  Scenario: {scenario.upper()}")
    print(f"  Risk Level : {emoji} {risk.upper()}")
    print(f"  ml_risk_score: {result['ml_risk_score']:.1f} / 100")
    print(f"  Fall detected: {result['fall_detected']} "
          f"(P(fall)={result['fall_probability']:.4f})")
    print(f"  Inference: {result['inference_ms']:.2f} ms")
    print(f"  Modalities: IMU={result['modality_flags']['has_imu']}, "
          f"PPG={result['modality_flags']['has_ppg']}")
    if result["vitals_warning"]:
        print("  ⚠ VITALS WARNING: HR or SpO2 abnormal")
    if result["ppg_unreliable"]:
        print("  ⚠ PPG UNRELIABLE: confidence degraded")
    print()
    for task, label in result["task_labels"].items():
        probs = result["task_probs"][task]
        conf = result["confidence"][task]
        print(f"  [{task}] → {label}  (conf={conf:.3f})")
    print(f"{'='*60}")


# ── Main ──────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="HealthAlert Prototype Inference Demo")
    p.add_argument(
        "--model",
        type=str,
        default=str(PROJECT_ROOT / "outputs" / "prototype_model" / "best_model.pt"),
    )
    p.add_argument(
        "--scenario",
        type=str,
        default="all",
        choices=["all"] + list(_SCENARIO_GEN.keys()),
        help="Synthetic scenario to run",
    )
    p.add_argument(
        "--npz",
        type=str,
        default=None,
        help="Optional: path to .npz file for real data inference demo",
    )
    p.add_argument("--n", type=int, default=5, help="Number of samples from npz")
    p.add_argument("--fall_threshold", type=float, default=0.4)
    p.add_argument("--device", type=str, default="auto")
    p.add_argument("--output_json", type=str, default=None, help="Save results to JSON")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        logger.error(
            f"Model not found: {model_path}\n"
            "Run: python scripts/train_prototype.py  first."
        )
        sys.exit(1)

    predictor = PrototypePredictor(
        model_path=model_path,
        device=args.device,
        fall_threshold=args.fall_threshold,
    )
    logger.info(f"Model parameters: {predictor.model_parameters():,}")

    rng = np.random.default_rng(42)
    all_results = []

    # ── Real NPZ inference demo ────────────────────────────────────────────
    if args.npz:
        npz_path = Path(args.npz)
        if not npz_path.exists():
            logger.error(f"NPZ not found: {npz_path}")
            sys.exit(1)
        data = np.load(npz_path, allow_pickle=True)
        imu_batch = data["imu"][:args.n].astype(np.float32)
        ppg_batch = data["ppg"][:args.n].astype(np.float32)
        meta = data["metadata"][:args.n] if "metadata" in data.files else [{}] * args.n
        labels = data["labels"][:args.n] if "labels" in data.files else [None] * args.n

        print(f"\nRunning inference on {args.n} real windows from {npz_path.name}")
        for i in range(args.n):
            result = predictor.predict(imu=imu_batch[i], ppg=ppg_batch[i])
            true_label = labels[i]
            scenario_id = f"real_{i}_label={true_label}"
            print_result(scenario_id, result)
            all_results.append({"scenario": scenario_id, **result})
        return

    # ── Synthetic scenario demo ────────────────────────────────────────────
    scenarios_to_run = list(_SCENARIO_GEN.keys()) if args.scenario == "all" else [args.scenario]

    print(f"\nHealthAlert Prototype Inference Demo")
    print(f"  Model: {model_path}")
    print(f"  Fall threshold: {args.fall_threshold}")
    print(f"  Scenarios: {scenarios_to_run}\n")

    for scenario in scenarios_to_run:
        gen_fn = _SCENARIO_GEN[scenario]
        imu, ppg, vitals = gen_fn(rng)
        result = predictor.predict(imu=imu, ppg=ppg, vitals=vitals)
        print_result(scenario, result)
        all_results.append({"scenario": scenario, **result})

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(all_results, f, indent=2, default=str)
        logger.info(f"Results saved: {out_path}")


if __name__ == "__main__":
    main()
