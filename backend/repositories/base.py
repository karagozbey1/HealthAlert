from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class AbstractUserRepo(ABC):
    """Kullanici verileri icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def update(self, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def list_by_role(self, role: str) -> List[Dict[str, Any]]: ...


class AbstractLinkCodeRepo(ABC):
    """Baglanti kodu verileri icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def get_by_id(self, code_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def get_by_code(self, code: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def update(self, code_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def list_by_owner(self, owner_id: str) -> List[Dict[str, Any]]: ...


class AbstractRelationRepo(ABC):
    """Kullanici iliskileri icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def get_by_id(self, relation_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def update(self, relation_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def find_active_by_self_user(self, self_user_id: str) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def find_active_by_linked_user(self, linked_user_id: str) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def find_active_link(self, self_user_id: str, linked_user_id: str) -> Optional[Dict[str, Any]]: ...


class AbstractLiveStatusRepo(ABC):
    """Canli durum verileri icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def get_by_user(self, user_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def upsert(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]: ...


class AbstractAnomalyRepo(ABC):
    """Anomali kayitlari icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def list_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]: ...


class AbstractAlertRepo(ABC):
    """Alarm kayitlari icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def get_by_id(self, alert_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def update(self, alert_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def list_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def get_active_by_user(self, user_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def get_countdown_alerts(self, user_id: str) -> List[Dict[str, Any]]: ...


class AbstractPostEventRepo(ABC):
    """Alarm sonrasi olay kayitlari icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def get_by_id(self, session_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def update(self, session_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...


class AbstractHistoryRepo(ABC):
    """Gecmis olcum kayitlari icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def list_by_user(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]: ...


class AbstractNotificationRepo(ABC):
    """Bildirim kayitlari icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def list_by_recipient(self, recipient_id: str, limit: int = 100) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def mark_read(self, notif_id: str, recipient_id: str) -> bool: ...

    @abstractmethod
    async def mark_all_read(self, recipient_id: str) -> int: ...


class AbstractClinicalNoteRepo(ABC):
    """Klinik not kayitlari icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def get_by_id(self, note_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def update(self, note_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def delete(self, note_id: str) -> bool: ...

    @abstractmethod
    async def list_by_patient(self, patient_id: str, doctor_id: Optional[str] = None) -> List[Dict[str, Any]]: ...


class AbstractSettingsRepo(ABC):
    """Kullanici ayarlari icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def get_or_create(self, user_id: str) -> Dict[str, Any]: ...

    @abstractmethod
    async def update(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]: ...


class AbstractSimulationStateRepo(ABC):
    """Simulasyon durumu icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def get_or_create(self, user_id: str) -> Dict[str, Any]: ...

    @abstractmethod
    async def update(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]: ...


class AbstractDeviceRepo(ABC):
    """Cihaz kayit ve paket loglari icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def register_device(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def get_registration(self, device_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def update_registration(self, device_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def log_packet(self, data: Dict[str, Any]) -> Dict[str, Any]: ...


class AbstractBaselineRepo(ABC):
    """Kisisel baz degerler icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def create_for_user(self, user_id: str) -> Dict[str, Any]: ...

    @abstractmethod
    async def get_or_create(self, user_id: str) -> Dict[str, Any]: ...

    @abstractmethod
    async def update_values(self, user_id: str, values: Dict[str, Any]) -> Dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Part 5A - Learning Loop repository
# ---------------------------------------------------------------------------


class AbstractLearningRepo(ABC):
    """Ogrenme pencereleri ve model versiyonlari icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def create_session(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def close_session(self, session_id: str, ended_at) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def create_window(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def list_windows(
        self,
        user_id: Optional[str] = None,
        training_candidate: Optional[bool] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def get_window(self, window_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def mark_window_candidate(self, window_id: str, status: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def update_window_feedback(self, window_id: str, feedback_label: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def create_feedback(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def get_feedback_for_window(self, window_id: str) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def create_model_version(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def list_model_versions(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def get_active_model_version(self) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def list_windows_for_export(
        self,
        user_id: Optional[str] = None,
        include_demo: bool = False,
        min_quality_confidence: float = 0.0,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def mark_windows_exported(self, window_ids: List[str]) -> int: ...


# ---------------------------------------------------------------------------
# Part 5B - Adaptive Personalization repository
# ---------------------------------------------------------------------------


class AbstractPersonalizationRepo(ABC):
    """Kisisellestirme verileri icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def get_or_create_profile(self, user_id: str) -> Dict[str, Any]: ...

    @abstractmethod
    async def update_profile(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def add_risk_memory(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def list_risk_memory(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def create_trend_snapshot(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def get_latest_trend_snapshot(self, user_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def summarize_personalization(self, user_id: str) -> Dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Part 5C - Care Assistant Orchestrator repository
# ---------------------------------------------------------------------------


class AbstractAssistantRepo(ABC):
    """Bakim asistani durumu ve aksiyonlari icin repository sozlesmesini tanimlar."""

    @abstractmethod
    async def get_or_create_state(self, user_id: str) -> Dict[str, Any]: ...

    @abstractmethod
    async def update_state(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def create_action(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def list_active_actions(self, user_id: str) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def complete_action(self, action_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def create_ack(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def get_due_ack_timeouts(self, now: Any) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def list_assistant_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]: ...
