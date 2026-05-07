import sys
import os
from pathlib import Path

# Konsol UTF-8 degilse Turkce ciktiyi bozmamak icin yeniden ayarlar.
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.io import load_all_configs
from src.utils.logger import setup_logger
from src.utils.validators import validate_config_paths


# Uc veri kaynagini ve modeli hizli ozetlerle denetler.
def main():
    logger = setup_logger("healthalert", level="INFO")
    cfg = load_all_configs(str(PROJECT_ROOT / "config"))

    print("\n" + "=" * 60)
    print("  HealthAlert - Veri Kesif & Dogrulama")
    print("=" * 60)

    # Veri yollarini once denetleyip uyari varsa yazdirir.
    warnings = validate_config_paths(cfg)
    if warnings:
        print("\n[!] Path uyarilari:")
        for w in warnings:
            print(f"   {w}")
    else:
        print("\n[OK] Tum veri yollari dogrulandi")

    print("\n" + "-" * 40)
    print("[HIFD Dataset]")
    print("-" * 40)
    try:
        from src.data.loaders.hifd_loader import load_all_subjects
        records = load_all_subjects(cfg.paths.hifd_dir, max_subjects=5)
        print(f"  Yuklenen kayit: {len(records)}")
        if records:
            labels = [r['label'] for r in records]
            print(f"  Fall: {labels.count(1)}, ADL: {labels.count(0)}, Near-fall: {labels.count(2)}")
            subjects = set(r['subject_id'] for r in records)
            print(f"  Denekler: {len(subjects)}")
            sample = records[0]['data']
            print(f"  Ornek boyut: {sample.shape}")
            print(f"  Sutunlar: {list(sample.columns)}")
    except Exception as e:
        print(f"  [HATA] {e}")

    print("\n" + "-" * 40)
    print("[WEDA_FALL Dataset]")
    print("-" * 40)
    try:
        from src.data.loaders.weda_fall_loader import load_all_trials
        records = load_all_trials(cfg.paths.weda_fall_dir, max_trials=20)
        print(f"  Yuklenen kayit: {len(records)}")
        if records:
            labels = [r['label'] for r in records]
            print(f"  Fall: {labels.count(1)}, ADL: {labels.count(0)}")
            subjects = set(r['subject_id'] for r in records)
            print(f"  Denekler: {len(subjects)}")
            sample = records[0]['data']
            print(f"  Ornek boyut: {sample.shape}")
            print(f"  Sutunlar: {list(sample.columns)}")
            ts = [r for r in records if r.get('fall_start') is not None]
            print(f"  Dusme zaman damgali: {len(ts)}")
    except Exception as e:
        print(f"  [HATA] {e}")

    print("\n" + "-" * 40)
    print("[BUT_PPG Dataset]")
    print("-" * 40)
    try:
        from src.data.loaders.but_ppg_loader import load_all_records
        records = load_all_records(cfg.paths.but_ppg_dir, max_records=50)
        print(f"  Yuklenen kayit: {len(records)}")
        if records:
            q_good = sum(1 for r in records if r['quality_label'] == 1)
            q_bad = sum(1 for r in records if r['quality_label'] == 0)
            print(f"  Kalite iyi: {q_good}, Kalite kotu: {q_bad}")
            hrs = [r['heart_rate'] for r in records]
            print(f"  HR araligi: {min(hrs):.0f} - {max(hrs):.0f} bpm")
            import math
            spo2s = [r['spo2'] for r in records if not math.isnan(r['spo2'])]
            if spo2s:
                print(f"  SpO2 araligi: {min(spo2s):.0f} - {max(spo2s):.0f}%")
    except Exception as e:
        print(f"  [HATA] {e}")

    print("\n" + "-" * 40)
    print("[Model Bilgisi]")
    print("-" * 40)
    try:
        from src.models.multitask_model import HealthAlertModel
        model = HealthAlertModel(cfg)
        print(f"  Toplam parametre: {model.count_parameters():,}")
        print(f"  IMU Encoder cikis: {model.imu_encoder.output_dim}")
        print(f"  PPG Encoder cikis: {model.ppg_encoder.output_dim}")
        print(f"  Vitals MLP cikis: {model.vitals_mlp.output_dim}")
        print(f"  Fusion cikis (embed_dim): {model.fusion.embed_dim}")

        # Rasgele batch ile ileri gecisin ayakta oldugunu dogrular.
        import torch
        batch = {
            "imu": torch.randn(2, 200, 6),
            "ppg": torch.randn(2, 200, 1),
            "vitals": torch.randn(2, 3),
        }
        with torch.no_grad():
            out = model(batch)
        print(f"  Forward pass: OK")
        for k, v in out.items():
            if isinstance(v, torch.Tensor):
                print(f"    {k}: {list(v.shape)}")
    except Exception as e:
        print(f"  [HATA] {e}")

    print("\n" + "=" * 60)
    print("  Kesif tamamlandi!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
