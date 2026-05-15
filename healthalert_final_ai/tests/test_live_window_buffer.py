from src.healthalert.inference.live_window_buffer import LiveWindowBuffer


def _sample(i: int, with_ppg: bool = True):
    sample = {
        "patient_id": "p1",
        "timestamp": f"2026-05-15T12:00:{i:02d}Z",
        "source": "esp32",
        "imu": {
            "acc_x": 0.1,
            "acc_y": 0.2,
            "acc_z": 0.3,
            "gyro_x": 0.4,
            "gyro_y": 0.5,
            "gyro_z": 0.6,
        },
        "heart_rate": 80,
        "spo2": 97,
    }
    if with_ppg:
        sample["ppg"] = {"ir": 1000 + i, "red": 900 + i}
    return sample


def test_window_forms_after_200_imu_samples():
    buf = LiveWindowBuffer()
    out = None
    for i in range(200):
        out = buf.add_sample("p1", _sample(i))
    assert out is not None
    assert out["window_ready"] is True
    assert out["window"].imu_window.shape == (200, 6)
    assert out["window"].ppg_window.shape == (200, 1)
    assert buf.is_ready("p1") is True


def test_window_not_ready_before_200_and_inference_can_be_skipped():
    buf = LiveWindowBuffer()
    for i in range(199):
        out = buf.add_sample("p1", _sample(i))
    assert out["window_ready"] is False
    assert buf.is_ready("p1") is False
    assert buf.get_window("p1") is None


def test_ppg_missing_does_not_crash_and_returns_none_window():
    buf = LiveWindowBuffer()
    out = None
    for i in range(200):
        out = buf.add_sample("p1", _sample(i, with_ppg=False))
    assert out["window_ready"] is True
    assert out["window"].ppg_window is None


def test_missing_imu_sample_is_skipped_without_crash():
    buf = LiveWindowBuffer()
    sample = _sample(1)
    sample["imu"] = None
    out = buf.add_sample("p1", sample)
    assert out["accepted_sample"] is False
    assert out["window_ready"] is False
    assert out["buffered_imu_samples"] == 0


def test_reset_or_slide_retains_50_percent_overlap():
    buf = LiveWindowBuffer()
    for i in range(200):
        buf.add_sample("p1", _sample(i))
    info = buf.reset_or_slide("p1")
    assert info["strategy"] == "50_percent_overlap"
    assert info["retained_samples"] == 100
    assert buf.is_ready("p1") is False
