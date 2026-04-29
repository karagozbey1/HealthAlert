"""
Tests for the LLM-powered chat assistant — Module 14.
Validates:
  - LLM client (configured/unconfigured, health check)
  - Context builder (all roles, empty data, demo mode)
  - System prompt templates (safety rules, role isolation)
  - Chat service (session management, LLM call, fallback)
  - Suggestions per role
  - UI action suggestions
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_chat.db")

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════
# 1. LLM Client Tests
# ═══════════════════════════════════════════════════════════════════════

class TestLLMClient:
    """Tests for services.llm_client.LLMClient."""

    def test_unconfigured_client(self):
        from services.llm_client import LLMClient
        client = LLMClient(api_key="", base_url="http://localhost", model="test")
        assert client.is_configured is False

    def test_configured_client(self):
        from services.llm_client import LLMClient
        client = LLMClient(api_key="sk-test-key", base_url="http://localhost", model="test")
        assert client.is_configured is True

    async def test_chat_returns_none_when_unconfigured(self):
        from services.llm_client import LLMClient
        client = LLMClient(api_key="", base_url="http://localhost", model="test")
        result = await client.chat([{"role": "user", "content": "hello"}])
        assert result is None

    async def test_health_check_unconfigured(self):
        from services.llm_client import LLMClient
        client = LLMClient(api_key="", base_url="http://localhost", model="test")
        info = await client.health_check()
        assert info["status"] == "not_configured"
        assert info["model"] == "test"


# ═══════════════════════════════════════════════════════════════════════
# 2. Context Builder Tests
# ═══════════════════════════════════════════════════════════════════════

class TestContextBuilder:
    """Tests for services.context_builder.build_chat_context."""

    def _build(self, **kwargs):
        from services.context_builder import build_chat_context
        defaults = dict(role="SELF", user_name="Test Kullanici")
        defaults.update(kwargs)
        return build_chat_context(**defaults)

    def test_basic_context_contains_role(self):
        ctx = self._build()
        assert "[ROL] SELF" in ctx

    def test_live_status_included(self):
        live = {"heart_rate": 78.0, "spo2": 97.5, "motion_score": 0.12, "risk_score": 0.05, "scenario": "normal"}
        ctx = self._build(live_status=live)
        assert "Nabiz: 78 bpm" in ctx
        assert "SpO2: %97.5" in ctx

    def test_no_live_data_message(self):
        ctx = self._build(live_status=None)
        assert "cihaz bagli degil" in ctx or "Yok" in ctx

    def test_active_alerts_shown(self):
        alerts = [
            {"severity": "critical", "title": "Yuksek Nabiz", "status": "active"},
            {"severity": "warning", "title": "SpO2 Dusuk", "status": "active"},
        ]
        ctx = self._build(recent_alerts=alerts)
        assert "Yuksek Nabiz" in ctx
        assert "[AKTIF ALARMLAR]" in ctx

    def test_resolved_alerts_excluded(self):
        alerts = [
            {"severity": "warning", "title": "Eski Alarm", "status": "resolved"},
        ]
        ctx = self._build(recent_alerts=alerts)
        assert "Eski Alarm" not in ctx

    def test_demo_mode_marked(self):
        ctx = self._build(is_demo_mode=True)
        assert "DEMO" in ctx

    def test_live_mode_marked(self):
        ctx = self._build(is_demo_mode=False)
        assert "CANLI" in ctx

    def test_doctor_role_includes_clinical_notes(self):
        notes = [{"content": "Hasta takipte", "created_at": "2025-01-01"}]
        ctx = self._build(role="DOCTOR", clinical_notes=notes)
        assert "Hasta takipte" in ctx or "[KLINIK NOTLAR]" in ctx

    def test_relative_role_shows_patient_name(self):
        ctx = self._build(role="RELATIVE", patient_name="Ahmet Bey")
        assert "Ahmet Bey" in ctx

    def test_max_alerts_capped_at_5(self):
        alerts = [
            {"severity": "warning", "title": f"Alarm {i}", "status": "active"}
            for i in range(10)
        ]
        ctx = self._build(recent_alerts=alerts)
        # Should not have all 10
        for i in range(5, 10):
            assert f"Alarm {i}" not in ctx

    def test_screen_context_included(self):
        ctx = self._build(screen_context="live_monitor")
        assert "live_monitor" in ctx


# ═══════════════════════════════════════════════════════════════════════
# 3. Prompt Template Tests
# ═══════════════════════════════════════════════════════════════════════

class TestPromptTemplates:
    """Tests for services.prompt_templates."""

    def test_self_prompt_contains_safety_rules(self):
        from services.prompt_templates import get_system_prompt
        prompt = get_system_prompt("SELF")
        assert "teshis" in prompt.lower() or "Teshis" in prompt
        assert "Ilac" in prompt or "ilac" in prompt.lower()

    def test_doctor_prompt_mentions_klinik(self):
        from services.prompt_templates import get_system_prompt
        prompt = get_system_prompt("DOCTOR")
        assert "Klinik" in prompt or "klinik" in prompt.lower()

    def test_relative_prompt_mentions_yakin(self):
        from services.prompt_templates import get_system_prompt
        prompt = get_system_prompt("RELATIVE")
        assert "yakin" in prompt.lower()

    def test_unknown_role_falls_back_to_self(self):
        from services.prompt_templates import get_system_prompt
        prompt_unknown = get_system_prompt("UNKNOWN_ROLE")
        prompt_self = get_system_prompt("SELF")
        assert prompt_unknown == prompt_self

    def test_all_prompts_enforce_turkish(self):
        from services.prompt_templates import get_system_prompt
        for role in ("SELF", "RELATIVE", "DOCTOR"):
            prompt = get_system_prompt(role)
            assert "Turkce" in prompt

    def test_all_prompts_have_no_diagnosis_rule(self):
        from services.prompt_templates import get_system_prompt
        for role in ("SELF", "RELATIVE", "DOCTOR"):
            prompt = get_system_prompt(role)
            assert "teshis" in prompt.lower()

    def test_all_prompts_have_no_medication_rule(self):
        from services.prompt_templates import get_system_prompt
        for role in ("SELF", "RELATIVE", "DOCTOR"):
            prompt = get_system_prompt(role)
            assert "Ilac" in prompt or "ilac" in prompt.lower()


# ═══════════════════════════════════════════════════════════════════════
# 4. Session Management Tests
# ═══════════════════════════════════════════════════════════════════════

class TestSessionManagement:
    """Tests for chat_service.SessionStore and ChatSession."""

    def test_create_session(self):
        from services.chat_service import SessionStore
        store = SessionStore(max_size=5)
        session = store.create("user1", "user1", "SELF")
        assert session.session_id
        assert session.user_id == "user1"
        assert session.role == "SELF"

    def test_get_existing_session(self):
        from services.chat_service import SessionStore
        store = SessionStore(max_size=5)
        s1 = store.create("user1", "user1", "SELF")
        s2 = store.get(s1.session_id)
        assert s2 is not None
        assert s2.session_id == s1.session_id

    def test_get_nonexistent_returns_none(self):
        from services.chat_service import SessionStore
        store = SessionStore(max_size=5)
        assert store.get("nonexistent-id") is None

    def test_lru_eviction(self):
        from services.chat_service import SessionStore
        store = SessionStore(max_size=3)
        s1 = store.create("u1", "u1", "SELF")
        store.create("u2", "u2", "SELF")
        store.create("u3", "u3", "SELF")
        store.create("u4", "u4", "SELF")  # should evict s1
        assert store.get(s1.session_id) is None

    def test_message_cap(self):
        from services.chat_service import ChatSession, MAX_MESSAGES_PER_SESSION
        session = ChatSession(session_id="s1", user_id="u1", target_user_id="u1", role="SELF")
        for i in range(MAX_MESSAGES_PER_SESSION + 10):
            session.add_message("user", f"msg {i}")
        assert len(session.messages) == MAX_MESSAGES_PER_SESSION

    def test_conversation_for_llm(self):
        from services.chat_service import ChatSession
        session = ChatSession(session_id="s1", user_id="u1", target_user_id="u1", role="SELF")
        session.add_message("user", "Merhaba")
        session.add_message("assistant", "Hosgeldiniz")
        conv = session.conversation_for_llm()
        assert len(conv) == 2
        assert conv[0] == {"role": "user", "content": "Merhaba"}
        assert conv[1] == {"role": "assistant", "content": "Hosgeldiniz"}

    def test_get_or_create_returns_existing(self):
        from services.chat_service import SessionStore
        store = SessionStore(max_size=5)
        s1 = store.create("user1", "user1", "SELF")
        s2 = store.get_or_create(s1.session_id, "user1", "user1", "SELF")
        assert s2.session_id == s1.session_id

    def test_get_or_create_creates_new_for_different_user(self):
        from services.chat_service import SessionStore
        store = SessionStore(max_size=5)
        s1 = store.create("user1", "user1", "SELF")
        s2 = store.get_or_create(s1.session_id, "user2", "user2", "SELF")
        assert s2.session_id != s1.session_id


# ═══════════════════════════════════════════════════════════════════════
# 5. Chat Service (Fallback) Tests
# ═══════════════════════════════════════════════════════════════════════

class TestChatServiceFallback:
    """Tests for the rule-based fallback in chat_service."""

    async def test_fallback_when_llm_unconfigured(self):
        from services.llm_client import LLMClient
        from services.chat_service import process_chat_message
        fake_llm = LLMClient(api_key="", base_url="http://localhost", model="test")
        result = await process_chat_message(
            message="Durumumu ozetle",
            session_id=None,
            user_id="test-user",
            target_user_id="test-user",
            role="SELF",
            llm=fake_llm,
        )
        assert result["source"] == "rule_based"
        assert result["session_id"]
        assert result["disclaimer"]

    async def test_fallback_includes_disclaimer(self):
        from services.llm_client import LLMClient
        from services.chat_service import process_chat_message
        fake_llm = LLMClient(api_key="", base_url="http://localhost", model="test")
        result = await process_chat_message(
            message="Ne yapmaliyim?",
            session_id=None,
            user_id="test-user",
            target_user_id="test-user",
            role="SELF",
            llm=fake_llm,
        )
        assert "tibbi teshis" in result["disclaimer"].lower() or "Tibbi" in result["disclaimer"]

    async def test_fallback_intent_uyari(self):
        from services.llm_client import LLMClient
        from services.chat_service import process_chat_message
        fake_llm = LLMClient(api_key="", base_url="http://localhost", model="test")
        result = await process_chat_message(
            message="Neden uyari aldim?",
            session_id=None,
            user_id="test-user",
            target_user_id="test-user",
            role="SELF",
            llm=fake_llm,
            recent_alerts=[{"severity": "warning", "title": "Test Alarm", "status": "active"}],
        )
        assert result["source"] == "rule_based"

    async def test_fallback_intent_oneri(self):
        from services.llm_client import LLMClient
        from services.chat_service import process_chat_message
        fake_llm = LLMClient(api_key="", base_url="http://localhost", model="test")
        result = await process_chat_message(
            message="Ne yapmaliyim?",
            session_id=None,
            user_id="test-user",
            target_user_id="test-user",
            role="SELF",
            llm=fake_llm,
        )
        assert result["source"] == "rule_based"

    async def test_session_reuse(self):
        from services.llm_client import LLMClient
        from services.chat_service import process_chat_message
        fake_llm = LLMClient(api_key="", base_url="http://localhost", model="test")
        r1 = await process_chat_message(
            message="Merhaba",
            session_id=None,
            user_id="session-test-user",
            target_user_id="session-test-user",
            role="SELF",
            llm=fake_llm,
        )
        sid = r1["session_id"]
        r2 = await process_chat_message(
            message="Devam et",
            session_id=sid,
            user_id="session-test-user",
            target_user_id="session-test-user",
            role="SELF",
            llm=fake_llm,
        )
        assert r2["session_id"] == sid


# ═══════════════════════════════════════════════════════════════════════
# 6. Suggestions Tests
# ═══════════════════════════════════════════════════════════════════════

class TestSuggestions:
    """Tests for get_suggestions()."""

    def test_self_suggestions(self):
        from services.chat_service import get_suggestions
        s = get_suggestions("SELF")
        assert len(s) > 0
        assert any("ozetle" in x.lower() or "durum" in x.lower() for x in s)

    def test_relative_suggestions(self):
        from services.chat_service import get_suggestions
        s = get_suggestions("RELATIVE")
        assert len(s) > 0
        assert any("yakin" in x.lower() for x in s)

    def test_doctor_suggestions(self):
        from services.chat_service import get_suggestions
        s = get_suggestions("DOCTOR")
        assert len(s) > 0
        assert any("hasta" in x.lower() for x in s)

    def test_unknown_role_returns_self(self):
        from services.chat_service import get_suggestions
        s_unknown = get_suggestions("MARTIAN")
        s_self = get_suggestions("SELF")
        assert s_unknown == s_self


# ═══════════════════════════════════════════════════════════════════════
# 7. UI Action Suggestions Tests
# ═══════════════════════════════════════════════════════════════════════

class TestUIActions:
    """Tests for _suggest_ui_actions()."""

    def test_live_monitor_suggestion(self):
        from services.chat_service import _suggest_ui_actions
        actions = _suggest_ui_actions("Canli izleme durumum nasil?", None, None)
        routes = [a.route for a in actions]
        assert "/live-monitor" in routes

    def test_history_suggestion(self):
        from services.chat_service import _suggest_ui_actions
        actions = _suggest_ui_actions("Son 24 saat gecmisimi goster", None, None)
        routes = [a.route for a in actions]
        assert "/history" in routes

    def test_settings_suggestion(self):
        from services.chat_service import _suggest_ui_actions
        actions = _suggest_ui_actions("Bildirim ayarlarimi degistirmek istiyorum", None, None)
        routes = [a.route for a in actions]
        assert "/settings" in routes

    def test_alarm_suggestion_with_active_alerts(self):
        from services.chat_service import _suggest_ui_actions
        alerts = [{"severity": "warning", "title": "Test", "status": "active"}]
        actions = _suggest_ui_actions("Son alarmlarim nedir?", None, alerts)
        routes = [a.route for a in actions]
        assert "/alerts" in routes

    def test_no_alarm_route_without_active_alerts(self):
        from services.chat_service import _suggest_ui_actions
        alerts = [{"severity": "warning", "title": "Test", "status": "resolved"}]
        actions = _suggest_ui_actions("Son alarmlarim nedir?", None, alerts)
        routes = [a.route for a in actions]
        assert "/alerts" not in routes

    def test_max_3_actions(self):
        from services.chat_service import _suggest_ui_actions
        # message that triggers many keywords
        actions = _suggest_ui_actions(
            "canli izleme gecmis ayar bildirim alarm uyari",
            None,
            [{"status": "active", "title": "X", "severity": "warning"}],
        )
        assert len(actions) <= 3
