# Baseline servisi kullanicinin tipik araligini EMA ile gunceller ve kaliteye duyarli risk ayari yapar.
# Bu katman global riski kontrollu bicimde duzeltir ancak davranisi yalnizca kendi kurallariyla etkiler.
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from config import settings

logger = logging.getLogger("healthalert.baseline")


# ---------------------------------------------------------------------------
# Guvenilirlik kapisi
# ---------------------------------------------------------------------------

# Bir olcumin baseline guncellemesine dahil edilip edilmeyecegini belirler.
def is_reliable_for_baseline(
    packet_mode: str,
    finger_detected: bool,
    hr_valid: bool,
    spo2_valid: bool,
    signal_quality: float,
    ppg_ok: bool,
    imu_ok: bool,
    hr: float,
    spo2: float,
    global_risk_score: float,
) -> bool:
    if not settings.BASELINE_ENABLED:
        return False

    # Demo / presentation-safe verisinin baseline'i bozmasini engeller.
    if (
        packet_mode in {"mock", "demo", "presentation_safe"}
        and not settings.BASELINE_ALLOW_MOCK_DATA
    ):
        return False

    # Gerekli sensor bayraklari gecersizse olcumu disarida birakir.
    if not finger_detected:
        return False
    if not hr_valid:
        return False
    if not spo2_valid:
        return False
    if not ppg_ok:
        return False
    if signal_quality < settings.BASELINE_MIN_SIGNAL_QUALITY:
        return False

    # Fizyolojik olarak mantiksiz uc degerleri kabul etmez.
    if hr < 45 or hr > 130:
        return False
    if spo2 < 88 or spo2 > 100:
        return False

    # Yuksek riskli olcumlerin baseline'i kaydirmasini engeller.
    if global_risk_score >= settings.RISK_WARNING_THRESHOLD:
        return False

    return True


# ---------------------------------------------------------------------------
# Baseline guncelleme
# ---------------------------------------------------------------------------

# Mevcut paketi kullanarak kullanici baseline degerlerini EMA ile gunceller.
# Guvenilir degilse mevcut baseline sozlugunu degistirmeden geri dondurur.
async def update_user_baseline(
    repos,
    user_id: str,
    packet_mode: str,
    finger_detected: bool,
    hr_valid: bool,
    spo2_valid: bool,
    signal_quality: float,
    ppg_ok: bool,
    imu_ok: bool,
    hr: float,
    spo2: float,
    motion_score: float,
    global_risk_score: float,
) -> Dict[str, Any]:
    baseline = await repos.baselines.get_or_create(user_id)

    reliable = is_reliable_for_baseline(
        packet_mode=packet_mode,
        finger_detected=finger_detected,
        hr_valid=hr_valid,
        spo2_valid=spo2_valid,
        signal_quality=signal_quality,
        ppg_ok=ppg_ok,
        imu_ok=imu_ok,
        hr=hr,
        spo2=spo2,
        global_risk_score=global_risk_score,
    )

    if not reliable:
        return baseline

    alpha = settings.BASELINE_EMA_ALPHA
    n = baseline["sample_count"]

    # Ortalama ve yayilim degerlerini EMA ile ilerletir.
    hr_mean = _ema(baseline["hr_mean"], hr, alpha)
    hr_var = _ema_var(baseline["hr_std"] ** 2, hr, baseline["hr_mean"], alpha)
    hr_std = max(5.0, hr_var ** 0.5)

    spo2_mean = _ema(baseline["spo2_mean"], spo2, alpha)
    spo2_var = _ema_var(baseline["spo2_std"] ** 2, spo2, baseline["spo2_mean"], alpha)
    spo2_std = max(1.0, spo2_var ** 0.5)

    # IMU gecerliyse hareket baseline'ini da birlikte gunceller.
    if imu_ok:
        motion_mean = _ema(baseline["motion_mean"], motion_score, alpha)
        motion_var = _ema_var(baseline["motion_std"] ** 2, motion_score, baseline["motion_mean"], alpha)
        motion_std = max(0.05, motion_var ** 0.5)
    else:
        motion_mean = baseline["motion_mean"]
        motion_std = baseline["motion_std"]

    ppg_quality_mean = _ema(baseline["ppg_quality_mean"], signal_quality, alpha)

    new_n = n + 1
    is_ready = new_n >= settings.BASELINE_MIN_SAMPLES

    now = datetime.utcnow()
    updates = {
        "hr_mean": round(hr_mean, 4),
        "hr_std": round(hr_std, 4),
        "spo2_mean": round(spo2_mean, 4),
        "spo2_std": round(spo2_std, 4),
        "motion_mean": round(motion_mean, 4),
        "motion_std": round(motion_std, 4),
        "ppg_quality_mean": round(ppg_quality_mean, 4),
        "sample_count": new_n,
        "is_ready": is_ready,
        "updated_at": now,
        "last_updated": now,
    }

    updated = await repos.baselines.update_values(user_id, updates)
    logger.debug(
        "Baseline updated user=%s sample_count=%d is_ready=%s",
        user_id, new_n, is_ready,
    )
    return updated


# Tek adimlik EMA ortalama guncellemesi yapar.
def _ema(old: float, new: float, alpha: float) -> float:
    return alpha * new + (1.0 - alpha) * old


# EMA varyansini onceki ortalamaya gore gunceller.
def _ema_var(old_var: float, new_val: float, old_mean: float, alpha: float) -> float:
    diff = new_val - old_mean
    return (1.0 - alpha) * (old_var + alpha * diff * diff)


# ---------------------------------------------------------------------------
# Kisisel sapma
# ---------------------------------------------------------------------------

# Anlik olcumin kisisel baseline'dan sapma miktarini hesaplar.
def compute_personal_deviation(
    baseline: Dict[str, Any],
    hr: float,
    spo2: float,
    motion_score: float,
    hr_valid: bool,
    spo2_valid: bool,
) -> Dict[str, Any]:
    hr_z = 0.0
    if hr_valid:
        hr_z = abs(hr - baseline["hr_mean"]) / max(baseline["hr_std"], 5.0)

    spo2_z = 0.0
    if spo2_valid:
        spo2_z = max(0.0, baseline["spo2_mean"] - spo2) / max(baseline["spo2_std"], 1.0)

    motion_z = max(0.0, motion_score - baseline["motion_mean"]) / max(baseline["motion_std"], 0.05)

    # Bonus etkisi ancak anlamli sapma esigi asildiginda baslar.
    hr_contrib = max(0.0, hr_z - 2.0) * 0.04
    spo2_contrib = max(0.0, spo2_z - 2.0) * 0.06
    motion_contrib = max(0.0, motion_z - 2.0) * 0.02

    bonus = min(
        settings.BASELINE_PERSONAL_BONUS_MAX,
        hr_contrib + spo2_contrib + motion_contrib,
    )

    return {
        "hr_z": round(hr_z, 3),
        "spo2_z": round(spo2_z, 3),
        "motion_z": round(motion_z, 3),
        "deviation_bonus": round(bonus, 4),
    }


# ---------------------------------------------------------------------------
# Kalite guveni
# ---------------------------------------------------------------------------

# Sensor bayraklari ve sinyal kalitesinden 0-1 arasi guven skoru uretir.
def compute_quality_confidence(
    signal_quality: float,
    finger_detected: bool,
    hr_valid: bool,
    spo2_valid: bool,
    ppg_ok: bool,
    spo2: float,
    spo2_valid_flag: bool,
) -> Dict[str, Any]:
    score = signal_quality

    if not finger_detected:
        score *= 0.0
    if not ppg_ok:
        score *= 0.5
    if not hr_valid:
        score *= 0.7
    if not spo2_valid:
        score *= 0.8

    score = max(0.0, min(1.0, score))

    warning: Optional[str] = None
    if not finger_detected:
        warning = "Finger not detected. Vitals may be unreliable."
    elif signal_quality < 0.40:
        warning = f"Low signal quality ({signal_quality:.2f}). Readings may be inaccurate."
    elif not hr_valid and not spo2_valid:
        warning = "Heart rate and SpO2 readings are invalid."
    elif not hr_valid:
        warning = "Heart rate reading is invalid."
    elif not spo2_valid:
        warning = "SpO2 reading is invalid."

    # Gecerli ve cok dusuk SpO2 varsa risk sinyalini bastirmaz.
    safety_override = spo2_valid_flag and spo2 < 88

    return {
        "quality_confidence": round(score, 3),
        "quality_warning": warning,
        "safety_override": safety_override,
    }


# ---------------------------------------------------------------------------
# Baseline duzeltmesi
# ---------------------------------------------------------------------------

# Global risk ile kisisel sapma bonusunu kalite guveni altinda birlestirir.
def apply_baseline_adjustment(
    global_risk_score: float,
    deviation: Dict[str, Any],
    quality_info: Dict[str, Any],
    baseline_ready: bool,
    alert_sensitivity: str = "normal",
) -> Dict[str, Any]:
    confidence = quality_info["quality_confidence"]
    safety_override = quality_info.get("safety_override", False)

    personal_deviation_score = 0.0
    if baseline_ready:
        personal_deviation_score = deviation["deviation_bonus"]
        # Dusuk kalitede bonusu kapatir ama global riski korur.
        if confidence < 0.5 and not safety_override:
            personal_deviation_score = 0.0

    final_risk_score = round(
        min(1.0, max(0.0, global_risk_score + personal_deviation_score)),
        3,
    )

    return {
        "final_risk_score": final_risk_score,
        "global_risk_score": round(global_risk_score, 3),
        "personal_deviation_score": round(personal_deviation_score, 4),
        "baseline_ready": baseline_ready,
        "quality_confidence": confidence,
        "quality_warning": quality_info["quality_warning"],
        "alert_sensitivity": alert_sensitivity,
    }
