from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from services.assistant_service import generate_assistant_summary
from services.context_builder import build_chat_context
from services.llm_client import LLMClient, get_llm_client
from services.prompt_templates import get_system_prompt
from services.trend_service import analyze_trends

logger = logging.getLogger("healthalert.chat")

DISCLAIMER = (
    "Bu degerlendirme sensor ve sistem verilerine dayali otomatik bir yorumdur. "
    "Tibbi teshis yerine gecmez."
)

SUGGESTIONS: Dict[str, List[str]] = {
    "SELF": [
        "Bugunku durumumu ozetle",
        "Neden uyari aldim?",
        "Su an ne yapmaliyim?",
        "Risk neden yukseldi?",
        "Doktora gorunmeli miyim?",
        "Trendleri acikla",
    ],
    "RELATIVE": [
        "Yakinimin durumu nasil?",
        "Yakinim icin ne yapmaliyim?",
        "Son alarmlari acikla",
        "Doktora haber vermeli miyim?",
        "Trendleri ozetle",
    ],
    "DOCTOR": [
        "Hastanin guncel durumunu ozetle",
        "Son 24 saatteki trend nasil?",
        "Dikkat edilmesi gereken bulgular",
        "Anomali oruntuleri var mi?",
        "Klinik notlara gore son durum",
    ],
}

@dataclass
class UIAction:
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    label: str
    route: str

    # Arayuzde kullanilacak eylem bilgisini API yanitina uygun bicime cevirir.
    def to_dict(self) -> Dict[str, str]:
        return {"label": self.label, "route": self.route}

MAX_SESSIONS = 500
MAX_MESSAGES_PER_SESSION = 20

@dataclass
class ChatMessage:
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)

    # Mesaji LLM istemcisinin bekledigi rol-icerik yapisina donusturur.
    def to_llm_format(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}

@dataclass
class ChatSession:
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    session_id: str
    user_id: str
    target_user_id: str
    role: str
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    # Sohbet oturumuna yeni bir mesaj ekler ve gecmis boyutunu sinirlar.
    def add_message(self, role: str, content: str) -> None:
        self.messages.append(ChatMessage(role=role, content=content))
        if len(self.messages) > MAX_MESSAGES_PER_SESSION:
            self.messages = self.messages[-MAX_MESSAGES_PER_SESSION:]

    # Oturum gecmisini LLM istemcisine gonderilecek listeye donusturur.
    def conversation_for_llm(self) -> List[Dict[str, str]]:
        return [m.to_llm_format() for m in self.messages]

class SessionStore:

    # Oturum deposunu belirlenen kapasiteyle baslatir.
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    def __init__(self, max_size: int = MAX_SESSIONS) -> None:
        self._store: OrderedDict[str, ChatSession] = OrderedDict()
        self._max = max_size

    # Kimlige gore oturumu getirir ve kullanildiysa sona tasir.
    def get(self, session_id: str) -> Optional[ChatSession]:
        session = self._store.get(session_id)
        if session:
            self._store.move_to_end(session_id)
        return session

    # Yeni bir sohbet oturumu olusturur ve kapasite doluysa en eskisini siler.
    def create(self, user_id: str, target_user_id: str, role: str) -> ChatSession:
        """chat servisinde kullanılacak kayıt veya bağlamı hazırlar."""
        sid = str(uuid4())
        session = ChatSession(
            session_id=sid,
            user_id=user_id,
            target_user_id=target_user_id,
            role=role,
        )
        self._store[sid] = session
        if len(self._store) > self._max:
            self._store.popitem(last=False)
        return session

    # Gecerli bir oturum varsa onu kullanir, yoksa yeni bir oturum olusturur.
    def get_or_create(
        self, session_id: Optional[str], user_id: str, target_user_id: str, role: str
    ) -> ChatSession:
        if session_id:
            existing = self.get(session_id)
            if existing and existing.user_id == user_id:
                return existing
        return self.create(user_id, target_user_id, role)

session_store = SessionStore()

# Kullanici mesajini isleyip baglam, yanit ve olasi arayuz eylemleriyle birlikte dondurur.
async def process_chat_message(
    *,
    message: str,
    session_id: Optional[str],
    user_id: str,
    target_user_id: str,
    role: str,
    user_name: str = "",
    patient_name: str = "",
    screen_context: str = "",
    live_status: Optional[Dict[str, Any]] = None,
    recent_alerts: Optional[List[Dict[str, Any]]] = None,
    recent_anomalies: Optional[List[Dict[str, Any]]] = None,
    recent_history: Optional[List[Dict[str, Any]]] = None,
    clinical_notes: Optional[List[Dict[str, Any]]] = None,
    is_demo_mode: bool = False,
    llm: Optional[LLMClient] = None,
) -> Dict[str, Any]:
    llm = llm or get_llm_client()

    session = session_store.get_or_create(session_id, user_id, target_user_id, role)
    session.add_message("user", message)

    trend = analyze_trends(recent_history or [], recent_anomalies or [], live_status, role)
    context_text = build_chat_context(
        role=role,
        user_name=user_name,
        patient_name=patient_name,
        live_status=live_status,
        recent_alerts=recent_alerts,
        recent_anomalies=recent_anomalies,
        recent_history=recent_history,
        trend_summary=trend,
        clinical_notes=clinical_notes if role == "DOCTOR" else None,
        screen_context=screen_context,
        is_demo_mode=is_demo_mode,
    )

    assistant_text: Optional[str] = None
    source = "llm"

    if llm.is_configured:
        system_prompt = get_system_prompt(role)
        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": f"--- HASTA/KULLANICI BAGLAMI ---\n{context_text}"},
        ]
        llm_messages.extend(session.conversation_for_llm())

        assistant_text = await llm.chat(llm_messages)

    if assistant_text is None:
        source = "rule_based"
        assistant_text = _rule_based_fallback(
            message=message,
            role=role,
            live_status=live_status,
            recent_alerts=recent_alerts or [],
            recent_anomalies=recent_anomalies or [],
            recent_history=recent_history or [],
        )

    session.add_message("assistant", assistant_text)

    ui_actions = _suggest_ui_actions(message, live_status, recent_alerts)

    return {
        "session_id": session.session_id,
        "message": assistant_text,
        "source": source,
        "disclaimer": DISCLAIMER,
        "ui_actions": [a.to_dict() for a in ui_actions],
        "context_summary": _brief_context_summary(live_status, recent_alerts, trend),
    }

# Rolle iliskili hazir sohbet onerilerini dondurur.
def get_suggestions(role: str) -> List[str]:
    return SUGGESTIONS.get(role.upper(), SUGGESTIONS["SELF"])

# Mevcut kullanici baglamini metinsel bir onizleme olarak uretir.
def get_context_preview(
    *,
    role: str,
    user_name: str = "",
    patient_name: str = "",
    live_status: Optional[Dict[str, Any]] = None,
    recent_alerts: Optional[List[Dict[str, Any]]] = None,
    recent_anomalies: Optional[List[Dict[str, Any]]] = None,
    recent_history: Optional[List[Dict[str, Any]]] = None,
    clinical_notes: Optional[List[Dict[str, Any]]] = None,
    is_demo_mode: bool = False,
) -> str:
    trend = analyze_trends(recent_history or [], recent_anomalies or [], live_status, role)
    return build_chat_context(
        role=role,
        user_name=user_name,
        patient_name=patient_name,
        live_status=live_status,
        recent_alerts=recent_alerts,
        recent_anomalies=recent_anomalies,
        recent_history=recent_history,
        trend_summary=trend,
        clinical_notes=clinical_notes if role == "DOCTOR" else None,
        is_demo_mode=is_demo_mode,
    )

# LLM kullanilamadiginda kurallara dayali yedek yaniti olusturur.
def _rule_based_fallback(
    *,
    message: str,
    role: str,
    live_status: Optional[Dict[str, Any]],
    recent_alerts: List[Dict[str, Any]],
    recent_anomalies: List[Dict[str, Any]],
    recent_history: List[Dict[str, Any]],
) -> str:
    summary = generate_assistant_summary(
        live_status, recent_anomalies, recent_alerts, recent_history, role
    )

    text = summary.get("summary", "")
    recs = summary.get("recommendations", [])
    rec_text = "\n".join(f"- {r['title']}: {r['action']}" for r in recs[:3])

    msg_lower = message.lower()
    if any(k in msg_lower for k in ("neden", "uyari", "alarm", "niye")):
        reasoning = summary.get("reasoning", [])
        if reasoning:
            text = "Uyari nedenleri:\n" + "\n".join(f"- {r}" for r in reasoning)
        else:
            text = "Su an aktif bir uyari nedeni bulunamadi."

    elif any(k in msg_lower for k in ("yapmaliyim", "oneri", "tavsiye")):
        if rec_text:
            text = "Oneriler:\n" + rec_text
        else:
            text = "Degerleriniz normal gorunuyor. Gunluk takibe devam edin."

    elif any(k in msg_lower for k in ("ozetle", "ozet", "durum", "nasil")):
        pass

    elif any(k in msg_lower for k in ("trend", "kotulesiyor", "artiyor", "iyilesiyor")):
        text = "Trend bilgisi icin yeterli gecmis veri bulunmuyor. Veriler toplandikca daha iyi analiz yapilabilecek."

    elif any(k in msg_lower for k in ("doktor", "hastane", "acil")):
        risk = summary.get("risk_level", "normal")
        if risk in ("critical", "warning"):
            text = "Mevcut verilerinize gore saglik uzmani kontrolu onerilir. Bu kesin bir teshis degildir."
        else:
            text = "Su anki verilere gore acil bir durum gorunmuyor. Ancak supheniz varsa doktorunuza danisin."

    text += f"\n\n({DISCLAIMER})"
    return text

# Kullanici mesajina gore uygulamada acilabilecek kisa yol eylemlerini seçer.
def _suggest_ui_actions(
    message: str,
    live_status: Optional[Dict[str, Any]],
    alerts: Optional[List[Dict[str, Any]]],
) -> List[UIAction]:
    actions: List[UIAction] = []
    msg = message.lower()

    if any(k in msg for k in ("canli", "izleme", "monitor", "vital")):
        actions.append(UIAction(label="Canli Izleme ekranini ac", route="/live-monitor"))
    if any(k in msg for k in ("gecmis", "tarihce", "son 24")):
        actions.append(UIAction(label="Gecmis detayina git", route="/history"))
    if any(k in msg for k in ("ayar", "bildirim", "profil")):
        actions.append(UIAction(label="Ayarlar", route="/settings"))
    if any(k in msg for k in ("yakin", "bilgilendir", "haber")):
        actions.append(UIAction(label="Yakinini bilgilendir", route="/contacts"))
    if any(k in msg for k in ("alarm", "uyari")):
        active = [a for a in (alerts or []) if a.get("status") not in ("resolved", "closed")]
        if active:
            actions.append(UIAction(label="Aktif alarmlari gor", route="/alerts"))

    return actions[:3]

# Canli veri, alarm ve trend bilgisini tek satirlik ozet haline getirir.
def _brief_context_summary(
    live: Optional[Dict[str, Any]],
    alerts: Optional[List[Dict[str, Any]]],
    trend: Optional[Dict[str, Any]],
) -> str:
    parts = []
    if live:
        hr = live.get("heart_rate", 0)
        spo2 = live.get("spo2", 0)
        parts.append(f"HR:{hr:.0f} SpO2:%{spo2:.1f}")
    else:
        parts.append("Canli veri yok")

    active = len([a for a in (alerts or []) if a.get("status") not in ("resolved", "closed")])
    if active:
        parts.append(f"{active} aktif alarm")

    if trend:
        parts.append(f"Trend:{trend.get('trend_label', '?')}")

    return " | ".join(parts)
