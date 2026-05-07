import sys
import time
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import torch

from src.utils.seed import set_seed, get_device
from src.models.multitask_model_v2 import HealthAlertModelV2
from src.inference.predictor import HealthAlertPredictor
from src.inference.risk_postprocessor_v2 import RiskPostprocessorV2
from src.inference.recommendation_engine_v2 import RecommendationEngineV2
from src.inference.explainability_v2 import ExplainableOutputV2
from src.simulation.extended_scenarios import ExtendedScenarioGenerator
from src.data.feature_engineering.feature_pipeline import extract_all_handcrafted_features


# Demo cagrisi icin model yolu ve cihaz secimini okur.
def parse_args():
    parser = argparse.ArgumentParser(description="HealthAlert Inference Demo")
    parser.add_argument("--model_path", type=str, default=None,
                        help="Path to trained model checkpoint")
    parser.add_argument("--device", type=str, default="cpu", help="Device")
    return parser.parse_args()


# Terminal ciktilarini risk seviyesine gore renklendirir.
C = {
    "normal": "\033[92m", "watch": "\033[93m",
    "warning": "\033[33m", "critical": "\033[91m",
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
}


# Demo basligini ekrana yazar.
def print_header():
    print("\n" + "=" * 70)
    print(f"{C['bold']}  🏥 HealthAlert AI — Inference Demo (6 Scenarios){C['reset']}")
    print(f"  Multimodal Early Warning & Fall Detection System")
    print("=" * 70)


# Tek senaryonun yapilandirilmis sonucunu ayrintili sekilde yazdirir.
def print_scenario_result(scenario_name: str, description: str,
                          result: dict, recommendations: list,
                          explanation: dict, elapsed_ms: float):
    level = result["final_risk_level"]
    color = C.get(level, "")
    risk_bar = "█" * int(result["early_risk_score"] * 20) + "░" * (20 - int(result["early_risk_score"] * 20))

    print(f"\n{'━' * 60}")
    print(f"  {C['bold']}Scenario: {scenario_name}{C['reset']}")
    print(f"  {C['dim']}{description}{C['reset']}")
    print(f"  {'—' * 50}")
    print(f"  📊 Risk Score:  [{risk_bar}] {result['early_risk_score']:.2f}")
    print(f"  🏷  Risk Level:  {color}{C['bold']}{level.upper()}{C['reset']}")
    print(f"  📉 Fall Prob:   {result['fall_probability']:.2%}")
    print(f"  ⚖  Instability: {result['instability_probability']:.2%}")
    print(f"  💚 PPG Quality: {result['ppg_quality_score']:.2%}")
    print(f"  🔒 Confidence:  {result['confidence']:.2%}")
    print(f"  🚨 Immediate:   {'YES' if result['immediate_alert'] else 'No'}")
    print(f"  ⚡ Latency:     {elapsed_ms:.1f}ms")

    if result["reasons"]:
        print(f"\n  {C['bold']}Reasons:{C['reset']}")
        for r in result["reasons"]:
            print(f"    • {r}")

    print(f"\n  {C['bold']}Recommendations:{C['reset']}")
    for rec in recommendations[:3]:
        print(f"    → {rec}")

    if explanation.get("contributions"):
        print(f"\n  {C['bold']}Explainability ({explanation['n_risk_factors']} risk factors):{C['reset']}")
        for contrib in explanation["contributions"][:3]:
            dir_icon = "⬆" if contrib["direction"] == "risk_increase" else "⬇"
            print(f"    {dir_icon} {contrib['explanation']} (importance: {contrib['importance']:.2f})")


# Alti temel senaryoda cikarim, aciklama ve oneri akislarini calistirir.
def main():
    args = parse_args()
    set_seed(42)
    device = get_device(args.device)

    print_header()
    print(f"  Device: {device}")

    # Checkpoint varsa onu yukler, yoksa demo modeliyle devam eder.
    if args.model_path and Path(args.model_path).exists():
        predictor = HealthAlertPredictor.from_checkpoint(args.model_path, str(device))
        print("  Model: Trained model loaded ✓")
    else:
        model = HealthAlertModelV2()
        model.to(device)
        predictor = HealthAlertPredictor(model, device)
        print("  Model: Demo mode (random weights)")

    postprocessor = RiskPostprocessorV2()
    recommender = RecommendationEngineV2()
    explainer = ExplainableOutputV2()

    # Alti temel senaryoyu sentetik olarak uretir.
    gen = ExtendedScenarioGenerator(sr=50, seed=42)
    scenarios = gen.generate_all()

    print(f"\n  Running {len(scenarios)} scenarios...\n")

    for scenario in scenarios:
        predictor.reset()
        name = scenario["name"]
        data = scenario["data"]
        description = scenario["description"]

        # Son pencereyi model girdisi olarak kullanir.
        window_size = 200
        n = len(data["timestamp"])
        start = max(0, n - window_size)

        imu = np.column_stack([
            data["accel_x"][start:start+window_size],
            data["accel_y"][start:start+window_size],
            data["accel_z"][start:start+window_size],
            data["gyro_x"][start:start+window_size],
            data["gyro_y"][start:start+window_size],
            data["gyro_z"][start:start+window_size],
        ]).astype(np.float32)

        ppg = data["heart_rate"][start:start+window_size].reshape(-1, 1).astype(np.float32)

        hr_mean = float(np.nanmean(data["heart_rate"][start:start+window_size]))
        spo2_mean = float(np.nanmean(data["spo2"][start:start+window_size]))
        vitals = np.array([hr_mean, spo2_mean / 100.0, 0.8], dtype=np.float32)

        # Pencere kisa kalirsa sifir dolguyla sabit boyuta tamamlar.
        if imu.shape[0] < window_size:
            pad = np.zeros((window_size - imu.shape[0], 6), dtype=np.float32)
            imu = np.vstack([imu, pad])
            pad_ppg = np.zeros((window_size - ppg.shape[0], 1), dtype=np.float32)
            ppg = np.vstack([ppg, pad_ppg])

        t0 = time.time()

        predictions = predictor.predict(imu, ppg, vitals, smooth=False)

    # Aciklanabilirlik katmani icin el yapimi ozellikleri cikarir.
        hc_vec, hc_names = extract_all_handcrafted_features(
            accel=imu[:, :3], gyro=imu[:, 3:6],
            hr_signal=ppg.flatten(),
            spo2_signal=np.full(window_size, spo2_mean),
            ppg_quality=0.8, sr=50,
        )
        hc_dict = dict(zip(hc_names, hc_vec.tolist()))

        vitals_dict = {"heart_rate": hr_mean, "spo2": spo2_mean}
        result = postprocessor.process(predictions, vitals_dict)

        recommendations = recommender.get_recommendations(result)

        explanation = explainer.explain(predictions, vitals_dict, hc_dict)

        elapsed_ms = (time.time() - t0) * 1000

        print_scenario_result(name, description, result, recommendations,
                             explanation, elapsed_ms)

    print(f"\n{'=' * 70}")
    print(f"  Demo complete. All {len(scenarios)} scenarios processed.")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
