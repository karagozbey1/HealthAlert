# Part 5B kisilestirme motorunun cekirdek hesaplarini ve servisini barindirir.
# Bu katman yalnizca riski kisisellestirir; final skoru ML veya retrieval degistirmez.
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from config import settings

logger = logging.getLogger("healthalert.personalization")

# ---------------------------------------------------------------------------
# Kisisellestirme seviye esikleri
# ---------------------------------------------------------------------------
_COLD_START_MAX_SAMPLES = 30
_LEARNING_MAX_SAMPLES = 300
_MATURE_MIN_FEEDBACK = 10


# Gozlem ve geri bildirim sayisina gore kisilestirme seviyesini belirler.
def _get_personalization_level(total_valid_samples: int, total_feedback_count: int) -> str:
    if total_valid_samples < _COLD_START_MAX_SAMPLES:
        return "cold_start"
    if total_valid_samples < _LEARNING_MAX_SAMPLES:
        return "learning"
    if total_feedback_count >= _MATURE_MIN_FEEDBACK:
        return "mature"
    return "calibrated"


# Seviye bazli uygulanabilecek azami bonusu dondurur.
def _max_bonus_for_level(level: str) -> float:
    if level == "cold_start":
        return settings.PERSONALIZATION_COLD_START_MAX_BONUS
    if level == "learning":
        return settings.PERSONALIZATION_LEARNING_MAX_BONUS
    if level in ("calibrated", "mature"):
        return settings.PERSONALIZATION_CALIBRATED_MAX_BONUS
    return 0.0


# ---------------------------------------------------------------------------
# Baglamsal sapma hesabi
# ---------------------------------------------------------------------------

# Mevcut olcumlerin kullanicinin tipik araligindan ne kadar saptigini hesaplar.
def compute_contextual_deviation(
    profile: Dict[str, Any],
    baseline: Dict[str, Any],
    hr: float,
    spo2: float,
    motion_score: float,
    hr_valid: bool,
    spo2_valid: bool,
) -> Dict[str, Any]:
    """adaptive personalization servisinde risk veya skor değerini hesaplar."""
    level = profile.get("personalization_level", "cold_start")
    max_bonus = _max_bonus_for_level(level)

    if not settings.PERSONALIZATION_ENABLED or max_bonus == 0.0:
        return {"deviation_bonus": 0.0, "level": level, "components": {}}

    hr_bonus = 0.0
    spo2_bonus = 0.0
    motion_bonus = 0.0

    if hr_valid:
        hr_min = profile.get("typical_hr_min", 55.0)
        hr_max = profile.get("typical_hr_max", 100.0)
        hr_range = max(hr_max - hr_min, 10.0)
        if hr > hr_max:
            hr_bonus = min(0.15, (hr - hr_max) / hr_range * 0.3)
        elif hr < hr_min:
            hr_bonus = min(0.10, (hr_min - hr) / hr_range * 0.2)

    if spo2_valid:
        spo2_min = profile.get("typical_spo2_min", 95.0)
        if spo2 < spo2_min:
            drop = spo2_min - spo2
            spo2_bonus = min(0.20, drop * 0.04)

    motion_max = profile.get("typical_motion_max", 0.5)
    if motion_score > motion_max:
        motion_bonus = min(0.05, (motion_score - motion_max) * 0.1)

    raw_bonus = hr_bonus + spo2_bonus + motion_bonus
    capped_bonus = min(max_bonus, raw_bonus)

    return {
        "deviation_bonus": round(capped_bonus, 4),
        "level": level,
        "components": {
            "hr_bonus": round(hr_bonus, 4),
            "spo2_bonus": round(spo2_bonus, 4),
            "motion_bonus": round(motion_bonus, 4),
        },
    }


# ---------------------------------------------------------------------------
# Trend analizi
# ---------------------------------------------------------------------------

# Deger listesinden basit yon bilgisini cikarir.
def _classify_trend(values: List[float]) -> str:
    if len(values) < 3:
        return "stable"
    delta = values[-1] - values[0]
    spread = max(values) - min(values)
    if spread < 1e-6:
        return "stable"
    ratio = abs(delta) / spread
    if ratio < 0.25:
        return "stable"
    return "rising" if delta > 0 else "falling"


# Son anlik goruntulardan HR, SpO2, hareket ve risk trendlerini hesaplar.
def compute_trend_from_snapshots(
    recent_statuses: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """adaptive personalization servisinde risk veya skor değerini hesaplar."""
    if not recent_statuses or len(recent_statuses) < 3:
        return {
            "hr_trend": "stable",
            "spo2_trend": "stable",
            "motion_trend": "stable",
            "quality_trend": "stable",
            "risk_trend": "stable",
            "trend_confidence": 0.0,
            "sample_count": len(recent_statuses) if recent_statuses else 0,
        }

    hrs = [s.get("heart_rate", 72.0) for s in recent_statuses]
    spo2s = [s.get("spo2", 98.0) for s in recent_statuses]
    motions = [s.get("motion_score", 0.1) for s in recent_statuses]
    risks = [s.get("risk_score", 0.05) for s in recent_statuses]
    qualities = [s.get("signal_quality", s.get("quality_confidence", 0.85))
                 for s in recent_statuses]

    n = len(recent_statuses)
    confidence = min(1.0, n / 10.0)

    return {
        "hr_trend": _classify_trend(hrs),
        "spo2_trend": _classify_trend(spo2s),
        "motion_trend": _classify_trend(motions),
        "quality_trend": _classify_trend(qualities),
        "risk_trend": _classify_trend(risks),
        "trend_confidence": round(confidence, 3),
        "sample_count": n,
    }


# Trend sinyallerini risk skoruna eklenecek bir duzeltmeye cevirir.
def compute_trend_adjustment(trend_info: Dict[str, Any], quality_confidence: float) -> float:
    """adaptive personalization servisinde risk veya skor değerini hesaplar."""
    if not settings.PERSONALIZATION_ENABLED:
        return 0.0

    confidence = trend_info.get("trend_confidence", 0.0)
    if confidence < 0.2:
        return 0.0

    hr_trend = trend_info.get("hr_trend", "stable")
    spo2_trend = trend_info.get("spo2_trend", "stable")
    motion_trend = trend_info.get("motion_trend", "stable")

    adjustment = 0.0

    # Tehlikeli kombinasyonda daha yuksek pozitif duzeltme uygular.
    if hr_trend == "rising" and spo2_trend == "falling":
        adjustment += 0.08
    elif hr_trend == "rising":
        adjustment += 0.03
    elif spo2_trend == "falling":
        adjustment += 0.05

    if motion_trend == "rising":
        adjustment += 0.02

    # Etkiyi trend guveni ile carperek sinirlar.
    adjustment *= confidence

    max_bonus = settings.PERSONALIZATION_TREND_MAX_BONUS
    return round(min(max_bonus, max(-max_bonus, adjustment)), 4)


# ---------------------------------------------------------------------------
# Geri bildirim duzeltmesi
# ---------------------------------------------------------------------------

# Gecmis geri bildirim desenlerine gore riski hafifce ayarlar.
def compute_feedback_adjustment(
    profile: Dict[str, Any],
    risk_score: float,
    severity: Optional[str],
    safety_override: bool = False,
) -> float:
    """adaptive personalization servisinde risk veya skor değerini hesaplar."""
    if not settings.PERSONALIZATION_ENABLED:
        return 0.0

    level = profile.get("personalization_level", "cold_start")
    if level == "cold_start":
        return 0.0

    total_fb = profile.get("total_feedback_count", 0)
    if total_fb < 3:
        return 0.0

    false_alarm_count = profile.get("false_alarm_count", 0)
    confirmed_risk_count = profile.get("confirmed_risk_count", 0)
    false_alarm_rate = false_alarm_count / total_fb if total_fb > 0 else 0.0

    adjustment = 0.0
    max_adj = settings.PERSONALIZATION_FEEDBACK_MAX_ADJUSTMENT

    # Yuksek yanlis alarm oraninda warning seviyesini biraz asagi ceker.
    if false_alarm_rate > 0.5 and severity == "warning" and not safety_override:
        adjustment -= min(max_adj * 0.5, false_alarm_rate * max_adj * 0.4)

    # Onaylanmis risk birikirse watch ve ustunde hafif artirir.
    if confirmed_risk_count >= 3 and severity in ("watch", "warning", "critical"):
        ratio = min(1.0, confirmed_risk_count / 20.0)
        adjustment += ratio * max_adj * 0.3

    # Cok sayida sensor hatasi varsa kisilestirme etkisini biraz kisar.
    sensor_errors = profile.get("sensor_error_count", 0)
    if sensor_errors > 5:
        adjustment -= min(0.02, sensor_errors * 0.002)

    # Sonucu belirlenen sinirlar icinde tutar.
    adjustment = max(-max_adj, min(max_adj, adjustment))

    # Koruma modunda negatif duzeltmeye izin vermez.
    if safety_override and adjustment < 0:
        adjustment = 0.0

    return round(adjustment, 4)


# ---------------------------------------------------------------------------
# Ana kisilestirilmis risk hesabi
# ---------------------------------------------------------------------------

# Baseline sonucunun ustune kisilestirme ve trend duzeltmelerini uygular.
def compute_personalized_risk(
    global_risk_score: float,
    baseline_result: Dict[str, Any],
    profile: Dict[str, Any],
    trend_info: Optional[Dict[str, Any]],
    quality_info: Dict[str, Any],
    hr: float = 72.0,
    spo2: float = 98.0,
    motion_score: float = 0.1,
    hr_valid: bool = True,
    spo2_valid: bool = True,
    severity: Optional[str] = None,
) -> Dict[str, Any]:
    """adaptive personalization servisinde risk veya skor değerini hesaplar."""
    baseline_final = baseline_result.get("final_risk_score", global_risk_score)
    quality_confidence = quality_info.get("quality_confidence", 1.0)
    safety_override = quality_info.get("safety_override", False)
    level = profile.get("personalization_level", "cold_start")

    # Kisisel tipik araliklardan sapmayi hesaplar.
    baseline_dict = {
        "hr_mean": profile.get("typical_hr_min", 55.0),
        "hr_std": 10.0,
        "spo2_mean": profile.get("typical_spo2_min", 95.0),
        "spo2_std": 2.0,
        "motion_mean": profile.get("typical_motion_min", 0.0),
        "motion_std": 0.1,
        "is_ready": level in ("calibrated", "mature"),
    }
    deviation = compute_contextual_deviation(
        profile=profile,
        baseline=baseline_dict,
        hr=hr,
        spo2=spo2,
        motion_score=motion_score,
        hr_valid=hr_valid,
        spo2_valid=spo2_valid,
    )
    baseline_deviation_score = deviation["deviation_bonus"]

    # Trend etkisini ekler.
    trend_adjustment = 0.0
    if trend_info:
        trend_adjustment = compute_trend_adjustment(trend_info, quality_confidence)

    # Dusuk kalitede kisilestirme etkisini zayiflatir.
    quality_adjustment = 0.0
    if quality_confidence < 0.5 and not safety_override:
        # Guvenilmez sinyalde bonuslari sinirlar.
        baseline_deviation_score *= quality_confidence * 2
        trend_adjustment = min(0.0, trend_adjustment)
        quality_adjustment = round(baseline_deviation_score * (1 - quality_confidence), 4)
        baseline_deviation_score = round(baseline_deviation_score, 4)

    # Geri bildirim duzeltmesini uygular.
    feedback_adjustment = compute_feedback_adjustment(
        profile=profile,
        risk_score=baseline_final,
        severity=severity,
        safety_override=safety_override,
    )

    # Son skoru baseline sonucunun ustune eklemeli olarak kurar.
    raw_personalized = (
        baseline_final
        + baseline_deviation_score
        + trend_adjustment
        + feedback_adjustment
    )
    final_personalized_risk = round(max(0.0, min(1.0, raw_personalized)), 4)

    # Koruma modunda sonucu baseline altina dusurmez.
    if safety_override:
        final_personalized_risk = max(final_personalized_risk, baseline_final)

    return {
        "global_risk_score": round(global_risk_score, 4),
        "baseline_final_risk": round(baseline_final, 4),
        "baseline_deviation_score": round(baseline_deviation_score, 4),
        "trend_adjustment": round(trend_adjustment, 4),
        "quality_adjustment": round(quality_adjustment, 4),
        "feedback_adjustment": round(feedback_adjustment, 4),
        "final_personalized_risk": final_personalized_risk,
        "personalization_level": level,
        "confidence": round(quality_confidence, 3),
        "safety_override": safety_override,
    }


# ---------------------------------------------------------------------------
# Servis sinifi
# ---------------------------------------------------------------------------

# Repository katmani uzerinden profil ve ozet islemlerini yurutur.
class AdaptivePersonalizationService:

    # Kullanici icin profil kaydini getirir veya guvenli bir varsayilan dondurur.
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    async def get_or_create_profile(self, repos, user_id: str) -> Dict[str, Any]:
        try:
            profile = await repos.personalization.get_or_create_profile(user_id)
            return profile
        except Exception as exc:
            logger.warning("get_or_create_profile failed for %s: %s", user_id, exc)
            return {"user_id": user_id, "personalization_level": "cold_start",
                    "total_valid_samples": 0, "total_feedback_count": 0,
                    "false_alarm_count": 0, "confirmed_risk_count": 0,
                    "sensor_error_count": 0,
                    "typical_hr_min": 55.0, "typical_hr_max": 100.0,
                    "typical_spo2_min": 95.0, "typical_spo2_max": 100.0,
                    "typical_motion_min": 0.0, "typical_motion_max": 0.5}

    # Yeni pakete gore profili EMA ile gunceller ve seviye bilgisini yeniler.
    async def update_profile_from_packet(
        self,
        repos,
        user_id: str,
        hr: float,
        spo2: float,
        motion_score: float,
        hr_valid: bool,
        spo2_valid: bool,
        baseline: Dict[str, Any],
    ) -> Dict[str, Any]:
        """adaptive personalization servisindeki iş kuralı güncellemesini uygular."""
        try:
            profile = await repos.personalization.get_or_create_profile(user_id)
            alpha = 0.01

            updates: Dict[str, Any] = {}

            current_samples = profile.get("total_valid_samples", 0)
            updates["total_valid_samples"] = current_samples + 1
            updates["total_observation_minutes"] = round(
                profile.get("total_observation_minutes", 0.0) + (1.0 / 60.0), 4
            )

            # Tipik aralik sinirlarini EMA ile yumusak bicimde gunceller.
            if hr_valid and hr > 20:
                updates["typical_hr_min"] = round(
                    _ema(profile.get("typical_hr_min", 55.0), max(40.0, hr - 5.0), alpha), 2
                )
                updates["typical_hr_max"] = round(
                    _ema(profile.get("typical_hr_max", 100.0), min(200.0, hr + 5.0), alpha), 2
                )

            if spo2_valid and spo2 > 70:
                updates["typical_spo2_min"] = round(
                    _ema(profile.get("typical_spo2_min", 95.0), max(80.0, spo2 - 1.0), alpha), 2
                )
                updates["typical_spo2_max"] = round(
                    _ema(profile.get("typical_spo2_max", 100.0), min(100.0, spo2), alpha), 2
                )

            updates["typical_motion_max"] = round(
                _ema(profile.get("typical_motion_max", 0.5), motion_score + 0.1, alpha), 3
            )

            new_count = updates["total_valid_samples"]
            updates["personalization_level"] = _get_personalization_level(
                new_count, profile.get("total_feedback_count", 0)
            )
            updates["baseline_id"] = baseline.get("id") if baseline else None

            return await repos.personalization.update_profile(user_id, updates)
        except Exception as exc:
            logger.warning("update_profile_from_packet failed for %s: %s", user_id, exc)
            return {}

    # Risk olayini bellege kaydeder ve profil sayaçlarini gunceller.
    async def record_risk_memory(
        self,
        repos,
        user_id: str,
        event_type: str,
        risk_score: float,
        severity: Optional[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            data = {
                "id": str(uuid4()),
                "user_id": user_id,
                "event_type": event_type,
                "risk_score": risk_score,
                "severity": severity,
                "context_json": context,
                "created_at": datetime.utcnow(),
            }
            result = await repos.personalization.add_risk_memory(data)
            # Ilgili olay sayaclarini ayni akista guncel tutar.
            await self._update_profile_counters(repos, user_id, event_type)
            return result
        except Exception as exc:
            logger.warning("record_risk_memory failed for %s: %s", user_id, exc)
            return None

    # Olay turune gore profil geri bildirim sayaçlarini artirir.
    async def _update_profile_counters(
        self, repos, user_id: str, event_type: str
    ) -> None:
        """adaptive personalization servisindeki iş kuralı güncellemesini uygular."""
        try:
            profile = await repos.personalization.get_or_create_profile(user_id)
            updates: Dict[str, Any] = {}
            total_fb = profile.get("total_feedback_count", 0)

            if event_type == "false_alarm":
                updates["false_alarm_count"] = profile.get("false_alarm_count", 0) + 1
                updates["total_feedback_count"] = total_fb + 1
            elif event_type in ("user_not_ok", "confirmed_risk"):
                updates["confirmed_risk_count"] = profile.get("confirmed_risk_count", 0) + 1
                updates["total_feedback_count"] = total_fb + 1
            elif event_type == "sensor_error":
                updates["sensor_error_count"] = profile.get("sensor_error_count", 0) + 1
                updates["total_feedback_count"] = total_fb + 1
            elif event_type == "user_ok":
                updates["total_feedback_count"] = total_fb + 1

            # Guncellenen geri bildirim sayisina gore seviyeyi yeniden hesaplar.
            new_fb = updates.get("total_feedback_count", total_fb)
            updates["personalization_level"] = _get_personalization_level(
                profile.get("total_valid_samples", 0), new_fb
            )

            if updates:
                await repos.personalization.update_profile(user_id, updates)
        except Exception as exc:
            logger.warning("_update_profile_counters failed for %s: %s", user_id, exc)

    # Hesaplanan trend ozetini kalici olarak saklar.
    async def save_trend_snapshot(
        self,
        repos,
        user_id: str,
        trend_info: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        try:
            data = {
                "id": str(uuid4()),
                "user_id": user_id,
                "window_minutes": 5,
                "hr_trend": trend_info.get("hr_trend", "stable"),
                "spo2_trend": trend_info.get("spo2_trend", "stable"),
                "motion_trend": trend_info.get("motion_trend", "stable"),
                "quality_trend": trend_info.get("quality_trend", "stable"),
                "risk_trend": trend_info.get("risk_trend", "stable"),
                "trend_confidence": trend_info.get("trend_confidence", 0.0),
                "created_at": datetime.utcnow(),
            }
            return await repos.personalization.create_trend_snapshot(data)
        except Exception as exc:
            logger.warning("save_trend_snapshot failed for %s: %s", user_id, exc)
            return None

    # ML model-window ciktisindan profilin ML hafiza metriklerini gunceller.
    async def update_profile_from_ml_window(
        self,
        repos,
        user_id: str,
        ml_evidence_result: Optional[Dict[str, Any]],
        fusion_result: Optional[Dict[str, Any]],
        window_quality: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """adaptive personalization servisindeki iş kuralı güncellemesini uygular."""
        try:
            if repos.personalization is None:
                return {}

            profile = await repos.personalization.get_or_create_profile(user_id)
            updates: Dict[str, Any] = {}

            prev_count = int(profile.get("ml_window_count", 0))
            new_count = prev_count + 1
            updates["ml_window_count"] = new_count

            ml_usable = bool((ml_evidence_result or {}).get("ml_usable", False))
            prev_usable = int(profile.get("ml_usable_window_count", 0))
            updates["ml_usable_window_count"] = prev_usable + (1 if ml_usable else 0)

            evidence = float((ml_evidence_result or {}).get("ml_evidence_score", 0.0) or 0.0)
            confidence = float((ml_evidence_result or {}).get("ml_confidence", 0.0) or 0.0)
            personalized = float((fusion_result or {}).get("personalized_risk_score", 0.0) or 0.0)
            adjustment = float((fusion_result or {}).get("ml_adjustment", 0.0) or 0.0)

            prev_mean = float(profile.get("ml_evidence_mean", 0.0) or 0.0)
            prev_std = float(profile.get("ml_evidence_std", 0.0) or 0.0)
            prev_var = prev_std * prev_std
            new_mean = prev_mean + ((evidence - prev_mean) / max(1, new_count))
            new_var = (
                ((prev_count * prev_var) + (evidence - prev_mean) * (evidence - new_mean))
                / max(1, new_count)
            )
            updates["ml_evidence_mean"] = round(new_mean, 4)
            updates["ml_evidence_std"] = round(max(0.0, new_var) ** 0.5, 4)

            prev_conf_mean = float(profile.get("ml_confidence_mean", 0.0) or 0.0)
            conf_mean = prev_conf_mean + ((confidence - prev_conf_mean) / max(1, new_count))
            updates["ml_confidence_mean"] = round(conf_mean, 4)

            if evidence > personalized:
                updates["ml_positive_support_count"] = int(
                    profile.get("ml_positive_support_count", 0)
                ) + 1

            if abs(evidence - personalized) >= 0.25:
                updates["ml_personal_disagreement_count"] = int(
                    profile.get("ml_personal_disagreement_count", 0)
                ) + 1

            updates["last_ml_evidence_score"] = round(evidence, 4)
            updates["last_ml_adjustment"] = round(adjustment, 4)
            updates["last_model_window_at"] = datetime.utcnow()

            if window_quality is not None:
                updates["last_recalibrated_at"] = datetime.utcnow()

            return await repos.personalization.update_profile(user_id, updates)
        except Exception as exc:
            logger.warning("update_profile_from_ml_window failed for %s: %s", user_id, exc)
            return {}

    # Kullanici icin ozet kisilestirme istatistiklerini dondurur.
    async def get_personalization_summary(self, repos, user_id: str) -> Dict[str, Any]:
        try:
            return await repos.personalization.summarize_personalization(user_id)
        except Exception as exc:
            logger.warning("get_personalization_summary failed for %s: %s", user_id, exc)
            return {"user_id": user_id, "personalization_level": "cold_start",
                    "total_valid_samples": 0, "total_observation_minutes": 0.0,
                    "false_alarm_rate": 0.0, "confirmed_risk_count": 0,
                    "feedback_count": 0, "latest_trend": None,
                    "typical_ranges": {"hr": [55.0, 100.0], "spo2": [95.0, 100.0],
                                       "motion": [0.0, 0.5]}}


# ---------------------------------------------------------------------------
# EMA yardimcisi
# ---------------------------------------------------------------------------

# Verilen degeri EMA mantigiyla gunceller.
def _ema(current: float, new_value: float, alpha: float) -> float:
    return current * (1.0 - alpha) + new_value * alpha


# ---------------------------------------------------------------------------
# Modulde ortak kullanilan servis nesnesini olusturur.
# ---------------------------------------------------------------------------

adaptive_personalization_service = AdaptivePersonalizationService()
