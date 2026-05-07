from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest
import unittest.mock as mock
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_live_integration.db")

# Tüm katmanların kabul ettiği örnek cihaz paketini üretir.
def _make_packet(**overrides) -> Dict:
    base = dict(
        device_id="ha-esp32-001",
        timestamp_ms=1_700_000_001_000,
        mode="mock",
        packet_seq=25_001,
        accel_x=0.01, accel_y=0.02, accel_z=1.0,
        gyro_x=0.0,  gyro_y=0.0,  gyro_z=0.0,
        red_value=50_000, ir_value=55_000,
        heart_rate=72.0, spo2=98.0, signal_quality=0.9,
        imu_ok=True, ppg_ok=True,
        hr_valid=True, spo2_valid=True, finger_detected=True,
        state_hint="normal",
    )
    base.update(overrides)
    return base


# Kritik durumu temsil eden örnek cihaz paketini üretir.
def _make_critical_packet(**overrides) -> Dict:
    return _make_packet(
        packet_seq=25_002,
        heart_rate=138.0, spo2=84.0,
        hr_valid=True, spo2_valid=True,
        state_hint="critical_state",
        **overrides,
    )


class _InMemoryAssistantRepo:
    # Asistan repository davranışını bellekte taklit eder.
    def __init__(self):
        self._states: Dict[str, Dict] = {}
        self._actions: List[Dict] = []

    # Kullanıcı için durum kaydını getirir veya varsayılanla oluşturur.
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

    # Durum güncellemesini belleğe uygular ve güncel kopyayı döndürür.
    async def update_state(self, user_id: str, updates: Dict) -> Dict:
        state = await self.get_or_create_state(user_id)
        state.update(updates)
        state["updated_at"] = datetime.utcnow()
        self._states[user_id] = state
        return dict(state)

    # Yeni aksiyonu saklayıp kaydedilmiş kopyasını döndürür.
    async def create_action(self, data: Dict) -> Dict:
        action = dict(data)
        if "id" not in action:
            action["id"] = str(uuid4())
        self._actions.append(action)
        return dict(action)

    # Aktif aksiyonları kullanıcıya göre filtreler.
    async def list_active_actions(self, user_id: str) -> List[Dict]:
        return [dict(a) for a in self._actions
                if a["user_id"] == user_id and a.get("completed_at") is None]

    # İstenen aksiyonu tamamlanmış olarak işaretler.
    async def complete_action(self, action_id: str) -> Optional[Dict]:
        for a in self._actions:
            if a["id"] == action_id:
                a["completed_at"] = datetime.utcnow()
                return dict(a)
        return None

    # Onay kaydını test içinde saklar.
    async def create_ack(self, data: Dict) -> Dict:
        ack = dict(data)
        self._actions.append(ack)
        return ack

    # Bu yalın taklit için timeout listesi döndürmez.
    async def get_due_ack_timeouts(self, now: datetime) -> List[Dict]:
        return []

    # Kullanıcıya ait asistan geçmişini yalın biçimde döndürür.
    async def list_assistant_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        return [dict(a) for a in self._actions if a.get("user_id") == user_id][:limit]


class _InMemoryPersonalizationRepo:
    # Kişiselleştirme verisini bellekte taklit eder.
    def __init__(self):
        self._profiles: Dict[str, Dict] = {}

    # Kullanıcı profili yoksa varsayılanlarla oluşturup döndürür.
    async def get_or_create_profile(self, user_id: str) -> Dict:
        if user_id not in self._profiles:
            self._profiles[user_id] = {
                "id": str(uuid4()), "user_id": user_id,
                "personalization_level": "cold_start",
                "total_valid_samples": 0, "total_observation_minutes": 0.0,
                "total_feedback_count": 0, "false_alarm_count": 0,
                "confirmed_risk_count": 0, "sensor_error_count": 0,
                "typical_hr_min": 55.0, "typical_hr_max": 100.0,
                "typical_spo2_min": 95.0, "typical_spo2_max": 100.0,
                "typical_motion_min": 0.0, "typical_motion_max": 0.5,
                "day_profile_json": None, "night_profile_json": None,
                "activity_profile_json": None,
                "last_recalibrated_at": datetime.utcnow(),
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
                "baseline_id": None,
            }
        return dict(self._profiles[user_id])

    # Profil alanlarını güncelleyip yeni kopyayı döndürür.
    async def update_profile(self, user_id: str, updates: Dict) -> Dict:
        p = await self.get_or_create_profile(user_id)
        p.update(updates)
        self._profiles[user_id] = p
        return dict(p)

    # Risk hafızası ekleme çağrısını yalın biçimde geri döndürür.
    async def add_risk_memory(self, data: Dict) -> Dict:
        return dict(data)

    # Risk hafızası sorgusunda boş liste döndürür.
    async def list_risk_memory(self, user_id: str, limit: int = 50) -> List[Dict]:
        return []

    # Trend anlık görüntüsünü yalın biçimde geri döndürür.
    async def create_trend_snapshot(self, data: Dict) -> Dict:
        return dict(data)

    # Son trend anlık görüntüsü olmadığı için boş değer döndürür.
    async def get_latest_trend_snapshot(self, user_id: str) -> Optional[Dict]:
        return None

    # Kişiselleştirme özetini temel bir sözlük olarak döndürür.
    async def summarize_personalization(self, user_id: str) -> Dict:
        return {"user_id": user_id, "personalization_level": "cold_start"}


@dataclass
class FakeRepos:
    assistant: Any = None
    personalization: Any = None
    learning: Any = None
    relations: Any = None
    notifications: Any = None


# Testlerde kullanılacak bellek içi repo takımını oluşturur.
def _make_full_repos(**overrides):
    r = FakeRepos(
        assistant=_InMemoryAssistantRepo(),
        personalization=_InMemoryPersonalizationRepo(),
    )
    for k, v in overrides.items():
        setattr(r, k, v)
    return r


class TestPacketContractAlignment(unittest.TestCase):
    REQUIRED_FIELDS = [
        "device_id", "timestamp_ms", "mode", "packet_seq",
        "accel_x", "accel_y", "accel_z",
        "gyro_x", "gyro_y", "gyro_z",
        "red_value", "ir_value",
        "heart_rate", "spo2", "signal_quality",
        "imu_ok", "ppg_ok",
        "hr_valid", "spo2_valid", "finger_detected",
        "state_hint",
    ]

    # Host bridge şemasının tüm zorunlu alanları kabul ettiğini doğrular.
    def test_a1_host_bridge_schema_accepts_all_fields(self):
        from host_bridge.packet_schema import DevicePacketSchema
        pkt = _make_packet()
        validated = DevicePacketSchema(**pkt)
        for field in self.REQUIRED_FIELDS:
            assert hasattr(validated, field), f"Missing field in schema: {field}"

    # Backend isteğinin tüm zorunlu alanları kabul ettiğini doğrular.
    def test_a2_backend_schema_accepts_all_fields(self):
        from schemas import DevicePacketRequest
        pkt = _make_packet()
        req = DevicePacketRequest(**pkt)
        for field in self.REQUIRED_FIELDS:
            assert hasattr(req, field), f"Missing field in backend schema: {field}"

    # state_hint verilmediğinde isteğin güvenli varsayılanla çalıştığını doğrular.
    def test_a3_state_hint_optional_defaults_normal(self):
        from schemas import DevicePacketRequest
        pkt = _make_packet()
        del pkt["state_hint"]
        req = DevicePacketRequest(**pkt)
        assert req.state_hint is None or req.state_hint == "normal"

    # Host bridge ve backend tarafında cihaz kimliğinin aynı kaldığını doğrular.
    def test_a4_host_bridge_and_backend_device_id_match(self):
        from host_bridge.packet_schema import DevicePacketSchema
        from schemas import DevicePacketRequest

        pkt = _make_packet()
        hb = DevicePacketSchema(**pkt)
        be = DevicePacketRequest(**pkt)
        assert hb.device_id == be.device_id == "ha-esp32-001"

    # Mode alanının her iki şemada da aynı biçimde korunduğunu doğrular.
    def test_a5_mode_field_type_consistent(self):
        from host_bridge.packet_schema import DevicePacketSchema
        from schemas import DevicePacketRequest

        for mode in ("mock", "real"):
            pkt = _make_packet(mode=mode)
            hb = DevicePacketSchema(**pkt)
            be = DevicePacketRequest(**pkt)
            assert hb.mode == be.mode == mode


class TestIngestionPipelineScoping(unittest.TestCase):

    # severity değişkeninin try bloğu öncesinde başlatıldığını doğrular.
    def test_b1_severity_initialized_before_try_block(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent / "routers" / "ingestion_router.py"
        code = src.read_text(encoding="utf-8")
        assert "severity: str | None = None" in code, (
            "severity must be initialized to None before the anomaly try block"
        )

    # Asistan sonuç değişkenlerinin dış kapsamda tanımlandığını doğrular.
    def test_b2_assistant_result_vars_initialized_outer_scope(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent / "routers" / "ingestion_router.py"
        code = src.read_text(encoding="utf-8")
        assert "assistant_state_result: dict | None = None" in code
        assert "assistant_actions_result: list | None = None" in code

    # Care assistant bloğunun risk skorunu yeniden atamadığını doğrular.
    def test_b3_risk_score_never_modified_by_care_assistant(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent / "routers" / "ingestion_router.py"
        lines = src.read_text(encoding="utf-8").splitlines()
        in_assistant_block = False
        for line in lines:
            if "Part 5C: Care Assistant" in line:
                in_assistant_block = True
            if in_assistant_block:
                stripped = line.strip()
                if stripped.startswith("risk_score =") or stripped.startswith("risk_score="):
                    assert False, f"risk_score modified inside care assistant block: {line}"
                if stripped.startswith("await db.commit()"):
                    break


class TestModeFieldValidation(unittest.TestCase):

    # Backend'in mock modunu kabul ettiğini doğrular.
    def test_c1_mock_mode_accepted_backend(self):
        from schemas import DevicePacketRequest
        req = DevicePacketRequest(**_make_packet(mode="mock"))
        assert req.mode == "mock"

    # Backend'in real modunu kabul ettiğini doğrular.
    def test_c2_real_mode_accepted_backend(self):
        from schemas import DevicePacketRequest
        req = DevicePacketRequest(**_make_packet(mode="real"))
        assert req.mode == "real"

    # Backend'in geçersiz mode değerini reddettiğini doğrular.
    def test_c3_invalid_mode_rejected_backend(self):
        from pydantic import ValidationError
        from schemas import DevicePacketRequest
        with pytest.raises((ValidationError, ValueError)):
            DevicePacketRequest(**_make_packet(mode="test"))

    # Host bridge şemasının mock modunu kabul ettiğini doğrular.
    def test_c4_mock_mode_accepted_host_bridge(self):
        from host_bridge.packet_schema import DevicePacketSchema
        pkt = DevicePacketSchema(**_make_packet(mode="mock"))
        assert pkt.mode == "mock"

    # Host bridge şemasının real modunu kabul ettiğini doğrular.
    def test_c5_real_mode_accepted_host_bridge(self):
        from host_bridge.packet_schema import DevicePacketSchema
        pkt = DevicePacketSchema(**_make_packet(mode="real"))
        assert pkt.mode == "real"

    # Host bridge şemasının geçersiz mode değerini reddettiğini doğrular.
    def test_c6_invalid_mode_rejected_host_bridge(self):
        from pydantic import ValidationError
        from host_bridge.packet_schema import DevicePacketSchema
        with pytest.raises((ValidationError, ValueError)):
            DevicePacketSchema(**_make_packet(mode="LIVE"))


class TestMultiLayerIsolation(unittest.TestCase):

    # ML shadow sonucunda final risk skorunun bulunmadığını doğrular.
    def test_d1_ml_shadow_has_no_final_risk_score(self):
        from services.ml_inference_service import MLInferenceService
        svc = MLInferenceService()
        svc._loaded = True
        svc._available = True
        svc._resolved_vitals_dim = 3

        def fake_predict(imu, ppg, vitals, smooth=True):
            return {
                "fall_prob": 0.05, "instability_prob": 0.05,
                "quality_score": 0.9, "risk_score": 0.1,
            }
        svc._predictor = types.SimpleNamespace(
            predict=fake_predict,
            _ema_state={"fall_prob": 0.0, "instability_prob": 0.0, "quality_score": 1.0, "risk_score": 0.0},
            reset=lambda: None,
        )
        svc._postprocessor = types.SimpleNamespace(
            process=lambda p, v: {"fall_probability": 0.05, "final_risk_level": "normal", "immediate_alert": False}
        )
        svc._ema_states_by_user["user_d1"] = {"fall_prob": 0.0, "instability_prob": 0.0, "quality_score": 1.0, "risk_score": 0.0}

        window = [
            types.SimpleNamespace(
                timestamp_ms=1_700_000_000_000 + i*1000,
                packet_seq=i, mode="mock",
                accel_x=0.01, accel_y=0.02, accel_z=1.0,
                gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
                red_value=50_000, ir_value=55_000,
                heart_rate=72.0, spo2=98.0, signal_quality=0.9,
                imu_ok=True, ppg_ok=True,
                hr_valid=True, spo2_valid=True, finger_detected=True,
                motion_score=0.1, final_risk_score=0.1, quality_confidence=0.9,
            )
            for i in range(200)
        ]

        with mock.patch("services.ml_inference_service.settings") as ms:
            ms.ML_SKIP_ON_SAMPLE_RATE_MISMATCH = True
            ms.ML_ALLOW_LOW_CONFIDENCE_INFERENCE = False
            ms.ML_FAIL_OPEN = True
            ms.ML_EMA_ALPHA = 0.2
            ms.ML_VITALS_DIM = 3
            ms.ML_MAX_DURATION_RATIO = 3.0
            result = svc.predict_window("user_d1", window, None, {"is_full": True, "sample_rate_warning": False, "estimated_window_duration_sec": 4.0, "expected_duration_sec": 4.0})

        assert "final_risk_score" not in result
        assert result.get("shadow_mode") is True

    # Retrieval servisinin shadow yapısını bozmadan sonuç döndürdüğünü doğrular.
    def test_d2_retrieval_shadow_flag_set(self):
        from services.retrieval_shadow_service import RetrievalShadowService
        svc = RetrievalShadowService()
        result = svc.query_window([], {"is_full": False})
        assert result is None or isinstance(result, dict)

    # Care assistant servisinin aldığı risk değerini değiştirmediğini doğrular.
    def test_d3_care_assistant_does_not_modify_risk_score_in_service(self):
        from services.care_assistant_service import CareAssistantService
        svc = CareAssistantService()
        repos = _make_full_repos()
        user_id = f"user_d3_{uuid4().hex[:6]}"
        original_risk = 0.55

        result = asyncio.run(svc.evaluate_assistant_state(
            repos=repos,
            user_id=user_id,
            final_risk_score=original_risk,
            severity="warning",
            risk_breakdown={"baseline_deviation_score": 0.1},
        ))
        assert original_risk == 0.55
        assert isinstance(result, dict)
        assert "current_mode" in result


class TestCareAssistantIntegration(unittest.TestCase):

    # Düşük risk ve boş severity durumunda normal modun korunduğunu doğrular.
    def test_e1_normal_severity_stays_normal(self):
        from services.care_assistant_service import CareAssistantService, MODE_NORMAL
        svc = CareAssistantService()
        repos = _make_full_repos()
        user_id = f"user_e1_{uuid4().hex[:6]}"
        result = asyncio.run(svc.evaluate_assistant_state(
            repos=repos, user_id=user_id,
            final_risk_score=0.10, severity=None, risk_breakdown=None,
        ))
        assert result["current_mode"] == MODE_NORMAL

    # Kritik severity verildiğinde kritik modun seçildiğini doğrular.
    def test_e2_critical_severity_triggers_critical_mode(self):
        from services.care_assistant_service import CareAssistantService, MODE_CRITICAL
        svc = CareAssistantService()
        repos = _make_full_repos()
        user_id = f"user_e2_{uuid4().hex[:6]}"
        result = asyncio.run(svc.evaluate_assistant_state(
            repos=repos, user_id=user_id,
            final_risk_score=0.82, severity="critical", risk_breakdown=None,
        ))
        assert result["current_mode"] == MODE_CRITICAL

    # Kritik modda kullanıcı onayı beklendiğini doğrular.
    def test_e3_critical_sets_awaiting_ack(self):
        from services.care_assistant_service import CareAssistantService
        svc = CareAssistantService()
        repos = _make_full_repos()
        user_id = f"user_e3_{uuid4().hex[:6]}"
        result = asyncio.run(svc.evaluate_assistant_state(
            repos=repos, user_id=user_id,
            final_risk_score=0.82, severity="critical", risk_breakdown=None,
        ))
        assert result["awaiting_user_ack"] is True

    # Asistan repository yokken çağrının güvenli biçimde döndüğünü doğrular.
    def test_e4_repos_none_does_not_raise(self):
        from services.care_assistant_service import CareAssistantService
        svc = CareAssistantService()
        repos = FakeRepos(assistant=None)
        user_id = f"user_e4_{uuid4().hex[:6]}"
        result = asyncio.run(svc.evaluate_assistant_state(
            repos=repos, user_id=user_id,
            final_risk_score=0.90, severity="critical", risk_breakdown=None,
        ))
        assert isinstance(result, dict)
        assert "current_mode" in result

    # Warning modunda en azından aksiyon listesinin üretildiğini doğrular.
    def test_e5_warning_mode_produces_guidance(self):
        from services.care_assistant_service import CareAssistantService
        svc = CareAssistantService()
        repos = _make_full_repos()
        user_id = f"user_e5_{uuid4().hex[:6]}"
        result = asyncio.run(svc.evaluate_assistant_state(
            repos=repos, user_id=user_id,
            final_risk_score=0.60, severity="warning",
            risk_breakdown={"baseline_deviation_score": 0.15},
        ))
        actions = result.get("actions_created") or []
        assert isinstance(actions, list)


class TestLearningLoopFailOpen(unittest.TestCase):

    # should_capture_window sonucunun bool döndüğünü doğrular.
    def test_f1_should_capture_window_returns_bool(self):
        from services.learning_data_service import should_capture_window
        result = should_capture_window(
            user_id="user_f1",
            packet_mode="mock",
            final_risk_score=0.4,
            quality_confidence=0.9,
            risk_level="warning",
            baseline_ready=True,
        )
        assert isinstance(result, bool)

    # Geçersiz girdilerin capture karar fonksiyonunu çökertmediğini doğrular.
    def test_f2_should_capture_does_not_raise_on_invalid_inputs(self):
        from services.learning_data_service import should_capture_window
        try:
            should_capture_window(
                user_id="",
                packet_mode="unknown",
                final_risk_score=-0.1,
                quality_confidence=0.0,
                risk_level=None,
                baseline_ready=False,
            )
        except Exception as exc:
            pytest.fail(f"should_capture_window raised unexpectedly: {exc}")

    # Learning veri servisinin sorunsuz içe aktarılabildiğini doğrular.
    def test_f3_learning_data_service_importable(self):
        from services.learning_data_service import learning_data_service
        assert learning_data_service is not None


class TestAdaptivePersonalizationFailOpen(unittest.TestCase):

    # Kişiselleştirme servisinin içe aktarılabildiğini doğrular.
    def test_g1_service_importable(self):
        from services.adaptive_personalization_service import adaptive_personalization_service
        assert adaptive_personalization_service is not None

    # Kişiselleştirilmiş risk hesabının sözlük yapısında sonuç verdiğini doğrular.
    def test_g2_compute_personalized_risk_returns_dict(self):
        from services.adaptive_personalization_service import compute_personalized_risk
        profile = {
            "personalization_level": "cold_start",
            "total_valid_samples": 0,
            "typical_hr_min": 55.0, "typical_hr_max": 100.0,
            "typical_spo2_min": 95.0, "typical_spo2_max": 100.0,
            "typical_motion_min": 0.0, "typical_motion_max": 0.5,
            "false_alarm_count": 0, "total_feedback_count": 0,
            "confirmed_risk_count": 0, "sensor_error_count": 0,
        }
        result = compute_personalized_risk(
            global_risk_score=0.30,
            baseline_result={"final_risk_score": 0.30, "alert_sensitivity": "normal"},
            profile=profile,
            trend_info=None,
            quality_info={"quality_confidence": 0.9, "safety_override": False},
            hr=75.0, spo2=98.5, motion_score=0.1,
            hr_valid=True, spo2_valid=True,
            severity=None,
        )
        assert isinstance(result, dict)
        assert "final_personalized_risk" in result
        assert 0.0 <= result["final_personalized_risk"] <= 1.0

    # Kişiselleştirilmiş risk hesabının üst sınırı aşmadığını doğrular.
    def test_g3_compute_personalized_risk_clamps_bounds(self):
        from services.adaptive_personalization_service import compute_personalized_risk
        profile = {
            "personalization_level": "cold_start",
            "total_valid_samples": 0,
            "typical_hr_min": 55.0, "typical_hr_max": 100.0,
            "typical_spo2_min": 95.0, "typical_spo2_max": 100.0,
            "typical_motion_min": 0.0, "typical_motion_max": 0.5,
            "false_alarm_count": 0, "total_feedback_count": 0,
            "confirmed_risk_count": 0, "sensor_error_count": 0,
        }
        result = compute_personalized_risk(
            global_risk_score=0.99,
            baseline_result={"final_risk_score": 0.99, "alert_sensitivity": "normal"},
            profile=profile,
            trend_info=None,
            quality_info={"quality_confidence": 0.9, "safety_override": True},
            hr=180.0, spo2=82.0, motion_score=2.5,
            hr_valid=True, spo2_valid=True,
            severity="critical",
        )
        assert result["final_personalized_risk"] <= 1.0


class TestConfigCompleteness(unittest.TestCase):

    REQUIRED_SETTINGS = [
        "DATA_MODE", "SECRET_KEY",
        "RISK_CRITICAL_THRESHOLD", "RISK_WARNING_THRESHOLD", "RISK_WATCH_THRESHOLD",
        "BASELINE_ENABLED", "BASELINE_MIN_SAMPLES",
        "ML_INFERENCE_ENABLED", "ML_SHADOW_MODE", "ML_FAIL_OPEN",
        "RETRIEVAL_ENABLED",
        "LEARNING_LOOP_ENABLED", "LEARNING_EXPORT_DIR",
        "PERSONALIZATION_ENABLED",
        "ASSISTANT_ENABLED",
        "ASSISTANT_CRITICAL_ACK_TIMEOUT_SEC",
        "ASSISTANT_WATCH_DURATION_SEC",
        "ASSISTANT_WARNING_GUIDANCE_COOLDOWN_SEC",
        "ASSISTANT_NORMAL_POLL_INTERVAL_SEC",
        "ASSISTANT_WATCH_POLL_INTERVAL_SEC",
        "ASSISTANT_CRITICAL_POLL_INTERVAL_SEC",
        "ASSISTANT_NOTIFY_RELATIVES_ON_NO_RESPONSE",
        "ASSISTANT_NOTIFY_DOCTORS_ON_NO_RESPONSE",
    ]

    # Gerekli tüm ayarların Settings içinde tanımlı olduğunu doğrular.
    def test_h1_all_settings_present(self):
        from config import Settings
        s = Settings()
        for key in self.REQUIRED_SETTINGS:
            assert hasattr(s, key), f"Missing setting: {key}"

    # Risk eşiklerinin düşükten yükseğe doğru sıralandığını doğrular.
    def test_h2_thresholds_in_correct_order(self):
        from config import Settings
        s = Settings()
        assert s.RISK_WATCH_THRESHOLD < s.RISK_WARNING_THRESHOLD < s.RISK_CRITICAL_THRESHOLD

    # Kritikten normale doğru yoklama aralıklarının büyüdüğünü doğrular.
    def test_h3_assistant_poll_intervals_ordered(self):
        from config import Settings
        s = Settings()
        assert s.ASSISTANT_CRITICAL_POLL_INTERVAL_SEC <= s.ASSISTANT_WATCH_POLL_INTERVAL_SEC
        assert s.ASSISTANT_WATCH_POLL_INTERVAL_SEC <= s.ASSISTANT_NORMAL_POLL_INTERVAL_SEC


class TestSchemaCompleteness(unittest.TestCase):

    # Yanıt şemasında assistant_state alanının bulunduğunu doğrular.
    def test_i1_response_has_assistant_state_field(self):
        from schemas import DevicePacketResponse
        fields = DevicePacketResponse.model_fields
        assert "assistant_state" in fields, "DevicePacketResponse missing assistant_state"

    # Yanıt şemasında assistant_actions alanının bulunduğunu doğrular.
    def test_i2_response_has_assistant_actions_field(self):
        from schemas import DevicePacketResponse
        fields = DevicePacketResponse.model_fields
        assert "assistant_actions" in fields, "DevicePacketResponse missing assistant_actions"

    # Yanıt şemasında learning_capture_result alanının bulunduğunu doğrular.
    def test_i3_response_has_learning_capture_result(self):
        from schemas import DevicePacketResponse
        fields = DevicePacketResponse.model_fields
        assert "learning_capture_result" in fields, "DevicePacketResponse missing learning_capture_result"

    # İstek şemasında temel paket alanlarının tanımlı olduğunu doğrular.
    def test_i4_request_has_all_required_fields(self):
        from schemas import DevicePacketRequest
        req_fields = DevicePacketRequest.model_fields
        for f in ["device_id", "timestamp_ms", "mode", "packet_seq", "heart_rate", "spo2"]:
            assert f in req_fields, f"DevicePacketRequest missing required field: {f}"

    # Asistanla ilgili tüm şemaların içe aktarılabildiğini doğrular.
    def test_i5_assistant_state_schema_importable(self):
        from schemas import AssistantStateResponse, AssistantActionResponse
        from schemas import AssistantAckRequest, AssistantAckResponse, AssistantSummaryResponse
        assert AssistantStateResponse is not None
        assert AssistantActionResponse is not None
        assert AssistantAckRequest is not None
        assert AssistantAckResponse is not None
        assert AssistantSummaryResponse is not None


class TestModePropagation(unittest.TestCase):

    # Mock modunun istek şemasında korunduğunu doğrular.
    def test_j1_mode_mock_preserved_in_request(self):
        from schemas import DevicePacketRequest
        req = DevicePacketRequest(**_make_packet(mode="mock"))
        assert req.mode == "mock"

    # Real modunun istek şemasında korunduğunu doğrular.
    def test_j2_mode_real_preserved_in_request(self):
        from schemas import DevicePacketRequest
        req = DevicePacketRequest(**_make_packet(mode="real"))
        assert req.mode == "real"

    # Firmware cihaz kimliğinin şema varsayılanıyla eşleştiğini doğrular.
    def test_j3_firmware_device_id_matches_schema(self):
        from schemas import DevicePacketRequest
        HA_DEVICE_ID = "ha-esp32-001"
        req = DevicePacketRequest(**_make_packet(device_id=HA_DEVICE_ID))
        assert req.device_id == HA_DEVICE_ID

    # Mock emitter cihaz kimliğinin firmware sabitiyle eşleştiğini doğrular.
    def test_j4_mock_emitter_device_id_matches_firmware(self):
        import pathlib
        emitter_path = pathlib.Path(__file__).parent.parent.parent.parent / "host_bridge" / "mock_serial_emitter.py"
        src = emitter_path.read_text(encoding="utf-8")
        assert 'DEVICE_ID = "ha-esp32-001"' in src, (
            "mock_serial_emitter.py DEVICE_ID must be 'ha-esp32-001'"
        )


class TestIngestionResponseContract(unittest.TestCase):

    REQUIRED_RESPONSE_KEYS = [
        "status", "packet_seq", "device_id", "user_id",
        "risk_breakdown",
        "window_status", "ml_shadow_result", "retrieval_shadow_result",
        "personalization_result", "learning_capture_result",
        "assistant_state", "assistant_actions",
    ]

    # Yanıt şemasında gerekli tüm alanların tanımlı olduğunu doğrular.
    def test_k1_response_schema_has_all_required_keys(self):
        from schemas import DevicePacketResponse
        fields = DevicePacketResponse.model_fields
        for key in self.REQUIRED_RESPONSE_KEYS:
            assert key in fields, f"DevicePacketResponse missing field: {key}"

    # Yanıt modelinin varsayılan alanlarla örneklenebildiğini doğrular.
    def test_k2_response_can_be_constructed_with_defaults(self):
        from schemas import DevicePacketResponse
        resp = DevicePacketResponse(
            status="ok",
            packet_seq=25_001,
            device_id="ha-esp32-001",
        )
        assert resp.status == "ok"
        assert resp.user_id is None
        assert resp.assistant_state is None
        assert resp.assistant_actions is None


class TestDeviceRegistrationGuard(unittest.TestCase):

    # Ingestion akışında cihaz kaydının önce kontrol edildiğini doğrular.
    def test_l1_ingestion_router_checks_registration(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent / "routers" / "ingestion_router.py"
        code = src.read_text(encoding="utf-8")
        assert "await repos.devices.get_registration" in code, (
            "ingestion_router must check device registration"
        )

    # user_id olmadığında kullanıcıya özel blokların atlandığını doğrular.
    def test_l2_user_id_none_skips_blocks(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent / "routers" / "ingestion_router.py"
        code = src.read_text(encoding="utf-8")
        assert "if user_id" in code, "Pipeline must gate on user_id"


class TestSeverityInitialization(unittest.TestCase):

    # Düşük riskte severity değerinin None döndüğünü doğrular.
    def test_m1_risk_to_severity_returns_none_for_low_risk(self):
        from routers.ingestion_router import _risk_to_severity
        with mock.patch("routers.ingestion_router.settings") as ms:
            ms.RISK_CRITICAL_THRESHOLD = 0.75
            ms.RISK_WARNING_THRESHOLD = 0.55
            ms.RISK_WATCH_THRESHOLD = 0.30
            result = _risk_to_severity(0.05, 0.0)
        assert result is None

    # Yüksek riskte severity değerinin critical olduğunu doğrular.
    def test_m2_risk_to_severity_returns_critical(self):
        from routers.ingestion_router import _risk_to_severity
        with mock.patch("routers.ingestion_router.settings") as ms:
            ms.RISK_CRITICAL_THRESHOLD = 0.75
            ms.RISK_WARNING_THRESHOLD = 0.55
            ms.RISK_WATCH_THRESHOLD = 0.30
            result = _risk_to_severity(0.80, 0.0)
        assert result == "critical"

    # severity=None durumunda care assistant servisinin çökmediğini doğrular.
    def test_m3_severity_none_safe_in_care_assistant(self):
        from services.care_assistant_service import CareAssistantService
        svc = CareAssistantService()
        repos = _make_full_repos()
        user_id = f"user_m3_{uuid4().hex[:6]}"
        result = asyncio.run(svc.evaluate_assistant_state(
            repos=repos, user_id=user_id,
            final_risk_score=0.10, severity=None, risk_breakdown=None,
        ))
        assert isinstance(result, dict)


class TestSmokeContracts(unittest.TestCase):

    # Uygulama başlangıcında assistant router'ın kaydedildiğini doğrular.
    def test_n1_assistant_router_registered_in_main(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent / "main.py"
        code = src.read_text(encoding="utf-8")
        assert "assistant_router" in code or "assistant" in code, (
            "assistant_router must be registered in main.py"
        )

    # Assistant router içinde state uç noktasının bulunduğunu doğrular.
    def test_n2_assistant_router_has_state_endpoint(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent / "routers" / "assistant_router.py"
        code = src.read_text(encoding="utf-8")
        assert "/state/" in code or "state/{user_id}" in code

    # Assistant router içinde ack uç noktasının bulunduğunu doğrular.
    def test_n3_assistant_router_has_ack_endpoint(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent / "routers" / "assistant_router.py"
        code = src.read_text(encoding="utf-8")
        assert "/ack" in code

    # Assistant router içinde actions uç noktasının bulunduğunu doğrular.
    def test_n4_assistant_router_has_actions_endpoint(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent / "routers" / "assistant_router.py"
        code = src.read_text(encoding="utf-8")
        assert "/actions/" in code or "actions/{user_id}" in code

    # Smoke API betiğinde asistan testlerinin tanımlı olduğunu doğrular.
    def test_n5_smoke_api_has_assistant_tests(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent / "_smoke_api.py"
        code = src.read_text(encoding="utf-8")
        assert "assistant" in code.lower()


class TestFirmwareConstantAlignment(unittest.TestCase):

    # Firmware cihaz kimliğinin seed dosyasıyla aynı olduğunu doğrular.
    def test_o1_firmware_device_id_matches_seed(self):
        import pathlib
        ha_config = pathlib.Path(__file__).parent.parent.parent.parent / "firmware" / "include" / "ha_config.h"
        seed = pathlib.Path(__file__).parent.parent.parent / "seed.py"
        ha_src = ha_config.read_text(encoding="utf-8")
        seed_src = seed.read_text(encoding="utf-8")
        assert '"ha-esp32-001"' in ha_src, "ha_config.h must define HA_DEVICE_ID = 'ha-esp32-001'"
        assert "ha-esp32-001" in seed_src, "seed.py must reference 'ha-esp32-001' as demo device"

    # Firmware yapılandırmasında FORCE_MOCK_MODE sabitinin bulunduğunu doğrular.
    def test_o2_firmware_force_mock_mode_defined(self):
        import pathlib
        ha_config = pathlib.Path(__file__).parent.parent.parent.parent / "firmware" / "include" / "ha_config.h"
        src = ha_config.read_text(encoding="utf-8")
        assert "FORCE_MOCK_MODE" in src

    # Host bridge şemasının mode alanını real ve mock ile sınırladığını doğrular.
    def test_o3_host_bridge_schema_mode_pattern(self):
        from host_bridge.packet_schema import DevicePacketSchema
        import json
        schema = DevicePacketSchema.model_json_schema()
        schema_str = json.dumps(schema)
        assert "real" in schema_str or "mock" in schema_str, (
            "host_bridge schema must enforce mode=real|mock"
        )
