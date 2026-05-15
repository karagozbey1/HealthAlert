from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from src.healthalert.api.schemas.hybrid_inference_schema import HybridInferenceResponse

DEFAULT_PATIENT_ID = "demo_patient_001"

IMU_ALIASES = {
    "acc_x": ("acc_x", "ax", "ACC_X", "accX", "accel_x", "AccelX"),
    "acc_y": ("acc_y", "ay", "ACC_Y", "accY", "accel_y", "AccelY"),
    "acc_z": ("acc_z", "az", "ACC_Z", "accZ", "accel_z", "AccelZ"),
    "gyro_x": ("gyro_x", "gx", "GYRO_X", "gyroX"),
    "gyro_y": ("gyro_y", "gy", "GYRO_Y", "gyroY"),
    "gyro_z": ("gyro_z", "gz", "GYRO_Z", "gyroZ"),
}

PPG_ALIASES = {
    "ir": ("ir", "IR", "ppg_ir", "ir_value"),
    "red": ("red", "RED", "ppg_red", "red_value"),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _first_present(source: Dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        if alias in source and source[alias] is not None:
            return source[alias]
    return None


def normalize_live_sensor_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(data)

    normalized["patient_id"] = (
        normalized.get("patient_id")
        or normalized.get("patientId")
        or normalized.get("patient")
        or normalized.get("user_id")
        or DEFAULT_PATIENT_ID
    )
    normalized["timestamp"] = str(
        normalized.get("timestamp")
        or normalized.get("time")
        or normalized.get("timestamp_ms")
        or _utc_now_iso()
    )
    source = normalized.get("source") or "esp32"
    if source not in {"esp32", "demo", "firebase"}:
        source = "esp32"
    normalized["source"] = source

    imu_source = normalized.get("imu")
    if not isinstance(imu_source, dict):
        imu_source = normalized
    imu = {}
    for canonical, aliases in IMU_ALIASES.items():
        value = _first_present(imu_source, aliases)
        if value is None:
            value = _first_present(normalized, aliases)
        if value is not None:
            imu[canonical] = value
    if len(imu) == len(IMU_ALIASES):
        normalized["imu"] = imu

    ppg_source = normalized.get("ppg")
    if not isinstance(ppg_source, dict):
        ppg_source = normalized
    ppg = {}
    for canonical, aliases in PPG_ALIASES.items():
        value = _first_present(ppg_source, aliases)
        if value is None:
            value = _first_present(normalized, aliases)
        if value is not None:
            ppg[canonical] = value
    ppg_ok = normalized.get("ppg_ok")
    if ppg and ppg_ok is not False:
        normalized["ppg"] = ppg
    elif ppg_ok is False:
        normalized["ppg"] = None

    if normalized.get("heart_rate") is None:
        normalized["heart_rate"] = normalized.get("hr")
    if normalized.get("spo2") is None:
        normalized["spo2"] = normalized.get("SpO2")

    return normalized


class IMUSampleBlock(BaseModel):
    acc_x: float
    acc_y: float
    acc_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float


class PPGSampleBlock(BaseModel):
    ir: Optional[float] = None
    red: Optional[float] = None


class LiveSensorSampleRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    timestamp: str
    imu: Optional[IMUSampleBlock] = None
    ppg: Optional[PPGSampleBlock] = None
    heart_rate: Optional[float] = None
    spo2: Optional[float] = None
    source: Literal["esp32", "demo", "firebase"] = "esp32"
    user_baseline: Optional[Dict[str, Any]] = None
    user_confirmed_okay: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_esp32_payload(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return normalize_live_sensor_payload(value)
        return value


class LiveSensorSampleResponse(BaseModel):
    patient_id: str
    timestamp: str
    data_mode: Literal["live"]
    window_ready: bool
    buffered_imu_samples: int
    inference_triggered: bool
    status: str
    inference_result: Optional[HybridInferenceResponse] = None
    missing_modalities: Dict[str, bool]
    ingestion_notes: List[str]
