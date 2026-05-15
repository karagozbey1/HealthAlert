from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.healthalert.api.schemas.live_sensor_schema import LiveSensorSampleRequest
from src.healthalert.api.services.live_sensor_ingestion_service import LiveSensorIngestionService


OUT_DIR = ROOT / "outputs" / "hybrid_redesign" / "live_stream"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _load_npz_window(path: Path, idx: int = 0):
    z = np.load(path, allow_pickle=True)
    imu = z["imu"][idx] if "imu" in z else None
    ppg = z["ppg"][idx] if "ppg" in z else None
    return np.asarray(imu, dtype=np.float32), None if ppg is None else np.asarray(ppg).squeeze()


def _sample_from_window(
    *,
    patient_id: str,
    i: int,
    imu_window: np.ndarray,
    ppg_window: np.ndarray | None,
    include_ppg: bool,
    include_vitals: bool,
) -> LiveSensorSampleRequest:
    if imu_window.shape == (200, 6):
        values = imu_window[i]
    elif imu_window.shape == (6, 200):
        values = imu_window[:, i]
    else:
        raise ValueError(f"Unexpected IMU window shape: {imu_window.shape}")

    data = {
        "patient_id": patient_id,
        "timestamp": f"2026-05-15T12:30:{i:02d}Z",
        "source": "esp32",
        "imu": {
            "acc_x": float(values[0]),
            "acc_y": float(values[1]),
            "acc_z": float(values[2]),
            "gyro_x": float(values[3]),
            "gyro_y": float(values[4]),
            "gyro_z": float(values[5]),
        },
    }
    if include_ppg and ppg_window is not None:
        ppg_value = float(ppg_window[i])
        data["ppg"] = {"ir": ppg_value, "red": ppg_value * 0.95}
    if include_vitals:
        data["heart_rate"] = 82.0
        data["spo2"] = 97.0
    return LiveSensorSampleRequest(**data)


def _run_window(
    *,
    service: LiveSensorIngestionService,
    patient_id: str,
    imu_window: np.ndarray,
    ppg_window: np.ndarray | None,
    include_ppg: bool,
    include_vitals: bool,
):
    response = None
    for i in range(200):
        response = service.ingest_sample(
            _sample_from_window(
                patient_id=patient_id,
                i=i,
                imu_window=imu_window,
                ppg_window=ppg_window,
                include_ppg=include_ppg,
                include_vitals=include_vitals,
            )
        )
    if response is None or response.inference_result is None:
        raise RuntimeError(f"Live demo did not produce inference for {patient_id}")
    return response.model_dump()


def main() -> None:
    gait_test = ROOT / "outputs" / "windowed_dataset" / "gait_instability_v2_ft0.30" / "test.npz"
    ppg_test = ROOT / "outputs" / "windowed_dataset" / "ppg_quality" / "test.npz"
    imu_window, _ = _load_npz_window(gait_test, idx=0)
    _, ppg_window = _load_npz_window(ppg_test, idx=0)

    service = LiveSensorIngestionService(
        config_path=str(ROOT / "config" / "hybrid_runtime_config.yaml"),
        persistence_dir=str(OUT_DIR),
    )

    outputs = {
        "imu_only": _run_window(
            service=service,
            patient_id="live_demo_imu_only",
            imu_window=imu_window,
            ppg_window=ppg_window,
            include_ppg=False,
            include_vitals=False,
        ),
        "imu_plus_ppg": _run_window(
            service=service,
            patient_id="live_demo_imu_plus_ppg",
            imu_window=imu_window,
            ppg_window=ppg_window,
            include_ppg=True,
            include_vitals=True,
        ),
        "missing_ppg": _run_window(
            service=service,
            patient_id="live_demo_missing_ppg",
            imu_window=imu_window,
            ppg_window=None,
            include_ppg=False,
            include_vitals=True,
        ),
        "baseline_missing": _run_window(
            service=service,
            patient_id="live_demo_baseline_missing",
            imu_window=imu_window,
            ppg_window=ppg_window,
            include_ppg=True,
            include_vitals=True,
        ),
    }

    out_file = OUT_DIR / "live_stream_demo_outputs.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(outputs, f, indent=2, ensure_ascii=True)

    print(json.dumps(outputs, indent=2, ensure_ascii=True))
    print(f"\nSaved: {out_file}")
    print(f"Events: {OUT_DIR / 'live_inference_events.jsonl'}")


if __name__ == "__main__":
    main()
