from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.healthalert.fusion.risk_fusion_engine import RiskFusionEngine
from src.healthalert.inference.hybrid_inference_service import HybridInferenceService


OUT_DIR = ROOT / "outputs" / "hybrid_redesign" / "final_runtime"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FIELDS = [
    "fall_probability",
    "activity_context",
    "ppg_quality_label",
    "gait_abnormal_probability",
    "gait_contribution",
    "vitals_contribution",
    "personalization_adjustment",
    "final_risk_score",
    "risk_level",
    "reasons",
    "recommended_action",
    "disabled_models",
]


def _load_npz_sample(npz_path: Path, idx: int = 0):
    if not npz_path.exists():
        return None, None
    z = np.load(npz_path, allow_pickle=True)
    imu = z["imu"][idx] if "imu" in z else None
    ppg = z["ppg"][idx] if "ppg" in z else None
    return imu, ppg


def _synthetic_imu(seed: int = 0) -> np.ndarray:
    rng = np.random.RandomState(seed)
    return rng.normal(0, 1, (6, 200)).astype(np.float32)


def _synthetic_ppg() -> np.ndarray:
    t = np.linspace(0, 4, 200)
    return np.sin(2 * np.pi * 1.2 * t).astype(np.float32)


def _make_vitals(ppg: np.ndarray | None) -> dict:
    if ppg is None:
        return {"hr": 78.0, "spo2": 97.0}
    signal = np.asarray(ppg).squeeze()
    hr = 72.0 + float(np.std(signal) * 5.0)
    spo2 = 97.0 - float(min(3.0, np.std(np.diff(signal))))
    return {"hr": hr, "spo2": spo2}


def _project_output(output: dict) -> dict:
    return {field: output.get(field) for field in OUTPUT_FIELDS}


def _controlled_fusion_output(
    *,
    fusion: RiskFusionEngine,
    disabled_models: list[str],
    fall_probability: float,
    activity_context: str,
    gait_score: float,
    ppg_quality_label: str = "missing",
) -> dict:
    ppg_score = None if ppg_quality_label == "missing" else 0.95
    fused = fusion.fuse(
        fall_probability=fall_probability,
        activity_context=activity_context,
        ppg_quality_score=ppg_score,
        ppg_quality_label=ppg_quality_label,
        runtime_vitals_adjustment=0.0,
        runtime_gait_motion_score=gait_score,
        personalization_adjustment=0.0,
        signal_confidence=0.8 if ppg_quality_label == "missing" else 1.0,
        missing_modality_flags={
            "ppg_missing": ppg_quality_label == "missing",
            "baseline_missing": True,
        },
    )
    fused["ppg_quality_label"] = ppg_quality_label
    fused["gait_abnormal_probability"] = round(float(gait_score), 4)
    fused["disabled_models"] = disabled_models
    return _project_output(fused)


def main() -> None:
    svc = HybridInferenceService(
        config_path=str(ROOT / "config" / "hybrid_runtime_config.yaml"),
        device="cpu",
        enable_temporal_smoothing=False,
    )

    gait_test = ROOT / "outputs" / "windowed_dataset" / "gait_instability_v2_ft0.30" / "test.npz"
    ppg_test = ROOT / "outputs" / "windowed_dataset" / "ppg_quality" / "test.npz"

    imu_g, _ = _load_npz_sample(gait_test, idx=0)
    _, ppg_q = _load_npz_sample(ppg_test, idx=0)
    imu_g = _synthetic_imu() if imu_g is None else imu_g
    ppg_q = _synthetic_ppg() if ppg_q is None else ppg_q

    demos = {}
    demos["imu_only"] = _project_output(
        svc.infer(
            imu_window=imu_g,
            ppg_window=None,
            vitals_values=None,
            user_id="final_demo_imu_only",
        )
    )
    demos["imu_plus_ppg"] = _project_output(
        svc.infer(
            imu_window=imu_g,
            ppg_window=ppg_q,
            vitals_values=_make_vitals(ppg_q),
            user_id="final_demo_imu_plus_ppg",
        )
    )
    demos["ppg_missing"] = _project_output(
        svc.infer(
            imu_window=imu_g,
            ppg_window=None,
            vitals_values={"hr": 92.0, "spo2": 96.0},
            user_id="final_demo_ppg_missing",
        )
    )
    demos["baseline_missing"] = _project_output(
        svc.infer(
            imu_window=imu_g,
            ppg_window=ppg_q,
            vitals_values={"hr": 105.0, "spo2": 93.0},
            user_id="final_demo_baseline_missing",
        )
    )

    disabled_models = svc._disabled_models()
    fusion = RiskFusionEngine(
        fall_threshold_caution=float(svc.config["fall_expert"]["threshold_caution"]),
        fall_threshold_balanced=float(svc.config["fall_expert"]["threshold_balanced"]),
        gait_max_contribution_points=float(
            svc.config["gait_instability_model"].get("max_contribution_points", 5)
        ),
    )
    demos["gait_auxiliary_high_fall_low"] = _controlled_fusion_output(
        fusion=fusion,
        disabled_models=disabled_models,
        fall_probability=0.10,
        activity_context="walking",
        gait_score=1.0,
    )
    demos["gait_auxiliary_high_fall_medium"] = _controlled_fusion_output(
        fusion=fusion,
        disabled_models=disabled_models,
        fall_probability=0.50,
        activity_context="walking",
        gait_score=1.0,
    )
    demos["activity_context_only_no_alert"] = _controlled_fusion_output(
        fusion=fusion,
        disabled_models=disabled_models,
        fall_probability=0.0,
        activity_context="lying",
        gait_score=0.0,
    )

    out_file = OUT_DIR / "final_hybrid_inference_demo_outputs.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(demos, f, indent=2)

    print(json.dumps(demos, indent=2))
    print(f"\nSaved: {out_file}")


if __name__ == "__main__":
    main()
