from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

class DevicePacketSchema(BaseModel):

    device_id: str = Field(..., min_length=1, max_length=64)
    timestamp_ms: int = Field(..., ge=0)
    mode: str = Field(..., pattern=r"^(real|mock)$")
    packet_seq: int = Field(..., ge=0)

    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float

    red_value: int = Field(..., ge=0)
    ir_value: int = Field(..., ge=0)
    heart_rate: float = Field(..., ge=0)
    spo2: float = Field(..., ge=0, le=100)
    signal_quality: float = Field(..., ge=0, le=1)

    imu_ok: bool
    ppg_ok: bool
    hr_valid: bool
    spo2_valid: bool
    finger_detected: bool

    state_hint: str = Field(default="normal", max_length=50)

    # Paket modunun yalnizca gercek veya mock olmasini dogrular.
    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("real", "mock"):
            raise ValueError("mode must be 'real' or 'mock'")
        return v

# Ham sozlugu semaya cevirip zorunlu alanlari dogrular.
def validate_packet(data: dict) -> DevicePacketSchema:
    return DevicePacketSchema(**data)


class RawSensorSample(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64)
    timestamp_ms: int = Field(..., ge=0)
    sample_seq: int = Field(..., ge=0)
    window_seq: int = Field(..., ge=0)
    sample_rate_hz: int = Field(..., ge=1)
    mode: str = Field(..., pattern=r"^(real|mock)$")

    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float

    red_value: int = Field(..., ge=0)
    ir_value: int = Field(..., ge=0)
    imu_ok: bool
    ppg_ok: bool
    finger_detected: bool
    signal_quality: float = Field(..., ge=0, le=1)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("real", "mock"):
            raise ValueError("mode must be 'real' or 'mock'")
        return v


class ModelWindowPayload(BaseModel):
    device_id: str
    mode: str
    window_seq: int
    sample_rate_hz: int
    sample_count: int
    window_duration_ms: int
    timestamp_start_ms: int
    timestamp_end_ms: int
    imu_samples: list[list[float]]
    ppg_samples: list[list[float]]
    quality_summary: dict
    latest_vitals: dict | None = None
    source: str | None = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("real", "mock"):
            raise ValueError("mode must be 'real' or 'mock'")
        return v

    @field_validator("imu_samples")
    @classmethod
    def validate_imu_rows(cls, rows: list[list[float]]) -> list[list[float]]:
        for row in rows:
            if len(row) != 6:
                raise ValueError("imu_samples rows must have length 6")
        return rows

    @field_validator("ppg_samples")
    @classmethod
    def validate_ppg_rows(cls, rows: list[list[float]]) -> list[list[float]]:
        for row in rows:
            if len(row) not in (1, 2):
                raise ValueError("ppg_samples rows must have length 1 or 2")
        return rows

    @field_validator("sample_count")
    @classmethod
    def validate_sample_count(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("sample_count must be > 0")
        return v


def validate_raw_sample(data: dict) -> RawSensorSample:
    return RawSensorSample(**data)


def validate_model_window_payload(data: dict) -> ModelWindowPayload:
    return ModelWindowPayload(**data)
