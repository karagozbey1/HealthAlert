from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_windowing_50hz_4sec_equals_200_samples():
    from src.data.windowing import segment_timeseries_to_windows

    data = np.random.randn(400, 6).astype(np.float32)
    windows = segment_timeseries_to_windows(data, sampling_rate_hz=50, window_sec=4, stride_sec=2)
    assert windows
    assert windows[0]["sample_count"] == 200


def test_windowing_25hz_normalizes_to_200_samples():
    from src.data.windowing import normalize_window_shape, segment_timeseries_to_windows

    data = np.random.randn(200, 6).astype(np.float32)
    windows = segment_timeseries_to_windows(data, sampling_rate_hz=25, window_sec=4, stride_sec=2)
    assert windows[0]["sample_count"] == 100
    normalized = normalize_window_shape(windows[0], target_rate_hz=50, target_sample_count=200)
    assert normalized["samples"].shape == (200, 6)


def test_windowing_1hz_marks_slow_model_only():
    from src.data.windowing import compute_window_quality, normalize_window_shape, segment_timeseries_to_windows

    data = np.random.randn(8, 1).astype(np.float32)
    windows = segment_timeseries_to_windows(data, sampling_rate_hz=1, window_sec=4, stride_sec=2)
    assert windows[0]["fast_model_candidate"] is False
    normalized = normalize_window_shape(windows[0])
    quality = compute_window_quality(normalized)
    assert normalized["training_candidate"] is False
    assert "slow_model_only" in quality["quality_flags"]


def test_training_metadata_file_created(tmp_path: Path):
    from scripts.train_window_model import train_window_model

    dataset_dir = tmp_path / "windowed_dataset"
    dataset_dir.mkdir(parents=True)
    features = np.random.randn(12, 23).astype(np.float32)
    labels = np.asarray([0, 1, 0, 1, 2, 0, 1, 0, 2, 0, 1, 0], dtype=np.int64)
    empty_imu = np.zeros((12, 200, 6), dtype=np.float32)
    empty_ppg = np.zeros((12, 200, 1), dtype=np.float32)
    metadata = np.asarray([json.dumps({"window_id": f"w{i}"}) for i in range(12)], dtype=object)
    for split in ("train", "val", "test"):
        np.savez_compressed(dataset_dir / f"{split}.npz", features=features, labels=labels, imu=empty_imu, ppg=empty_ppg, metadata=metadata)

    output_dir = tmp_path / "models"
    result = train_window_model(dataset_dir=str(dataset_dir), output_dir=str(output_dir), smoke=True)
    assert (output_dir / "model_metadata.json").exists()
    assert (output_dir / "healthalert_window_model.pt").exists()
    assert result["window_sec"] == 4