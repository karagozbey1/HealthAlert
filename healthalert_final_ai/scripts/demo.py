import sys
import argparse
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import torch

from src.utils.seed import set_seed, get_device
from src.utils.logger import setup_logger
from src.models.multitask_model import HealthAlertModel
from src.inference.predictor import HealthAlertPredictor
from src.inference.risk_postprocessor import RiskPostprocessor
from src.inference.recommendation_engine import RecommendationEngine
from src.inference.explainability import ExplainableOutput
from src.simulation.synthetic_stream import SyntheticStream
from src.data.feature_engineering.imu_features import extract_imu_features


# Komut satiri argumanlarini okuyup demo senaryosunu belirler.
def parse_args():
    parser = argparse.ArgumentParser(description="HealthAlert Demo")
    parser.add_argument("--scenario", type=str, default="mixed",
                        choices=["normal", "fall", "presyncope", "mixed"])
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--model_path", type=str, default=None)
    parser.add_argument("--device", type=str, default="cpu")
    return parser.parse_args()


# Terminalde risk seviyelerini renkli gostermek icin ANSI kodlarini tutar.
COLORS = {
    "normal": "\033[92m",     # Green
    "watch": "\033[93m",      # Yellow
    "warning": "\033[33m",    # Orange
    "critical": "\033[91m",   # Red
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
}


# Risk seviyesine uygun renkle metni bicimler.
def colorize(text: str, level: str) -> str:
    return f"{COLORS.get(level, '')}{text}{COLORS['reset']}"


# Demo acilis basligini ekrana yazar.
def print_header():
    print("\n" + "=" * 70)
    print(f"{COLORS['bold']}  🏥 HealthAlert AI - Gerçek Zamanlı Demo{COLORS['reset']}")
    print(f"  Multimodal Erken Uyarı & Düşme Tespit Sistemi")
    print("=" * 70 + "\n")


# Tek pencere sonucunu risk ve onerilerle birlikte yazdirir.
def print_result(window_time: float, result: dict, recommendations: list, elapsed_ms: float):
    level = result["final_risk_level"]
    color = COLORS.get(level, "")
    risk_bar = "█" * int(result["early_risk_score"] * 20) + "░" * (20 - int(result["early_risk_score"] * 20))

    print(f"\n{'─' * 60}")
    print(f"  ⏱  Zaman: {window_time:.1f}s")
    print(f"  📊 Risk Skoru: [{risk_bar}] {result['early_risk_score']:.2f}")
    print(f"  🏷  Risk Seviyesi: {color}{COLORS['bold']}{level.upper()}{COLORS['reset']}")
    print(f"  📉 Düşme Olasılığı: {result['fall_probability']:.2%}")
    print(f"  ⚖  Denge Bozukluğu: {result['instability_probability']:.2%}")
    print(f"  💚 Sinyal Kalitesi: {result['ppg_quality_score']:.2%}")
    print(f"  🔒 Güvenilirlik: {result['confidence']:.2%}")
    print(f"  ⚡ İşlem süresi: {elapsed_ms:.1f}ms")

    if result["reasons"]:
        print(f"\n  {COLORS['bold']}Nedenler:{COLORS['reset']}")
        for reason in result["reasons"]:
            print(f"    • {reason}")

    print(f"\n  {COLORS['bold']}Öneriler:{COLORS['reset']}")
    for rec in recommendations[:3]:
        print(f"    → {rec}")


# Sentetik akis uzerinden uc uca demo calistirir.
def main():
    args = parse_args()
    set_seed(42)

    logger = setup_logger("healthalert", level="WARNING")
    device = get_device(args.device)

    print_header()
    print(f"  Senaryo: {args.scenario}")
    print(f"  Süre: {args.duration}s")
    print(f"  Cihaz: {device}")

    # Egitilmis agirlik varsa onu, yoksa demo icin rastgele modeli kullanir.
    if args.model_path and Path(args.model_path).exists():
        predictor = HealthAlertPredictor.from_checkpoint(args.model_path, str(device))
        print("  Model: Eğitilmiş model yüklendi ✓")
    else:
        model = HealthAlertModel()
        model.to(device)
        predictor = HealthAlertPredictor(model, device)
        print("  Model: Demo modu (rastgele ağırlıklar)")

    postprocessor = RiskPostprocessor()
    recommender = RecommendationEngine()
    explainer = ExplainableOutput()

    # Secilen senaryo icin sentetik pencere akisi uretir.
    stream = SyntheticStream(sr=50, noise_std=0.05)
    window_gen = stream.generate_stream(
        scenario=args.scenario,
        duration=args.duration,
        window_size=200,
        stride=100,
    )

    print(f"\n  {'─' * 50}")
    print(f"  🔴 Canlı izleme başlatılıyor...\n")
    time.sleep(1)

    for window_data in window_gen:
        t0 = time.time()

        # Ham pencereyi modelin bekledigi girdi bicimine cevirir.
        imu = np.column_stack([
            window_data["accel_x"], window_data["accel_y"], window_data["accel_z"],
            window_data["gyro_x"], window_data["gyro_y"], window_data["gyro_z"],
        ]).astype(np.float32)

        ppg = window_data["heart_rate"].reshape(-1, 1).astype(np.float32)

        hr_mean = float(np.nanmean(window_data["heart_rate"]))
        spo2_mean = float(np.nanmean(window_data["spo2"])) / 100.0
        vitals = np.array([hr_mean, spo2_mean, 0.8], dtype=np.float32)

        predictions = predictor.predict(imu, ppg, vitals, smooth=True)

        vitals_dict = {
            "heart_rate": hr_mean,
            "spo2": float(np.nanmean(window_data["spo2"])),
        }
        result = postprocessor.process(predictions, vitals_dict)

        recommendations = recommender.get_recommendations(result)

        elapsed_ms = (time.time() - t0) * 1000
        window_time = window_data.get("window_start", 0)

        print_result(window_time, result, recommendations, elapsed_ms)

    # Ciktiyi canli akis gibi gostermek icin kisa gecikme ekler.
        time.sleep(0.5)

    print(f"\n{'=' * 70}")
    print(f"  Demo tamamlandı. Toplam {args.duration}s veri işlendi.")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
