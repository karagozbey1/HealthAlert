from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, field_validator

class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str
    full_name: str
    phone: Optional[str] = None
    birth_date: Optional[str] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("SELF", "RELATIVE", "DOCTOR"):
            raise ValueError("role must be SELF, RELATIVE, or DOCTOR")
        return v

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    full_name: str

class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    full_name: str
    phone: Optional[str]
    birth_date: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    birth_date: Optional[str] = None

class LinkCodeResponse(BaseModel):
    id: str
    code: str
    code_type: str
    is_active: bool
    uses_remaining: int
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True

class LinkCodeGenerateRequest(BaseModel):
    relation_type: str = "RELATIVE"

    @field_validator("relation_type")
    @classmethod
    def validate_relation_type(cls, v: str) -> str:
        relation_type = v.upper()
        if relation_type not in ("RELATIVE", "DOCTOR"):
            raise ValueError("relation_type must be RELATIVE or DOCTOR")
        return relation_type

class RedeemCodeRequest(BaseModel):
    code: str

class RedeemCodeResponse(BaseModel):
    relation_id: str
    self_user_id: str
    linked_user_id: str
    relation_type: str
    linked_user_name: str

class UserRelationResponse(BaseModel):
    id: str
    self_user_id: str
    linked_user_id: str
    relation_type: str
    is_active: bool
    linked_user_name: str
    created_at: datetime

    class Config:
        from_attributes = True

class LiveStatusResponse(BaseModel):
    id: str
    user_id: str
    heart_rate: float
    spo2: float
    motion_score: float
    risk_score: float
    scenario: str
    timestamp: datetime

    class Config:
        from_attributes = True

class AnomalyResponse(BaseModel):
    id: str
    user_id: str
    metric: str
    value: float
    unit: str
    severity: str
    detected_at: datetime
    summary: str

    class Config:
        from_attributes = True

class AlertResponse(BaseModel):
    id: str
    user_id: str
    title: str
    description: str
    severity: str
    status: str
    created_at: datetime
    countdown_total_sec: int
    countdown_remaining_sec: int
    recommendations: List[str]
    related_anomaly_id: Optional[str]
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True

class AlertRespondRequest(BaseModel):
    action: str

class PostEventSessionResponse(BaseModel):
    id: str
    user_id: str
    alert_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    outcome: Optional[str]

    class Config:
        from_attributes = True

class ClosePostEventRequest(BaseModel):
    outcome: str

class HistoryResponse(BaseModel):
    id: str
    user_id: str
    item_type: str
    title: str
    subtitle: str
    timestamp: datetime
    severity: str
    outcome: Optional[str]

    class Config:
        from_attributes = True

class NotificationResponse(BaseModel):
    id: str
    recipient_id: str
    sender_id: Optional[str]
    title: str
    body: str
    notification_type: str
    reference_id: Optional[str]
    reference_type: Optional[str]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ClinicalNoteCreate(BaseModel):
    patient_id: str
    note: str
    recommendation: Optional[str] = None

class ClinicalNoteUpdate(BaseModel):
    note: Optional[str] = None
    recommendation: Optional[str] = None

class ClinicalNoteResponse(BaseModel):
    id: str
    doctor_id: str
    patient_id: str
    note: str
    recommendation: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SettingsResponse(BaseModel):
    user_id: str
    notifications_enabled: bool
    battery_mode: str
    background_monitoring: bool
    update_interval_seconds: int

    class Config:
        from_attributes = True

class SettingsUpdate(BaseModel):
    notifications_enabled: Optional[bool] = None
    battery_mode: Optional[str] = None
    background_monitoring: Optional[bool] = None
    update_interval_seconds: Optional[int] = None

class DevicePacketRequest(BaseModel):
    device_id: str
    timestamp_ms: int
    mode: str
    packet_seq: int

    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float

    red_value: int
    ir_value: int
    heart_rate: float
    spo2: float
    signal_quality: float

    imu_ok: bool
    ppg_ok: bool
    hr_valid: bool
    spo2_valid: bool
    finger_detected: bool

    state_hint: Optional[str] = "normal"

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("real", "mock"):
            raise ValueError("mode must be 'real' or 'mock'")
        return v

class DevicePacketResponse(BaseModel):
    status: str
    packet_seq: int
    device_id: str
    user_id: Optional[str] = None

class DeviceRegistrationRequest(BaseModel):
    device_id: str

class DeviceRegistrationResponse(BaseModel):
    id: str
    device_id: str
    user_id: str
    registered_at: datetime
    is_active: bool

    class Config:
        from_attributes = True

class AIInferenceRequest(BaseModel):
    user_id: str

    fall_probability: float = 0.0
    instability_probability: float = 0.0
    ppg_quality_score: float = 1.0
    vital_confidence_score: float = 1.0
    early_risk_score: float = 0.0
    final_risk_level: str = "normal"
    immediate_alert: bool = False
    confidence: float = 1.0

    reasons: List[str] = []
    recommendations: List[str] = []
    raw_scores: Optional[dict] = None

    heart_rate: Optional[float] = None
    spo2: Optional[float] = None

    @field_validator("final_risk_level")
    @classmethod
    def validate_risk_level(cls, v: str) -> str:
        if v not in ("normal", "watch", "warning", "critical"):
            raise ValueError("final_risk_level must be normal|watch|warning|critical")
        return v

class AIInferenceResponse(BaseModel):
    status: str
    risk_level: str
    anomaly_id: Optional[str] = None
    alert_id: Optional[str] = None
    notifications_sent: int = 0

class RegisterDeviceTokenRequest(BaseModel):
    token: str
    platform: str

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        if v not in ("android", "ios", "web"):
            raise ValueError("platform must be android, ios, or web")
        return v

class DeviceTokenResponse(BaseModel):
    id: str
    user_id: str
    token: str
    platform: str
    created_at: datetime

    class Config:
        from_attributes = True

