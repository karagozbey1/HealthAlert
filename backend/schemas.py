from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator

class RegisterRequest(BaseModel):
    """API sözleşmesindeki RegisterRequest veri alanlarını doğrular."""
    email: str
    password: str
    role: str
    full_name: str
    phone: Optional[str] = None
    birth_date: Optional[str] = None

    # Kayit sirasinda rol degerini sinirlar.
    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """schemas şemasındaki yardımcı doğrulama adımını yürütür."""
        if v not in ("SELF", "RELATIVE", "DOCTOR"):
            raise ValueError("role must be SELF, RELATIVE, or DOCTOR")
        return v

class LoginRequest(BaseModel):
    """API sözleşmesindeki LoginRequest veri alanlarını doğrular."""
    email: str
    password: str

class TokenResponse(BaseModel):
    """API sözleşmesindeki TokenResponse veri alanlarını doğrular."""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    full_name: str

class UserResponse(BaseModel):
    """API sözleşmesindeki UserResponse veri alanlarını doğrular."""
    id: str
    email: str
    role: str
    full_name: str
    phone: Optional[str]
    birth_date: Optional[str]
    created_at: datetime

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True

class UpdateProfileRequest(BaseModel):
    """API sözleşmesindeki UpdateProfileRequest veri alanlarını doğrular."""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    birth_date: Optional[str] = None

class LinkCodeResponse(BaseModel):
    """API sözleşmesindeki LinkCodeResponse veri alanlarını doğrular."""
    id: str
    code: str
    code_type: str
    is_active: bool
    uses_remaining: int
    expires_at: datetime
    created_at: datetime

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True

class LinkCodeGenerateRequest(BaseModel):
    """API sözleşmesindeki LinkCodeGenerateRequest veri alanlarını doğrular."""
    relation_type: str = "RELATIVE"

    # Uretilen baglanti kodunun iliski tipini dogrular.
    @field_validator("relation_type")
    @classmethod
    def validate_relation_type(cls, v: str) -> str:
        """schemas şemasındaki yardımcı doğrulama adımını yürütür."""
        relation_type = v.upper()
        if relation_type not in ("RELATIVE", "DOCTOR"):
            raise ValueError("relation_type must be RELATIVE or DOCTOR")
        return relation_type

class RedeemCodeRequest(BaseModel):
    """API sözleşmesindeki RedeemCodeRequest veri alanlarını doğrular."""
    code: str

class RedeemCodeResponse(BaseModel):
    """API sözleşmesindeki RedeemCodeResponse veri alanlarını doğrular."""
    relation_id: str
    self_user_id: str
    linked_user_id: str
    relation_type: str
    linked_user_name: str

class UserRelationResponse(BaseModel):
    """API sözleşmesindeki UserRelationResponse veri alanlarını doğrular."""
    id: str
    self_user_id: str
    linked_user_id: str
    relation_type: str
    is_active: bool
    linked_user_name: str
    created_at: datetime

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True

class LiveStatusResponse(BaseModel):
    """API sözleşmesindeki LiveStatusResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    heart_rate: float
    spo2: float
    motion_score: float
    risk_score: float
    scenario: str
    timestamp: datetime
    final_risk_score: Optional[float] = None
    personalized_risk_score: Optional[float] = None
    ml_evidence_score: Optional[float] = None
    ml_adjustment: Optional[float] = None
    fusion_applied: Optional[bool] = None
    model_window_status: Optional[dict] = None
    ml_base_score: Optional[float] = None
    personal_adjustment: Optional[float] = None
    fusion_mode: Optional[str] = None
    model_version: Optional[str] = None
    ml_confidence: Optional[float] = None
    # BLE / sensor quality fields (populated from latest device packet)
    signal_quality: Optional[float] = None
    hr_valid: Optional[bool] = None
    spo2_valid: Optional[bool] = None
    finger_present: Optional[bool] = None
    source: Optional[str] = None

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


class PatientSummaryResponse(BaseModel):
    """API sözleşmesindeki PatientSummaryResponse veri alanlarını doğrular."""
    patient_id: str
    display_name: str
    email: str
    role: str
    has_live_data: bool = False
    latest_timestamp: Optional[datetime] = None
    heart_rate: Optional[float] = None
    heart_rate_valid: Optional[bool] = None
    spo2: Optional[float] = None
    spo2_valid: Optional[bool] = None
    movement_percent: Optional[float] = None
    risk_score: Optional[float] = None
    risk_level: str = "unknown"
    signal_quality: Optional[float] = None
    last_seen_seconds: Optional[int] = None
    finger_present: Optional[bool] = None
    source: Optional[str] = None

class AnomalyResponse(BaseModel):
    """API sözleşmesindeki AnomalyResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    metric: str
    value: float
    unit: str
    severity: str
    detected_at: datetime
    summary: str

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True

class AlertResponse(BaseModel):
    """API sözleşmesindeki AlertResponse veri alanlarını doğrular."""
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
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True

class AlertRespondRequest(BaseModel):
    """API sözleşmesindeki AlertRespondRequest veri alanlarını doğrular."""
    action: str

class HelpRequestResponse(BaseModel):
    """API sözleşmesindeki HelpRequestResponse veri alanlarını doğrular."""
    alert_id: str
    notified_count: int
    message: str

class PostEventSessionResponse(BaseModel):
    """API sözleşmesindeki PostEventSessionResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    alert_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    outcome: Optional[str]

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True

class ClosePostEventRequest(BaseModel):
    """API sözleşmesindeki ClosePostEventRequest veri alanlarını doğrular."""
    outcome: str

class HistoryResponse(BaseModel):
    """API sözleşmesindeki HistoryResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    item_type: str
    title: str
    subtitle: str
    timestamp: datetime
    severity: str
    outcome: Optional[str]

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True

class NotificationResponse(BaseModel):
    """API sözleşmesindeki NotificationResponse veri alanlarını doğrular."""
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
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True

class ClinicalNoteCreate(BaseModel):
    """API sözleşmesindeki ClinicalNoteCreate veri alanlarını doğrular."""
    patient_id: str
    note: str
    recommendation: Optional[str] = None

class ClinicalNoteUpdate(BaseModel):
    """API sözleşmesindeki ClinicalNoteUpdate veri alanlarını doğrular."""
    note: Optional[str] = None
    recommendation: Optional[str] = None

class ClinicalNoteResponse(BaseModel):
    """API sözleşmesindeki ClinicalNoteResponse veri alanlarını doğrular."""
    id: str
    doctor_id: str
    patient_id: str
    note: str
    recommendation: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True

class SettingsResponse(BaseModel):
    """API sözleşmesindeki SettingsResponse veri alanlarını doğrular."""
    user_id: str
    notifications_enabled: bool
    battery_mode: str
    background_monitoring: bool
    update_interval_seconds: int
    alert_sensitivity: str = "normal"

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True

class SettingsUpdate(BaseModel):
    """API sözleşmesindeki SettingsUpdate veri alanlarını doğrular."""
    notifications_enabled: Optional[bool] = None
    battery_mode: Optional[str] = None
    background_monitoring: Optional[bool] = None
    update_interval_seconds: Optional[int] = None
    alert_sensitivity: Optional[str] = None

class DevicePacketRequest(BaseModel):
    """API sözleşmesindeki DevicePacketRequest veri alanlarını doğrular."""
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

    # Paket modunun yalnizca gercek veya mock olmasini dogrular.
    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """schemas şemasındaki yardımcı doğrulama adımını yürütür."""
        if v not in ("real", "mock"):
            raise ValueError("mode must be 'real' or 'mock'")
        return v

class DevicePacketResponse(BaseModel):
    """API sözleşmesindeki DevicePacketResponse veri alanlarını doğrular."""
    status: str
    packet_seq: int
    device_id: str
    user_id: Optional[str] = None
    risk_breakdown: Optional[dict] = None
    # Part 2: Devre disi veya kullanicisiz akista bos kalabilir.
    window_status: Optional[dict] = None
    ml_shadow_result: Optional[dict] = None
    # Part 3: Retrieval sonucu sadece izleme metadata'sidir.
    retrieval_shadow_result: Optional[dict] = None
    # Part 5A: Ogrenme yakalama ozeti risk skorunu degistirmez.
    learning_capture_result: Optional[dict] = None
    # Part 5B: Kisisellestirme ozeti risk kiriliminda da tasinabilir.
    personalization_result: Optional[dict] = None
    # Part 5C: Bakim asistani modu ve aksiyonlarini tasir.
    assistant_state: Optional[dict] = None
    assistant_actions: Optional[list] = None


class DeviceModelWindowRequest(BaseModel):
    """API sözleşmesindeki DeviceModelWindowRequest veri alanlarını doğrular."""
    device_id: str
    mode: str
    window_seq: int
    sample_rate_hz: int
    sample_count: int
    window_duration_ms: int
    timestamp_start_ms: int
    timestamp_end_ms: int
    imu_samples: List[List[float]]
    ppg_samples: List[List[float]]
    quality_summary: Optional[dict[str, Any]] = None
    latest_vitals: Optional[dict[str, Any]] = None
    source: Optional[str] = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """schemas şemasındaki yardımcı doğrulama adımını yürütür."""
        if v not in ("real", "mock"):
            raise ValueError("mode must be 'real' or 'mock'")
        return v

    @model_validator(mode="after")
    def validate_shapes(self):
        """schemas şemasındaki yardımcı doğrulama adımını yürütür."""
        if self.sample_count != len(self.imu_samples):
            raise ValueError("sample_count must match imu_samples length")
        if self.sample_count != len(self.ppg_samples):
            raise ValueError("sample_count must match ppg_samples length")
        for row in self.imu_samples:
            if len(row) != 6:
                raise ValueError("each imu_samples row must have length 6")
        for row in self.ppg_samples:
            if len(row) not in (1, 2):
                raise ValueError("each ppg_samples row must have length 1 or 2")
        if self.timestamp_end_ms < self.timestamp_start_ms:
            raise ValueError("timestamp_end_ms must be >= timestamp_start_ms")
        return self


class DeviceModelWindowResponse(BaseModel):
    """API sözleşmesindeki DeviceModelWindowResponse veri alanlarını doğrular."""
    status: str
    device_id: str
    user_id: Optional[str] = None
    window_seq: int
    model_ready: bool
    ml_live_result: Optional[dict] = None
    ml_evidence_result: Optional[dict] = None
    fusion_result: Optional[dict] = None
    final_risk_score: Optional[float] = None
    reason: Optional[str] = None


class UserBaselineResponse(BaseModel):
    """API sözleşmesindeki UserBaselineResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    hr_mean: float
    hr_std: float
    spo2_mean: float
    spo2_std: float
    motion_mean: float
    motion_std: float
    ppg_quality_mean: float
    sample_count: int
    is_ready: bool
    created_at: datetime
    updated_at: datetime
    last_updated: Optional[datetime] = None

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


class BaselineStatusResponse(BaseModel):
    """API sözleşmesindeki BaselineStatusResponse veri alanlarını doğrular."""
    user_id: str
    is_ready: bool
    sample_count: int
    hr_mean: float
    spo2_mean: float

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


# ---------------------------------------------------------------------------
# Part 5A: Ogrenme dongusu semalari
# ---------------------------------------------------------------------------

class LearningCaptureSessionResponse(BaseModel):
    """API sözleşmesindeki LearningCaptureSessionResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    device_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    source: str
    mode: str
    sample_count: int
    quality_sample_count: int
    low_quality_sample_count: int
    event_count: int
    has_user_feedback: bool
    training_candidate: bool
    training_status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


class LearningWindowResponse(BaseModel):
    """API sözleşmesindeki LearningWindowResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    device_id: str
    session_id: Optional[str]
    window_start_at: datetime
    window_end_at: datetime
    duration_sec: float
    sample_count: int
    source: str
    risk_level_at_capture: str
    final_risk_score: float
    quality_confidence: float
    baseline_ready: bool
    ml_shadow_summary: Optional[dict] = None
    retrieval_shadow_summary: Optional[dict] = None
    assistant_mode: Optional[str]
    user_feedback_label: Optional[str]
    suggested_label: Optional[str]
    label_confidence: Optional[float]
    training_candidate: bool
    exported_at: Optional[datetime]
    created_at: datetime

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


class UserFeedbackCreate(BaseModel):
    """API sözleşmesindeki UserFeedbackCreate veri alanlarını doğrular."""
    user_id: str
    related_window_id: Optional[str] = None
    related_alert_id: Optional[str] = None
    feedback_type: str
    feedback_source: str = "mobile"
    note: Optional[str] = None

    # Geri bildirim tipinin izinli degerlerden gelmesini saglar.
    @field_validator("feedback_type")
    @classmethod
    def validate_feedback_type(cls, v: str) -> str:
        """schemas şemasındaki yardımcı doğrulama adımını yürütür."""
        allowed = {"ok", "not_ok", "false_alarm", "fall_confirmed", "sensor_error", "other"}
        if v not in allowed:
            raise ValueError(f"feedback_type must be one of {allowed}")
        return v

    # Geri bildirim kaynaginin desteklenen kanallardan gelmesini saglar.
    @field_validator("feedback_source")
    @classmethod
    def validate_feedback_source(cls, v: str) -> str:
        """schemas şemasındaki yardımcı doğrulama adımını yürütür."""
        allowed = {"mobile", "relative", "doctor", "system"}
        if v not in allowed:
            raise ValueError(f"feedback_source must be one of {allowed}")
        return v


class UserFeedbackResponse(BaseModel):
    """API sözleşmesindeki UserFeedbackResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    related_window_id: Optional[str]
    related_alert_id: Optional[str]
    feedback_type: str
    feedback_source: str
    note: Optional[str]
    created_at: datetime

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


class TrainingExportRequest(BaseModel):
    """API sözleşmesindeki TrainingExportRequest veri alanlarını doğrular."""
    user_id: Optional[str] = None
    training_status: Optional[str] = None
    min_quality_confidence: Optional[float] = None
    include_demo: bool = False
    limit: int = 1000


class TrainingExportResponse(BaseModel):
    """API sözleşmesindeki TrainingExportResponse veri alanlarını doğrular."""
    export_dir: str
    window_count: int
    feedback_count: int
    export_summary: dict


class ModelVersionResponse(BaseModel):
    """API sözleşmesindeki ModelVersionResponse veri alanlarını doğrular."""
    id: str
    model_name: str
    version: str
    model_path: str
    training_data_snapshot: Optional[str]
    metrics_json: Optional[dict] = None
    status: str
    created_at: datetime
    activated_at: Optional[datetime]

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


# ---------------------------------------------------------------------------
# Part 5B: Uyarlanabilir kisisellestirme semalari
# ---------------------------------------------------------------------------

class PersonalHealthProfileResponse(BaseModel):
    """API sözleşmesindeki PersonalHealthProfileResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    baseline_id: Optional[str]
    personalization_level: str
    total_observation_minutes: float
    total_valid_samples: int
    total_feedback_count: int
    false_alarm_count: int
    confirmed_risk_count: int
    sensor_error_count: int
    typical_hr_min: float
    typical_hr_max: float
    typical_spo2_min: float
    typical_spo2_max: float
    typical_motion_min: float
    typical_motion_max: float
    day_profile_json: Optional[dict] = None
    night_profile_json: Optional[dict] = None
    activity_profile_json: Optional[dict] = None
    ml_window_count: int = 0
    ml_usable_window_count: int = 0
    ml_evidence_mean: float = 0.0
    ml_evidence_std: float = 0.0
    ml_confidence_mean: float = 0.0
    ml_positive_support_count: int = 0
    ml_personal_disagreement_count: int = 0
    last_ml_evidence_score: Optional[float] = None
    last_ml_adjustment: Optional[float] = None
    last_model_window_at: Optional[datetime] = None
    last_recalibrated_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


class PersonalRiskMemoryResponse(BaseModel):
    """API sözleşmesindeki PersonalRiskMemoryResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    event_type: str
    risk_score: float
    severity: Optional[str]
    context_json: Optional[dict] = None
    created_at: datetime

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


class PersonalTrendSnapshotResponse(BaseModel):
    """API sözleşmesindeki PersonalTrendSnapshotResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    window_minutes: int
    hr_trend: str
    spo2_trend: str
    motion_trend: str
    quality_trend: str
    risk_trend: str
    trend_confidence: float
    created_at: datetime

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


class PersonalizationSummaryResponse(BaseModel):
    """API sözleşmesindeki PersonalizationSummaryResponse veri alanlarını doğrular."""
    user_id: str
    personalization_level: str
    total_valid_samples: int
    total_observation_minutes: float
    false_alarm_rate: float
    confirmed_risk_count: int
    feedback_count: int
    latest_trend: Optional[dict] = None
    typical_ranges: dict


class RiskBreakdownResponse(BaseModel):
    """API sözleşmesindeki RiskBreakdownResponse veri alanlarını doğrular."""
    global_risk_score: float
    final_risk_score: float
    personal_deviation_score: float
    baseline_ready: bool
    quality_confidence: float
    quality_warning: Optional[str] = None

class DeviceRegistrationRequest(BaseModel):
    """API sözleşmesindeki DeviceRegistrationRequest veri alanlarını doğrular."""
    device_id: str

class DeviceRegistrationResponse(BaseModel):
    """API sözleşmesindeki DeviceRegistrationResponse veri alanlarını doğrular."""
    id: str
    device_id: str
    user_id: str
    registered_at: datetime
    is_active: bool

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True

class AIInferenceRequest(BaseModel):
    """API sözleşmesindeki AIInferenceRequest veri alanlarını doğrular."""
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

    # AI cikti risk seviyesinin desteklenen aralikta kalmasini saglar.
    @field_validator("final_risk_level")
    @classmethod
    def validate_risk_level(cls, v: str) -> str:
        """schemas şemasındaki yardımcı doğrulama adımını yürütür."""
        if v not in ("normal", "watch", "warning", "critical"):
            raise ValueError("final_risk_level must be normal|watch|warning|critical")
        return v

class AIInferenceResponse(BaseModel):
    """API sözleşmesindeki AIInferenceResponse veri alanlarını doğrular."""
    status: str
    risk_level: str
    anomaly_id: Optional[str] = None
    alert_id: Optional[str] = None
    notifications_sent: int = 0

class RegisterDeviceTokenRequest(BaseModel):
    """API sözleşmesindeki RegisterDeviceTokenRequest veri alanlarını doğrular."""
    token: str
    platform: str

    # Cihaz token platformunu izinli istemcilerle sinirlar.
    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        """schemas şemasındaki yardımcı doğrulama adımını yürütür."""
        if v not in ("android", "ios", "web"):
            raise ValueError("platform must be android, ios, or web")
        return v

class DeviceTokenResponse(BaseModel):
    """API sözleşmesindeki DeviceTokenResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    token: str
    platform: str
    created_at: datetime

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


# ---------------------------------------------------------------------------
# Part 5C: Bakim asistani semalari
# ---------------------------------------------------------------------------

class AssistantStateResponse(BaseModel):
    """API sözleşmesindeki AssistantStateResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    current_mode: str
    previous_mode: Optional[str] = None
    last_risk_score: float
    last_severity: Optional[str] = None
    personalization_level: Optional[str] = None
    watch_started_at: Optional[datetime] = None
    warning_started_at: Optional[datetime] = None
    critical_started_at: Optional[datetime] = None
    awaiting_user_ack: bool
    ack_deadline_at: Optional[datetime] = None
    last_user_response: Optional[str] = None
    last_action_summary: Optional[dict] = None
    monitoring_intensity: str
    recommended_poll_interval_sec: int
    created_at: datetime
    updated_at: datetime

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


class AssistantActionResponse(BaseModel):
    """API sözleşmesindeki AssistantActionResponse veri alanlarını doğrular."""
    id: str
    user_id: str
    state_id: Optional[str] = None
    mode: str
    action_type: str
    message: str
    priority: str
    requires_ack: bool
    ack_options: Optional[dict] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata_json: Optional[dict] = None

    class Config:
        """API sözleşmesindeki Config veri alanlarını doğrular."""
        from_attributes = True


class AssistantAckRequest(BaseModel):
    """API sözleşmesindeki AssistantAckRequest veri alanlarını doğrular."""
    user_id: str
    response: str   # ok | not_ok | false_alarm
    note: Optional[str] = None
    action_id: Optional[str] = None


class AssistantAckResponse(BaseModel):
    """API sözleşmesindeki AssistantAckResponse veri alanlarını doğrular."""
    success: bool
    new_mode: str
    message: str
    actions_created: list = []


class AssistantSummaryResponse(BaseModel):
    """API sözleşmesindeki AssistantSummaryResponse veri alanlarını doğrular."""
    user_id: str
    current_mode: str
    monitoring_intensity: str
    recommended_poll_interval_sec: int
    awaiting_user_ack: bool
    ack_deadline_at: Optional[datetime] = None
    last_risk_score: float
    last_severity: Optional[str] = None
    active_action_count: int
    last_user_response: Optional[str] = None
    should_sound_alarm: bool
    guidance_messages: list = []

