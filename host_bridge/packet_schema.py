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

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("real", "mock"):
            raise ValueError("mode must be 'real' or 'mock'")
        return v

def validate_packet(data: dict) -> DevicePacketSchema:
    return DevicePacketSchema(**data)
