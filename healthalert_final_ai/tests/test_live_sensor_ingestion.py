import json
from pathlib import Path

from src.healthalert.api.schemas.live_sensor_schema import LiveSensorSampleRequest
from src.healthalert.api.services.live_sensor_ingestion_service import LiveSensorIngestionService


RISK_LEVELS = {"normal", "caution", "high_risk", "critical"}


def _payload(i: int, patient_id: str = "live_patient_001", with_ppg: bool = True):
    data = {
        "patient_id": patient_id,
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
    }
    if with_ppg:
        data["ppg"] = {"ir": 1200 + i, "red": 1000 + i}
        data["heart_rate"] = 82
        data["spo2"] = 97
    return LiveSensorSampleRequest(**data)


def _persistence_dir(name: str) -> Path:
    path = Path("outputs/hybrid_redesign/test_live_stream") / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_window_ready_triggers_imu_plus_ppg_inference_and_persists_event():
    out_dir = _persistence_dir("ready")
    svc = LiveSensorIngestionService(persistence_dir=str(out_dir))
    out = None
    for i in range(200):
        out = svc.ingest_sample(_payload(i, patient_id="live_ready"))
    assert out is not None
    assert out.window_ready is True
    assert out.inference_triggered is True
    assert out.inference_result is not None
    assert out.inference_result.data_mode == "live"
    assert 0 <= out.inference_result.risk.final_risk_score <= 100
    assert out.inference_result.risk.risk_level in RISK_LEVELS
    assert out.inference_result.experts.gait.contribution <= 5.0

    aggregate = out_dir / "live_inference_events.jsonl"
    assert aggregate.exists()
    event = json.loads(aggregate.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert event["patient_id"] == "live_ready"
    assert event["data_mode"] == "live"
    assert "experts" in event


def test_window_not_ready_does_not_trigger_inference():
    svc = LiveSensorIngestionService(persistence_dir=str(_persistence_dir("not_ready")))
    out = svc.ingest_sample(_payload(1, patient_id="live_not_ready"))
    assert out.window_ready is False
    assert out.inference_triggered is False
    assert out.inference_result is None


def test_imu_only_window_inference_and_ppg_missing_no_crash():
    svc = LiveSensorIngestionService(persistence_dir=str(_persistence_dir("missing_ppg")))
    out = None
    for i in range(200):
        out = svc.ingest_sample(_payload(i, patient_id="live_missing_ppg", with_ppg=False))
    assert out.window_ready is True
    assert out.inference_result is not None
    assert out.inference_result.missing_modalities.ppg_missing is True
    assert "ppg_missing" in out.inference_result.risk.reasons


def test_missing_baseline_sets_cold_start_mode():
    svc = LiveSensorIngestionService(persistence_dir=str(_persistence_dir("baseline_missing")))
    out = None
    for i in range(200):
        out = svc.ingest_sample(_payload(i, patient_id="live_baseline_missing"))
    assert out.inference_result is not None
    assert out.inference_result.personalization.cold_start_mode is True
    assert out.inference_result.missing_modalities.baseline_missing is True


def test_missing_imu_sample_does_not_crash_or_trigger_inference():
    svc = LiveSensorIngestionService(persistence_dir=str(_persistence_dir("missing_imu")))
    payload = _payload(1, patient_id="live_missing_imu")
    data = payload.model_dump()
    data["imu"] = None
    out = svc.ingest_sample(LiveSensorSampleRequest(**data))
    assert out.window_ready is False
    assert out.inference_triggered is False
    assert out.missing_modalities["imu_missing"] is True
