from __future__ import annotations

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_care_assistant.db")


class InMemoryAssistantRepo:
    # Bellekte asistan durumu ve aksiyonlarını test için taklit eder.
    def __init__(self):
        self._states: Dict[str, Dict] = {}
        self._actions: List[Dict] = []
        self._acks: List[Dict] = []

    # Kullanıcı için durum kaydı yoksa oluşturup mevcut durumu döndürür.
    async def get_or_create_state(self, user_id: str) -> Dict:
        if user_id not in self._states:
            self._states[user_id] = {
                "id": str(uuid4()),
                "user_id": user_id,
                "current_mode": "normal",
                "previous_mode": None,
                "last_risk_score": 0.0,
                "last_severity": None,
                "personalization_level": None,
                "watch_started_at": None,
                "warning_started_at": None,
                "critical_started_at": None,
                "awaiting_user_ack": False,
                "ack_deadline_at": None,
                "last_user_response": None,
                "last_action_summary": None,
                "monitoring_intensity": "normal",
                "recommended_poll_interval_sec": 60,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        return dict(self._states[user_id])

    # Verilen alanları durum kaydına uygular ve güncel kopyayı döndürür.
    async def update_state(self, user_id: str, updates: Dict) -> Dict:
        state = await self.get_or_create_state(user_id)
        state.update(updates)
        state["updated_at"] = datetime.utcnow()
        self._states[user_id] = state
        return dict(state)

    # Yeni aksiyonu belleğe ekleyip kaydedilmiş kopyasını döndürür.
    async def create_action(self, data: Dict) -> Dict:
        action = dict(data)
        if "id" not in action:
            action["id"] = str(uuid4())
        self._actions.append(action)
        return dict(action)

    # Tamamlanmamış aksiyonları ilgili kullanıcı için listeler.
    async def list_active_actions(self, user_id: str) -> List[Dict]:
        return [
            dict(a) for a in self._actions
            if a["user_id"] == user_id and a.get("completed_at") is None
        ]

    # Eşleşen aksiyonu tamamlanmış olarak işaretler.
    async def complete_action(self, action_id: str) -> Optional[Dict]:
        for a in self._actions:
            if a["id"] == action_id:
                a["completed_at"] = datetime.utcnow()
                return dict(a)
        return None

    # Onay kaydını belleğe ekler.
    async def create_ack(self, data: Dict) -> Dict:
        ack = dict(data)
        self._acks.append(ack)
        return dict(ack)

    # Süresi dolmuş kullanıcı onaylarını seçer.
    async def get_due_ack_timeouts(self, now: datetime) -> List[Dict]:
        return [
            dict(s) for s in self._states.values()
            if s.get("awaiting_user_ack")
            and s.get("ack_deadline_at") is not None
            and s["ack_deadline_at"] <= now
        ]

    # Kullanıcının aksiyon geçmişini yeninden eskiye sıralayarak döndürür.
    async def list_assistant_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        actions = [a for a in self._actions if a["user_id"] == user_id]
        actions.sort(key=lambda a: a.get("created_at", datetime.min), reverse=True)
        return [dict(a) for a in actions[:limit]]


class FakeRepos:
    # Testlerde gereken repository alanlarını basit bir kapsayıcıda toplar.
    def __init__(self):
        self.assistant = InMemoryAssistantRepo()
        self.personalization = None
        self.learning = None


from services.care_assistant_service import (
    CareAssistantService,
    determine_mode,
    safe_guidance_for_context,
    build_actions_for_mode,
    MODE_NORMAL,
    MODE_WATCH,
    MODE_WARNING,
    MODE_CRITICAL,
)


class TestDetermineMode(unittest.TestCase):
    # Severity yokken düşük skorun normal modda kaldığını doğrular.
    def test_normal_no_severity(self):
        assert determine_mode(0.0, None) == MODE_NORMAL
        assert determine_mode(0.25, None) == MODE_NORMAL

    # Watch severity veya eşik skorunun watch modunu seçtiğini doğrular.
    def test_watch_severity(self):
        assert determine_mode(0.0, "watch") == MODE_WATCH
        assert determine_mode(0.30, None) == MODE_WATCH

    # Warning severity veya eşik skorunun warning modunu seçtiğini doğrular.
    def test_warning_severity(self):
        assert determine_mode(0.0, "warning") == MODE_WARNING
        assert determine_mode(0.60, None) == MODE_WARNING

    # Kritik severity ya da yüksek skorun kritik modu seçtiğini doğrular.
    def test_critical_severity(self):
        assert determine_mode(0.0, "critical") == MODE_CRITICAL
        assert determine_mode(0.80, None) == MODE_CRITICAL
        assert determine_mode(1.0, "critical") == MODE_CRITICAL

    # Yüksek skorun severity olmasa da öncelikli olduğunu doğrular.
    def test_score_takes_precedence(self):
        assert determine_mode(0.95, None) == MODE_CRITICAL


class TestSafeGuidance(unittest.TestCase):
    FORBIDDEN_KEYWORDS = ["aspirin", "ibuprofen", "ilaç", "teşhis", "tanı"]

    # Warning için en az bir güvenli yönlendirme döndüğünü doğrular.
    def test_warning_returns_messages(self):
        msgs = safe_guidance_for_context({}, "warning")
        assert len(msgs) > 0

    # Uyarı mesajlarında tıbbi terim geçmediğini doğrular.
    def test_no_clinical_terms(self):
        msgs = safe_guidance_for_context({"baseline_deviation_score": 0.20}, "warning")
        combined = " ".join(msgs).lower()
        for kw in self.FORBIDDEN_KEYWORDS:
            assert kw not in combined, f"Forbidden keyword '{kw}' found"

    # Kritik durumda sakinleştirici mesajların döndüğünü doğrular.
    def test_critical_returns_calm_messages(self):
        msgs = safe_guidance_for_context({}, "critical")
        assert len(msgs) > 0

    # Severity yoksa yönlendirme listesi üretilmediğini doğrular.
    def test_normal_returns_empty(self):
        msgs = safe_guidance_for_context({}, None)
        assert msgs == []


class TestBuildActionsForMode(unittest.TestCase):
    # Testlerde kullanılacak örnek durum sözlüğünü hazırlar.
    def _make_state(self) -> Dict:
        return {"id": str(uuid4()), "user_id": "u1"}

    # Normal modda gözlem aksiyonu üretildiğini doğrular.
    def test_normal_observe(self):
        actions = build_actions_for_mode("u1", MODE_NORMAL, self._make_state())
        assert len(actions) == 1
        assert actions[0]["action_type"] == "observe"

    # Watch modunda izleme artırma aksiyonu üretildiğini doğrular.
    def test_watch_increase_monitoring(self):
        actions = build_actions_for_mode("u1", MODE_WATCH, self._make_state())
        assert any(a["action_type"] == "increase_monitoring" for a in actions)

    # Warning modunda yönlendirme aksiyonu üretildiğini doğrular.
    def test_warning_show_guidance(self):
        actions = build_actions_for_mode("u1", MODE_WARNING, self._make_state())
        assert any(a["action_type"] == "show_guidance" for a in actions)

    # Kritik modun alarm ve kullanıcı onayı aksiyonlarını birlikte ürettiğini doğrular.
    def test_critical_alarm_and_ask(self):
        actions = build_actions_for_mode("u1", MODE_CRITICAL, self._make_state())
        types = {a["action_type"] for a in actions}
        assert "sound_alarm" in types
        assert "ask_are_you_ok" in types

    # Kritik onay aksiyonunun cevap bekleyecek şekilde üretildiğini doğrular.
    def test_critical_ask_requires_ack(self):
        actions = build_actions_for_mode("u1", MODE_CRITICAL, self._make_state())
        ask = next(a for a in actions if a["action_type"] == "ask_are_you_ok")
        assert ask["requires_ack"] is True
        assert ask["ack_options"] is not None


class TestEvaluateAssistantState(unittest.TestCase):
    # Asenkron test çağrılarını tek satırda çalıştırır.
    def _run(self, coro):
        return asyncio.run(coro)

    # Düşük riskte normal modun korunduğunu doğrular.
    def test_normal_mode(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        result = self._run(svc.evaluate_assistant_state(
            repos=repos, user_id="u1", final_risk_score=0.1, severity=None
        ))
        assert result["current_mode"] == MODE_NORMAL
        assert result["should_sound_alarm"] is False

    # Watch eşiklerinde watch moduna geçildiğini doğrular.
    def test_watch_mode(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        result = self._run(svc.evaluate_assistant_state(
            repos=repos, user_id="u1", final_risk_score=0.35, severity="watch"
        ))
        assert result["current_mode"] == MODE_WATCH

    # Warning eşiklerinde warning moduna geçildiğini doğrular.
    def test_warning_mode(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        result = self._run(svc.evaluate_assistant_state(
            repos=repos, user_id="u1", final_risk_score=0.65, severity="warning"
        ))
        assert result["current_mode"] == MODE_WARNING

    # Kritik eşiklerde alarm ve kullanıcı onayının başlatıldığını doğrular.
    def test_critical_mode(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        result = self._run(svc.evaluate_assistant_state(
            repos=repos, user_id="u1", final_risk_score=0.9, severity="critical"
        ))
        assert result["current_mode"] == MODE_CRITICAL
        assert result["should_sound_alarm"] is True
        assert result["awaiting_user_ack"] is True


class TestHandleAckOk(unittest.TestCase):
    # Asenkron test çağrılarını tek satırda çalıştırır.
    def _run(self, coro):
        return asyncio.run(coro)

    # Kullanıcı iyi olduğunu bildirdiğinde watch moduna dönüldüğünü doğrular.
    def test_ok_returns_watch(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        self._run(svc.evaluate_assistant_state(
            repos=repos, user_id="u1", final_risk_score=0.9, severity="critical"
        ))
        result = self._run(svc.handle_user_ack(repos=repos, user_id="u1", response="ok"))
        assert result["success"] is True
        assert result["new_mode"] == MODE_WATCH
        types = [a["action_type"] for a in result["actions_created"]]
        assert "return_to_watch" in types

    # İyi yanıtı sonrası onay bekleme durumunun kapandığını doğrular.
    def test_ack_cleared_after_ok(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        self._run(svc.evaluate_assistant_state(
            repos=repos, user_id="u1", final_risk_score=0.9, severity="critical"
        ))
        self._run(svc.handle_user_ack(repos=repos, user_id="u1", response="ok"))
        state = asyncio.run(repos.assistant.get_or_create_state("u1"))
        assert state["awaiting_user_ack"] is False


class TestHandleAckNotOk(unittest.TestCase):
    # Asenkron test çağrılarını tek satırda çalıştırır.
    def _run(self, coro):
        return asyncio.run(coro)

    # Yardım istendiğinde bildirim aksiyonlarının üretildiğini doğrular.
    def test_not_ok_creates_notify_actions(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        self._run(svc.evaluate_assistant_state(
            repos=repos, user_id="u1", final_risk_score=0.9, severity="critical"
        ))
        result = self._run(svc.handle_user_ack(repos=repos, user_id="u1", response="not_ok"))
        assert result["success"] is True
        types = [a["action_type"] for a in result["actions_created"]]
        assert "notify_relative" in types
        assert "notify_doctor" in types


class TestHandleAckFalseAlarm(unittest.TestCase):
    # Asenkron test çağrılarını tek satırda çalıştırır.
    def _run(self, coro):
        return asyncio.run(coro)

    # Yanlış alarm yanıtında daha düşük moda inildiğini doğrular.
    def test_false_alarm_returns_lower_mode(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        self._run(svc.evaluate_assistant_state(
            repos=repos, user_id="u1", final_risk_score=0.9, severity="critical"
        ))
        result = self._run(svc.handle_user_ack(repos=repos, user_id="u1", response="false_alarm"))
        assert result["success"] is True
        assert result["new_mode"] in (MODE_WATCH, MODE_NORMAL)


class TestCriticalTimeout(unittest.TestCase):
    # Asenkron test çağrılarını tek satırda çalıştırır.
    def _run(self, coro):
        return asyncio.run(coro)

    # Süresi dolan kritik onayın bildirim aksiyonları başlattığını doğrular.
    def test_timeout_creates_notify_actions(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        asyncio.run(repos.assistant.update_state("u1", {
            "current_mode": MODE_CRITICAL,
            "awaiting_user_ack": True,
            "ack_deadline_at": datetime.utcnow() - timedelta(seconds=10),
            "last_risk_score": 0.9,
        }))
        result = self._run(svc.handle_critical_timeout(repos=repos, user_id="u1"))
        assert result["triggered"] is True
        types = [a["action_type"] for a in result["actions_created"]]
        assert "notify_relative" in types
        assert "notify_doctor" in types

    # Timeout işlendiğinde onay bekleme bayrağının kapandığını doğrular.
    def test_timeout_clears_ack_flag(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        asyncio.run(repos.assistant.update_state("u1", {
            "current_mode": MODE_CRITICAL,
            "awaiting_user_ack": True,
            "ack_deadline_at": datetime.utcnow() - timedelta(seconds=5),
        }))
        asyncio.run(svc.handle_critical_timeout(repos=repos, user_id="u1"))
        state = asyncio.run(repos.assistant.get_or_create_state("u1"))
        assert state["awaiting_user_ack"] is False


class TestAssistantSummary(unittest.TestCase):
    # Özet yanıtında beklenen tüm alanların yer aldığını doğrular.
    def test_summary_shape(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        summary = asyncio.run(svc.get_current_assistant_summary(repos, "u1"))
        required_keys = [
            "user_id", "current_mode", "monitoring_intensity",
            "recommended_poll_interval_sec", "awaiting_user_ack",
            "last_risk_score", "active_action_count",
            "should_sound_alarm", "guidance_messages",
        ]
        for key in required_keys:
            assert key in summary, f"Missing key: {key}"


class TestRiskScoreInvariance(unittest.TestCase):
    # Servisin aldığı risk skorunu değiştirmeden sakladığını doğrular.
    def test_risk_score_not_modified(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        original = 0.75
        asyncio.run(svc.evaluate_assistant_state(
            repos=repos, user_id="u1", final_risk_score=original, severity="warning"
        ))
        state = asyncio.run(repos.assistant.get_or_create_state("u1"))
        assert state["last_risk_score"] == original


class TestInMemoryRepo(unittest.TestCase):
    # Yeni kullanıcı için varsayılan durum kaydı oluşturulduğunu doğrular.
    def test_get_or_create_state(self):
        repo = InMemoryAssistantRepo()
        state = asyncio.run(repo.get_or_create_state("u1"))
        assert state["user_id"] == "u1"
        assert state["current_mode"] == "normal"

    # Durum güncellemesinin bellek kaydına işlendiğini doğrular.
    def test_update_state(self):
        repo = InMemoryAssistantRepo()
        asyncio.run(repo.get_or_create_state("u1"))
        updated = asyncio.run(repo.update_state("u1", {"current_mode": "watch"}))
        assert updated["current_mode"] == "watch"

    # Oluşturulan aksiyonun aktif listede göründüğünü doğrular.
    def test_create_and_list_actions(self):
        repo = InMemoryAssistantRepo()
        asyncio.run(repo.create_action({
            "id": "act1", "user_id": "u1", "state_id": None,
            "mode": "watch", "action_type": "increase_monitoring",
            "message": "test", "priority": "medium",
            "requires_ack": False, "ack_options": None,
            "created_at": datetime.utcnow(), "expires_at": None,
            "completed_at": None, "metadata_json": None,
        }))
        actions = asyncio.run(repo.list_active_actions("u1"))
        assert len(actions) == 1
        assert actions[0]["action_type"] == "increase_monitoring"

    # Tamamlanan aksiyonun aktif listeden çıktığını doğrular.
    def test_complete_action(self):
        repo = InMemoryAssistantRepo()
        asyncio.run(repo.create_action({
            "id": "act1", "user_id": "u1", "state_id": None,
            "mode": "watch", "action_type": "increase_monitoring",
            "message": "test", "priority": "medium",
            "requires_ack": False, "ack_options": None,
            "created_at": datetime.utcnow(), "expires_at": None,
            "completed_at": None, "metadata_json": None,
        }))
        asyncio.run(repo.complete_action("act1"))
        active = asyncio.run(repo.list_active_actions("u1"))
        assert len(active) == 0


class TestFailOpen(unittest.TestCase):
    # Repository yokken evaluate çağrısının güvenli varsayılan döndürdüğünü doğrular.
    def test_evaluate_with_none_repo(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        repos.assistant = None
        result = asyncio.run(svc.evaluate_assistant_state(
            repos=repos, user_id="u1", final_risk_score=0.9, severity="critical"
        ))
        assert result["current_mode"] == MODE_NORMAL

    # Repository yokken ack çağrısının başarısız ama güvenli döndüğünü doğrular.
    def test_handle_ack_with_none_repo(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        repos.assistant = None
        result = asyncio.run(svc.handle_user_ack(repos=repos, user_id="u1", response="ok"))
        assert result["success"] is False


class TestModeTimestamps(unittest.TestCase):
    # Watch moduna girildiğinde başlangıç zamanının yazıldığını doğrular.
    def test_watch_timestamp_set_on_entry(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        asyncio.run(svc.evaluate_assistant_state(
            repos=repos, user_id="u1", final_risk_score=0.35, severity="watch"
        ))
        state = asyncio.run(repos.assistant.get_or_create_state("u1"))
        assert state["watch_started_at"] is not None

    # Kritik moda girildiğinde onay son tarihinin ayarlandığını doğrular.
    def test_critical_ack_deadline_set(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        asyncio.run(svc.evaluate_assistant_state(
            repos=repos, user_id="u1", final_risk_score=0.9, severity="critical"
        ))
        state = asyncio.run(repos.assistant.get_or_create_state("u1"))
        assert state["ack_deadline_at"] is not None
        assert state["ack_deadline_at"] > datetime.utcnow()


class TestActionCreationLogic(unittest.TestCase):
    # Aynı kritik mod tekrarlandığında aksiyonların sınırsız büyümediğini doğrular.
    def test_repeated_critical_still_active(self):
        svc = CareAssistantService()
        repos = FakeRepos()
        for _ in range(3):
            asyncio.run(svc.evaluate_assistant_state(
                repos=repos, user_id="u1", final_risk_score=0.9, severity="critical"
            ))
        actions = asyncio.run(repos.assistant.list_active_actions("u1"))
        assert len(actions) <= 20


# Test dosyası doğrudan çalıştırılırsa unittest ana döngüsünü başlatır.
if __name__ == "__main__":
    unittest.main()
