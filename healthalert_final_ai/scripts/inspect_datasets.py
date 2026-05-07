import sys
from pathlib import Path
from collections import Counter

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.io import load_all_configs
from src.utils.logger import setup_logger
from src.utils.validators import validate_config_paths
from src.data.column_schema import STANDARD_COLUMNS


# Veri seti yukleyicilerini ve temel model seklini hizli kontrol eder.
def main():
    logger = setup_logger("healthalert", level="INFO")
    cfg = load_all_configs(str(PROJECT_ROOT / "config"))

    print("\n" + "=" * 60)
    print("  HealthAlert — Dataset Inspection (Stage 1)")
    print("=" * 60)

    # Yapilandirmadaki veri yollarini once dogrular.
    warnings = validate_config_paths(cfg)
    if warnings:
        print("\n[!] Path warnings:")
        for w in warnings:
            print(f"   {w}")
    else:
        print("\n[OK] All data paths validated")

    print("\n" + "-" * 40)
    print("[HIFD Dataset]")
    print("-" * 40)
    try:
        from src.data.loaders.hifd_loader import load_all_subjects
        records = load_all_subjects(cfg.paths.hifd_dir, max_subjects=5)
        _print_dataset_summary(records, "HIFD")
    except Exception as e:
        print(f"  [ERROR] {e}")

    print("\n" + "-" * 40)
    print("[WEDA_FALL Dataset]")
    print("-" * 40)
    try:
        from src.data.loaders.weda_fall_loader import load_all_trials
        records = load_all_trials(cfg.paths.weda_fall_dir, max_trials=20)
        _print_dataset_summary(records, "WEDA_FALL")
    except Exception as e:
        print(f"  [ERROR] {e}")

    print("\n" + "-" * 40)
    print("[BUT_PPG Dataset]")
    print("-" * 40)
    try:
        from src.data.loaders.but_ppg_loader import load_all_records
        records = load_all_records(cfg.paths.but_ppg_dir, max_records=50)
        _print_butppg_summary(records)
    except Exception as e:
        print(f"  [ERROR] {e}")

    print("\n" + "-" * 40)
    print("[Model Info]")
    print("-" * 40)
    try:
        from src.models.multitask_model_v2 import HealthAlertModelV2
        import torch
        model = HealthAlertModelV2(cfg)
        print(f"  Total parameters: {model.count_parameters():,}")
        print(f"  IMU Encoder output: {model.imu_encoder.output_dim}")
        print(f"  PPG Encoder output: {model.ppg_encoder.output_dim}")
        print(f"  Vitals MLP output: {model.vitals_mlp.output_dim}")
        print(f"  Handcrafted MLP output: {model.handcrafted_mlp.output_dim}")
        print(f"  Fusion embed_dim: {model.fusion.embed_dim}")

        # Ornek ileri gecisle tensor boyutlarini kontrol eder.
        batch = {
            "imu": torch.randn(2, 200, 6),
            "ppg": torch.randn(2, 200, 1),
            "vitals": torch.randn(2, 3),
            "handcrafted_features": torch.randn(2, 38),
        }
        with torch.no_grad():
            out = model(batch)
        print(f"  Forward pass: OK")
        for k, v in out.items():
            if isinstance(v, torch.Tensor):
                print(f"    {k}: {list(v.shape)}")
    except Exception as e:
        print(f"  [ERROR] {e}")

    print("\n" + "-" * 40)
    print("[Standard Column Schema]")
    print("-" * 40)
    for col in STANDARD_COLUMNS:
        print(f"  {col}")

    print("\n" + "=" * 60)
    print("  Inspection complete!")
    print("=" * 60 + "\n")


# Genel veri setlerinde kayit, etiket ve ornek sekillerini ozetler.
def _print_dataset_summary(records, name):
    print(f"  Loaded records: {len(records)}")
    if not records:
        return

    labels = [r.get("label", -1) for r in records]
    dist = Counter(labels)
    label_names = {0: "ADL", 1: "Fall", 2: "Near-fall", -1: "Unknown"}
    print(f"  Label distribution:")
    for lbl, count in sorted(dist.items()):
        print(f"    {label_names.get(lbl, f'Label {lbl}')}: {count}")

    subjects = set(r.get("subject_id", "") for r in records)
    print(f"  Unique subjects: {len(subjects)}")

    if "data" in records[0] and hasattr(records[0]["data"], "shape"):
        sample = records[0]["data"]
        print(f"  Sample shape: {sample.shape}")
        if hasattr(sample, "columns"):
            print(f"  Columns: {list(sample.columns)[:10]}...")


# BUT_PPG kayitlari icin kalite ve vital araliklarini ozetler.
def _print_butppg_summary(records):
    print(f"  Loaded records: {len(records)}")
    if not records:
        return

    q_good = sum(1 for r in records if r.get("quality_label") == 1)
    q_bad = sum(1 for r in records if r.get("quality_label") == 0)
    print(f"  Quality good: {q_good}, Quality poor: {q_bad}")

    hrs = [r.get("heart_rate", 0) for r in records]
    print(f"  HR range: {min(hrs):.0f} - {max(hrs):.0f} bpm")

    import math
    spo2s = [r.get("spo2", 0) for r in records if not math.isnan(r.get("spo2", float("nan")))]
    if spo2s:
        print(f"  SpO2 range: {min(spo2s):.0f} - {max(spo2s):.0f}%")

    subjects = set(r.get("subject_id", "") for r in records)
    print(f"  Unique subjects: {len(subjects)}")


if __name__ == "__main__":
    main()
