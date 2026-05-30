from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Sohbet ekranina gidecek mevcut kullanici baglamini metin olarak kurar.
def build_chat_context(
    *,
    role: str,
    user_name: str = "",
    patient_name: str = "",
    live_status: Optional[Dict[str, Any]] = None,
    recent_alerts: Optional[List[Dict[str, Any]]] = None,
    recent_anomalies: Optional[List[Dict[str, Any]]] = None,
    recent_history: Optional[List[Dict[str, Any]]] = None,
    trend_summary: Optional[Dict[str, Any]] = None,
    clinical_notes: Optional[List[Dict[str, Any]]] = None,
    screen_context: str = "",
    is_demo_mode: bool = False,
) -> str:
    """context builder servisinde kullanılacak kayıt veya bağlamı hazırlar."""
    lines: List[str] = []

    lines.append(f"[ROL] {role}")
    if user_name:
        lines.append(f"[KULLANICI] {user_name}")
    if patient_name and role in ("RELATIVE", "DOCTOR"):
        lines.append(f"[HASTA] {patient_name}")
    if screen_context:
        lines.append(f"[EKRAN] {screen_context}")
    if is_demo_mode:
        lines.append("[MOD] DEMO — veriler ornektir, gercek degil.")
    else:
        lines.append("[MOD] CANLI")

    lines.append("")
    if live_status:
        hr = live_status.get("heart_rate")
        spo2 = live_status.get("spo2")
        motion = live_status.get("motion_score")
        risk = live_status.get("risk_score")
        scenario = live_status.get("scenario", "unknown")
        ts = live_status.get("timestamp", "")
        lines.append("[CANLI VERILER]")
        if hr is not None:
            lines.append(f"  Nabiz: {hr:.0f} bpm")
        if spo2 is not None:
            lines.append(f"  SpO2: %{spo2:.1f}")
        if motion is not None:
            lines.append(f"  Hareket: {motion:.2f}")
        if risk is not None:
            lines.append(f"  Risk skoru: {risk:.2f}")
        lines.append(f"  Senaryo: {scenario}")
        if ts:
            lines.append(f"  Son guncelleme: {ts}")
    else:
        lines.append("[CANLI VERILER] Yok — cihaz bagli degil veya veri gelmedi.")

    alerts = recent_alerts or []
    active_alerts = [
        a for a in alerts
        if a.get("status") not in ("resolved", "closed")
    ][:5]
    lines.append("")
    if active_alerts:
        lines.append(f"[AKTIF ALARMLAR] ({len(active_alerts)})")
        for a in active_alerts:
            sev = a.get("severity", "?")
            title = a.get("title", "Alarm")
            lines.append(f"  - [{sev.upper()}] {title}")
    else:
        lines.append("[AKTIF ALARMLAR] Yok")

    anomalies = (recent_anomalies or [])[:5]
    lines.append("")
    if anomalies:
        lines.append(f"[SON ANOMALILER] ({len(anomalies)})")
        for an in anomalies:
            metric = an.get("metric", "?")
            value = an.get("value", "?")
            unit = an.get("unit", "")
            lines.append(f"  - {metric}: {value} {unit}")
    else:
        lines.append("[SON ANOMALILER] Yok")

    lines.append("")
    if trend_summary:
        label = trend_summary.get("trend_label", "bilinmiyor")
        summary = trend_summary.get("summary", "")
        lines.append(f"[TREND] {label}")
        if summary:
            lines.append(f"  {summary}")
    else:
        lines.append("[TREND] Bilgi yok")

    history = (recent_history or [])[:5]
    if history:
        lines.append("")
        lines.append(f"[SON GECMIS] ({len(history)} kayit)")
        for h in history:
            itype = h.get("item_type", "?")
            sev = h.get("severity", "")
            ts = _short_ts(h)
            lines.append(f"  - {itype} ({sev}) @ {ts}")

    if role == "DOCTOR" and clinical_notes:
        notes = clinical_notes[:3]
        lines.append("")
        lines.append(f"[KLINIK NOTLAR] ({len(notes)})")
        for n in notes:
            content = (n.get("content") or "")[:150]
            ts = _short_ts(n)
            lines.append(f"  - [{ts}] {content}")

    return "\n".join(lines)

# Farkli zaman alanlarindan kisa ve okunur tarih metni uretir.
def _short_ts(item: dict) -> str:
    for key in ("detected_at", "created_at", "timestamp"):
        val = item.get(key)
        if val is None:
            continue
        if isinstance(val, datetime):
            return val.strftime("%d.%m %H:%M")
        try:
            dt = datetime.fromisoformat(str(val).replace("Z", ""))
            return dt.strftime("%d.%m %H:%M")
        except (ValueError, TypeError):
            continue
    return "?"
