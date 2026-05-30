"""
care_assistant_service.py — Part 5C: Care Assistant Orchestrator

Sorumluluklar:
- Risk seviyesine göre uygulama modunu belirlemek (NORMAL/WATCH/WARNING/CRITICAL)
- Mode geçişlerinde uygun aksiyonlar üretmek
- CRITICAL modda "İyi misiniz?" akışını yönetmek
- Kullanıcı cevabına göre mod geçişi yapmak
- Cevap yoksa yakın/doktora bildirim göndermek
- LearningLoop ve Personalization'a feedback aktarmak

KRİTİK KISITLAR:
- final_risk_score ASLA değiştirilmez (bu servise giriş olarak gelir)
- ML/retrieval shadow sonuçları karar sürecini doğrudan etkilemez
- Tıbbi teşhis verilmez; sadece güvenli yönlendirmeler yapılır
- Tüm metodlar fail-open (hata ingestion akışını kesmez)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from config import settings

logger = logging.getLogger("healthalert.care_assistant")

# Asistan modları için sabit adlar.
MODE_NORMAL = "normal"
MODE_WATCH = "watch"
MODE_WARNING = "warning"
MODE_CRITICAL = "critical"

# Tanı veya ilaç önerisi içermeyen güvenli yönlendirme mesajlarıdır.
_WARNING_GUIDANCE = [
    "Lütfen birkaç dakika oturup dinlen.",
    "Sensörün doğru takılı olduğundan emin ol.",
    "Ani hareketlerden kaçın.",
    "Yavaş ve kontrollü nefes almayı dene.",
    "Kendini kötü hissediyorsan yakınına haber ver.",
    "Bir bardak su içmeyi düşünebilirsin.",
]

_CRITICAL_GUIDANCE = [
    "Şu an değerlerin kritik aralıkta. Lütfen hareketsiz kal.",
    "Derin ve yavaş nefes almaya çalış.",
    "Yakınını çağır veya 'Yardıma ihtiyacım var' seçeneğine bas.",
]


# ---------------------------------------------------------------------------
# Saf yardimci fonksiyonlar
# ---------------------------------------------------------------------------

# Risk skoru ve severity bilgisinden asistan modunu belirler.
def determine_mode(
    final_risk_score: float,
    severity: Optional[str],
    risk_breakdown: Optional[Dict[str, Any]] = None,
) -> str:
    if severity == "critical" or final_risk_score >= 0.80:
        return MODE_CRITICAL
    if severity == "warning" or final_risk_score >= 0.60:
        return MODE_WARNING
    if severity == "watch" or final_risk_score >= 0.30:
        return MODE_WATCH
    return MODE_NORMAL


# Guvenli yonlendirme mesajlarini severity baglamina gore dondurur.
# Bu mesajlar tani veya ilac onerisi icermez.
def safe_guidance_for_context(
    risk_breakdown: Optional[Dict[str, Any]],
    severity: Optional[str],
) -> List[str]:
    if severity == "critical":
        return list(_CRITICAL_GUIDANCE)
    if severity == "warning":
        guidance = list(_WARNING_GUIDANCE)
        if risk_breakdown:
            bs = risk_breakdown.get("baseline_deviation_score", 0.0) or 0.0
            if bs > 0.10:
                guidance.insert(0, "Değerlerinde kişisel normundan belirgin sapma var — dinlenmek faydalı olabilir.")
        return guidance
    return []


# Verilen moda gore kaydedilecek aksiyon taslaklarini uretir.
# Dondurulen nesneler kaydedilmemis dict yapilardir.
def build_actions_for_mode(
    user_id: str,
    mode: str,
    state: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """care assistant servisinde kullanılacak kayıt veya bağlamı hazırlar."""
    now = datetime.utcnow()
    actions = []

    if mode == MODE_NORMAL:
        actions.append(_make_action(
            user_id=user_id,
            mode=mode,
            state_id=state.get("id"),
            action_type="observe",
            message="Değerlerin şu an normal aralıkta görünüyor.",
            priority="low",
        ))

    elif mode == MODE_WATCH:
        actions.append(_make_action(
            user_id=user_id,
            mode=mode,
            state_id=state.get("id"),
            action_type="increase_monitoring",
            message="Değerlerinde küçük bir değişim var. Seni bir süre daha yakından takip edeceğim.",
            priority="medium",
        ))

    elif mode == MODE_WARNING:
        guidance = safe_guidance_for_context(context, "warning")
        actions.append(_make_action(
            user_id=user_id,
            mode=mode,
            state_id=state.get("id"),
            action_type="show_guidance",
            message=" ".join(guidance[:3]) if guidance else "Değerlerin yükselme eğiliminde. Lütfen dinlen.",
            priority="high",
            metadata_json={"guidance_list": guidance},
        ))

    elif mode == MODE_CRITICAL:
        actions.append(_make_action(
            user_id=user_id,
            mode=mode,
            state_id=state.get("id"),
            action_type="sound_alarm",
            message="Kritik durum algılandı!",
            priority="critical",
            requires_ack=False,
        ))
        deadline = now + timedelta(seconds=settings.ASSISTANT_CRITICAL_ACK_TIMEOUT_SEC)
        actions.append(_make_action(
            user_id=user_id,
            mode=mode,
            state_id=state.get("id"),
            action_type="ask_are_you_ok",
            message="Kritik durum algılandı. İyi misiniz?",
            priority="critical",
            requires_ack=True,
            ack_options={
                "ok": "İyiyim",
                "not_ok": "Yardıma ihtiyacım var",
                "false_alarm": "Yanlış alarm",
            },
            expires_at=deadline,
        ))

    return actions


# Tek bir aksiyon kaydi icin standart sozluk yapisini olusturur.
def _make_action(
    user_id: str,
    mode: str,
    state_id: Optional[str],
    action_type: str,
    message: str,
    priority: str = "low",
    requires_ack: bool = False,
    ack_options: Optional[Dict] = None,
    expires_at: Optional[datetime] = None,
    metadata_json: Optional[Dict] = None,
) -> Dict[str, Any]:
    return {
        "id": str(uuid4()),
        "user_id": user_id,
        "state_id": state_id,
        "mode": mode,
        "action_type": action_type,
        "message": message,
        "priority": priority,
        "requires_ack": requires_ack,
        "ack_options": ack_options,
        "created_at": datetime.utcnow(),
        "expires_at": expires_at,
        "completed_at": None,
        "metadata_json": metadata_json,
    }


# Moda gore onerilen yoklama araligini dondurur.
def _poll_interval_for_mode(mode: str) -> int:
    if mode == MODE_CRITICAL:
        return settings.ASSISTANT_CRITICAL_POLL_INTERVAL_SEC
    if mode in (MODE_WARNING, MODE_WATCH):
        return settings.ASSISTANT_WATCH_POLL_INTERVAL_SEC
    return settings.ASSISTANT_NORMAL_POLL_INTERVAL_SEC


# Moda gore izleme yogunlugunu belirler.
def _monitoring_intensity_for_mode(mode: str) -> str:
    if mode == MODE_CRITICAL:
        return "urgent"
    if mode in (MODE_WARNING, MODE_WATCH):
        return "increased"
    return "normal"


# ---------------------------------------------------------------------------
# Servis sinifi
# ---------------------------------------------------------------------------

# Asistan durumunu repository katmani uzerinden degerlendirip aksiyon uretir.
class CareAssistantService:

    # Her yeni paket sonrasi asistan modunu ve olasi aksiyonlari hesaplar.
    # Bu akis final risk skorunu asla degistirmez.
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    async def evaluate_assistant_state(
        self,
        repos,
        user_id: str,
        final_risk_score: float,
        severity: Optional[str],
        risk_breakdown: Optional[Dict[str, Any]] = None,
        personalization_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not settings.ASSISTANT_ENABLED or repos.assistant is None:
            return _default_result()

        try:
            state = await repos.assistant.get_or_create_state(user_id)
            new_mode = determine_mode(final_risk_score, severity, risk_breakdown)
            now = datetime.utcnow()
            old_mode = state.get("current_mode", MODE_NORMAL)

            state_updates: Dict[str, Any] = {
                "last_risk_score": final_risk_score,
                "last_severity": severity,
                "current_mode": new_mode,
                "monitoring_intensity": _monitoring_intensity_for_mode(new_mode),
                "recommended_poll_interval_sec": _poll_interval_for_mode(new_mode),
            }

            if new_mode != old_mode:
                state_updates["previous_mode"] = old_mode
                if new_mode == MODE_WATCH and old_mode == MODE_NORMAL:
                    state_updates["watch_started_at"] = now
                elif new_mode == MODE_WARNING:
                    state_updates["warning_started_at"] = now
                elif new_mode == MODE_CRITICAL:
                    state_updates["critical_started_at"] = now
                    state_updates["awaiting_user_ack"] = True
                    state_updates["ack_deadline_at"] = now + timedelta(
                        seconds=settings.ASSISTANT_CRITICAL_ACK_TIMEOUT_SEC
                    )

            if old_mode == MODE_CRITICAL and new_mode != MODE_CRITICAL:
                state_updates["awaiting_user_ack"] = False
                state_updates["ack_deadline_at"] = None

            if personalization_summary:
                state_updates["personalization_level"] = personalization_summary.get("personalization_level")

            updated_state = await repos.assistant.update_state(user_id, state_updates)

            actions_created = []
            should_create_actions = (
                new_mode != old_mode
                or new_mode in (MODE_CRITICAL, MODE_WARNING)
            )
            if should_create_actions:
                action_dicts = build_actions_for_mode(
                    user_id=user_id,
                    mode=new_mode,
                    state=updated_state,
                    context=risk_breakdown,
                )
                for ad in action_dicts:
                    saved = await repos.assistant.create_action(ad)
                    actions_created.append(saved)

            if actions_created:
                summary = {
                    "mode": new_mode,
                    "action_types": [a["action_type"] for a in actions_created],
                }
                await repos.assistant.update_state(user_id, {
                    "last_action_summary": summary,
                })

            return {
                "current_mode": new_mode,
                "previous_mode": old_mode,
                "monitoring_intensity": _monitoring_intensity_for_mode(new_mode),
                "recommended_poll_interval_sec": _poll_interval_for_mode(new_mode),
                "awaiting_user_ack": updated_state.get("awaiting_user_ack", False),
                "ack_deadline_at": updated_state.get("ack_deadline_at"),
                "actions_created": actions_created,
                "should_sound_alarm": new_mode == MODE_CRITICAL,
            }

        except Exception as exc:
            logger.warning("evaluate_assistant_state error for %s (ignored): %s", user_id, exc)
            return _default_result()

    # Kullanici onayina gore modu gunceller ve gerekli aksiyonlari baslatir.
    # Hata durumunda guvenli bir sonuc dondurerek akisi kesmez.
    async def handle_user_ack(
        self,
        repos,
        user_id: str,
        response: str,
        note: Optional[str] = None,
        action_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not settings.ASSISTANT_ENABLED or repos.assistant is None:
            return {"success": False, "new_mode": MODE_NORMAL, "message": "Assistant disabled.", "actions_created": []}

        try:
            state = await repos.assistant.get_or_create_state(user_id)
            now = datetime.utcnow()
            actions_created = []

            ack_data = {
                "id": str(uuid4()),
                "user_id": user_id,
                "state_id": state.get("id"),
                "action_id": action_id,
                "response": response,
                "response_source": "self",
                "note": note,
                "created_at": now,
            }
            await repos.assistant.create_ack(ack_data)

            if action_id:
                await repos.assistant.complete_action(action_id)

            if response == "ok":
                new_mode = MODE_WATCH
                state_updates = {
                    "current_mode": new_mode,
                    "previous_mode": state.get("current_mode"),
                    "awaiting_user_ack": False,
                    "ack_deadline_at": None,
                    "last_user_response": "ok",
                    "monitoring_intensity": "increased",
                    "recommended_poll_interval_sec": settings.ASSISTANT_WATCH_POLL_INTERVAL_SEC,
                    "watch_started_at": now,
                }
                await repos.assistant.update_state(user_id, state_updates)
                action = await repos.assistant.create_action(_make_action(
                    user_id=user_id, mode=new_mode, state_id=state.get("id"),
                    action_type="return_to_watch",
                    message="Tamam, seni bir süre daha yakından takip edeceğim.",
                    priority="medium",
                ))
                actions_created.append(action)

                await _record_feedback(repos, user_id, "user_ok", state.get("last_risk_score", 0.0))

                return {
                    "success": True,
                    "new_mode": new_mode,
                    "message": "Tamam, seni bir süre daha yakından takip edeceğim.",
                    "actions_created": actions_created,
                }

            elif response == "not_ok":
                new_mode = MODE_CRITICAL
                state_updates = {
                    "current_mode": new_mode,
                    "awaiting_user_ack": False,
                    "ack_deadline_at": None,
                    "last_user_response": "not_ok",
                    "monitoring_intensity": "urgent",
                    "recommended_poll_interval_sec": settings.ASSISTANT_CRITICAL_POLL_INTERVAL_SEC,
                }
                await repos.assistant.update_state(user_id, state_updates)

                for notify_type in ("notify_relative", "notify_doctor"):
                    action = await repos.assistant.create_action(_make_action(
                        user_id=user_id, mode=new_mode, state_id=state.get("id"),
                        action_type=notify_type,
                        message="Kullanıcı kritik durumda yardım istedi.",
                        priority="critical",
                    ))
                    actions_created.append(action)

                await _send_notifications(
                    repos=repos,
                    user_id=user_id,
                    trigger="not_ok",
                    message="Kullanıcı kritik durumda yardım istedi.",
                )

                await _record_feedback(repos, user_id, "user_not_ok", state.get("last_risk_score", 0.0))

                return {
                    "success": True,
                    "new_mode": new_mode,
                    "message": "Yakınlarınıza bildirim gönderildi. Yardım yolda.",
                    "actions_created": actions_created,
                }

            elif response == "false_alarm":
                last_risk = state.get("last_risk_score", 0.0)
                new_mode = MODE_WATCH if last_risk > 0.30 else MODE_NORMAL
                state_updates = {
                    "current_mode": new_mode,
                    "previous_mode": state.get("current_mode"),
                    "awaiting_user_ack": False,
                    "ack_deadline_at": None,
                    "last_user_response": "false_alarm",
                    "monitoring_intensity": _monitoring_intensity_for_mode(new_mode),
                    "recommended_poll_interval_sec": _poll_interval_for_mode(new_mode),
                }
                await repos.assistant.update_state(user_id, state_updates)

                await _record_feedback(repos, user_id, "false_alarm", state.get("last_risk_score", 0.0))

                return {
                    "success": True,
                    "new_mode": new_mode,
                    "message": "Anladım, yanlış alarm olarak kaydedildi.",
                    "actions_created": actions_created,
                }

            else:
                return {"success": False, "new_mode": state.get("current_mode", MODE_NORMAL),
                        "message": f"Unknown response: {response}", "actions_created": []}

        except Exception as exc:
            logger.warning("handle_user_ack error for %s (ignored): %s", user_id, exc)
            return {"success": False, "new_mode": MODE_NORMAL, "message": str(exc), "actions_created": []}

    # Kritik onay suresi doldugunda bildirim akislarini tetikler.
    async def handle_critical_timeout(self, repos, user_id: str) -> Dict[str, Any]:
        if not settings.ASSISTANT_ENABLED or repos.assistant is None:
            return {"triggered": False}

        try:
            state = await repos.assistant.get_or_create_state(user_id)
            if not state.get("awaiting_user_ack"):
                return {"triggered": False, "reason": "not_awaiting_ack"}

            now = datetime.utcnow()
            state_updates = {
                "awaiting_user_ack": False,
                "ack_deadline_at": None,
                "last_user_response": "no_response",
            }
            await repos.assistant.update_state(user_id, state_updates)

            actions_created = []
            for notify_type in ("notify_relative", "notify_doctor"):
                action = await repos.assistant.create_action(_make_action(
                    user_id=user_id, mode=MODE_CRITICAL, state_id=state.get("id"),
                    action_type=notify_type,
                    message="Kritik uyarı sonrası kullanıcıdan cevap alınamadı.",
                    priority="critical",
                ))
                actions_created.append(action)

            if settings.ASSISTANT_NOTIFY_RELATIVES_ON_NO_RESPONSE or settings.ASSISTANT_NOTIFY_DOCTORS_ON_NO_RESPONSE:
                await _send_notifications(
                    repos=repos,
                    user_id=user_id,
                    trigger="no_response_after_critical",
                    message="Kritik uyarı sonrası kullanıcıdan cevap alınamadı.",
                )

            await _record_feedback(repos, user_id, "no_response", state.get("last_risk_score", 0.0))

            return {
                "triggered": True,
                "user_id": user_id,
                "actions_created": actions_created,
            }

        except Exception as exc:
            logger.warning("handle_critical_timeout error for %s (ignored): %s", user_id, exc)
            return {"triggered": False, "error": str(exc)}

    # Mevcut durum ve aktif aksiyonlar icin ozet bir asistan cevabi olusturur.
    async def get_current_assistant_summary(self, repos, user_id: str) -> Dict[str, Any]:
        if repos.assistant is None:
            return _default_result()
        try:
            state = await repos.assistant.get_or_create_state(user_id)
            active_actions = await repos.assistant.list_active_actions(user_id)
            mode = state.get("current_mode", MODE_NORMAL)
            guidance = safe_guidance_for_context(None, state.get("last_severity"))
            return {
                "user_id": user_id,
                "current_mode": mode,
                "monitoring_intensity": state.get("monitoring_intensity", "normal"),
                "recommended_poll_interval_sec": state.get("recommended_poll_interval_sec", 60),
                "awaiting_user_ack": state.get("awaiting_user_ack", False),
                "ack_deadline_at": state.get("ack_deadline_at"),
                "last_risk_score": state.get("last_risk_score", 0.0),
                "last_severity": state.get("last_severity"),
                "active_action_count": len(active_actions),
                "last_user_response": state.get("last_user_response"),
                "should_sound_alarm": mode == MODE_CRITICAL and state.get("awaiting_user_ack", False),
                "guidance_messages": guidance,
            }
        except Exception as exc:
            logger.warning("get_current_assistant_summary error for %s: %s", user_id, exc)
            return _default_result()


# Geri bildirimi kisilestirme ve ogrenme katmanlarina fail-open sekilde aktarir.
async def _record_feedback(
    repos,
    user_id: str,
    event_type: str,
    risk_score: float,
) -> None:
    try:
        from uuid import uuid4 as _uuid4

        if repos.personalization is not None:
            await repos.personalization.add_risk_memory({
                "id": str(_uuid4()),
                "user_id": user_id,
                "event_type": event_type,
                "risk_score": risk_score,
                "severity": None,
                "context_json": {"source": "care_assistant_ack"},
                "created_at": datetime.utcnow(),
            })

        if repos.learning is not None:
            from models import UserFeedbackEvent
            fb_label = _event_to_feedback_label(event_type)
            if fb_label:
                fe = UserFeedbackEvent(
                    id=str(_uuid4()),
                    user_id=user_id,
                    feedback_type=fb_label,
                    note=f"care_assistant:{event_type}",
                    created_at=datetime.utcnow(),
                )
    except Exception as exc:
        logger.debug("_record_feedback error (ignored): %s", exc)


# Dahili olay turunu ogrenme geri bildirim etiketine cevirir.
def _event_to_feedback_label(event_type: str) -> Optional[str]:
    mapping = {
        "user_ok": "ok",
        "user_not_ok": "not_ok",
        "false_alarm": "false_alarm",
        "no_response": "no_response",
    }
    return mapping.get(event_type)


# Yakin ve doktor bildirimlerini uygun baslikla gonderir.
async def _send_notifications(
    repos,
    user_id: str,
    trigger: str,
    message: str,
) -> None:
    try:
        from services.notification import notify_linked_users

        title_map = {
            "not_ok": "🚨 Acil: Kullanıcı yardım istedi",
            "no_response_after_critical": "⚠️ Kritik: Kullanıcı cevap vermedi",
            "repeated_warning": "⚠️ Tekrarlayan uyarı değerleri",
            "critical_unacknowledged": "🚨 Kritik alarm onaylanmadı",
        }
        title = title_map.get(trigger, "HealthAlert Bildirimi")
        await notify_linked_users(
            db=None,
            self_user_id=user_id,
            self_user_name="",
            title=title,
            body=message,
            notification_type=trigger,
            repos=repos,
        )
    except Exception as exc:
        logger.debug("_send_notifications error (ignored): %s", exc)


# Servis devre disi veya hata durumlari icin guvenli varsayilan sonucu dondurur.
def _default_result() -> Dict[str, Any]:
    return {
        "current_mode": MODE_NORMAL,
        "previous_mode": None,
        "monitoring_intensity": "normal",
        "recommended_poll_interval_sec": settings.ASSISTANT_NORMAL_POLL_INTERVAL_SEC,
        "awaiting_user_ack": False,
        "ack_deadline_at": None,
        "actions_created": [],
        "should_sound_alarm": False,
    }


care_assistant_service = CareAssistantService()
