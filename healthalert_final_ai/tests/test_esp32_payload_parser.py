from src.healthalert.api.schemas.live_sensor_schema import (
    DEFAULT_PATIENT_ID,
    LiveSensorSampleRequest,
    normalize_live_sensor_payload,
)


def test_esp32_ax_alias_payload_normalizes_to_backend_schema():
    payload = {
        "patientId": "esp32_alias_patient",
        "source": "wifi",
        "ax": 0.11,
        "ay": 0.22,
        "az": 0.33,
        "gx": 1.1,
        "gy": 1.2,
        "gz": 1.3,
        "IR": 18400,
        "RED": 9100,
        "hr": 81,
        "SpO2": 97,
    }

    req = LiveSensorSampleRequest(**payload)

    assert req.patient_id == "esp32_alias_patient"
    assert req.source == "esp32"
    assert req.imu is not None
    assert req.imu.acc_x == 0.11
    assert req.imu.acc_y == 0.22
    assert req.imu.acc_z == 0.33
    assert req.imu.gyro_x == 1.1
    assert req.imu.gyro_y == 1.2
    assert req.imu.gyro_z == 1.3
    assert req.ppg is not None
    assert req.ppg.ir == 18400
    assert req.ppg.red == 9100
    assert req.heart_rate == 81
    assert req.spo2 == 97


def test_standard_nested_payload_is_preserved():
    req = LiveSensorSampleRequest(
        **{
            "patient_id": "standard_patient",
            "timestamp": "2026-05-15T12:00:00Z",
            "source": "esp32",
            "imu": {
                "acc_x": 0.0,
                "acc_y": 0.1,
                "acc_z": 0.2,
                "gyro_x": 0.3,
                "gyro_y": 0.4,
                "gyro_z": 0.5,
            },
            "ppg": {"ir": 2000, "red": 1000},
        }
    )

    assert req.patient_id == "standard_patient"
    assert req.timestamp == "2026-05-15T12:00:00Z"
    assert req.imu is not None
    assert req.imu.gyro_z == 0.5
    assert req.ppg is not None
    assert req.ppg.ir == 2000


def test_legacy_firmware_payload_normalizes_accel_and_ppg_fields():
    normalized = normalize_live_sensor_payload(
        {
            "device_id": "ha-esp32-01",
            "timestamp_ms": 123456,
            "accel_x": -0.1,
            "accel_y": 0.0,
            "accel_z": 1.0,
            "gyro_x": 2.0,
            "gyro_y": 3.0,
            "gyro_z": 4.0,
            "ir_value": 9000,
            "red_value": 8000,
        }
    )

    assert normalized["patient_id"] == DEFAULT_PATIENT_ID
    assert normalized["timestamp"] == "123456"
    assert normalized["imu"]["acc_x"] == -0.1
    assert normalized["imu"]["gyro_z"] == 4.0
    assert normalized["ppg"]["ir"] == 9000
    assert normalized["ppg"]["red"] == 8000


def test_ppg_missing_payload_does_not_raise():
    req = LiveSensorSampleRequest(
        **{
            "ax": 0.1,
            "ay": 0.2,
            "az": 0.3,
            "gx": 0.4,
            "gy": 0.5,
            "gz": 0.6,
            "ppg_ok": False,
        }
    )

    assert req.patient_id == DEFAULT_PATIENT_ID
    assert req.ppg is None
    assert req.imu is not None


def test_malformed_sample_without_imu_is_accepted_for_safe_runtime_default():
    req = LiveSensorSampleRequest(**{"patient_id": "malformed_but_safe"})

    assert req.patient_id == "malformed_but_safe"
    assert req.imu is None
    assert req.ppg is None
    assert req.timestamp
