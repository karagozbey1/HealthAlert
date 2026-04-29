from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class AbstractUserRepo(ABC):
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
    @abstractmethod
    async def get_by_user(self, user_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def upsert(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]: ...

class AbstractAnomalyRepo(ABC):
    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def list_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]: ...

class AbstractAlertRepo(ABC):
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
    @abstractmethod
    async def get_by_id(self, session_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def update(self, session_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...

class AbstractHistoryRepo(ABC):
    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def list_by_user(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]: ...

class AbstractNotificationRepo(ABC):
    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def list_by_recipient(self, recipient_id: str, limit: int = 100) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def mark_read(self, notif_id: str, recipient_id: str) -> bool: ...

    @abstractmethod
    async def mark_all_read(self, recipient_id: str) -> int: ...

class AbstractClinicalNoteRepo(ABC):
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
    @abstractmethod
    async def get_or_create(self, user_id: str) -> Dict[str, Any]: ...

    @abstractmethod
    async def update(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]: ...

class AbstractSimulationStateRepo(ABC):
    @abstractmethod
    async def get_or_create(self, user_id: str) -> Dict[str, Any]: ...

    @abstractmethod
    async def update(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]: ...

class AbstractDeviceRepo(ABC):
    @abstractmethod
    async def register_device(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def get_registration(self, device_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def update_registration(self, device_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def log_packet(self, data: Dict[str, Any]) -> Dict[str, Any]: ...
