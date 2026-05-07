import logging
from typing import Dict, List

logger = logging.getLogger("healthalert.inference.postprocessor_v2")

# Varsayilan esik degerlerini tek yerde toplar.
DEFAULT_THRESHOLDS = {
    "hr_low": 50,
    "hr_high": 120,
    "spo2_low": 92,
    "fall_prob_critical": 0.8,
    "fall_prob_warning": 0.5,
    "instability_warning": 0.4,
    "risk_critical": 0.7,
    "risk_warning": 0.5,
    "risk_watch": 0.3,
    "quality_unreliable": 0.3,
    "quality_low": 0.5,
    "immediate_alert_risk": 0.85,
    "immediate_alert_fall": 0.9,
    "single_signal_dampen": 0.9,
}

DEFAULT_FUSION_WEIGHTS = {
    "fall_probability": 0.35,
    "instability_probability": 0.20,
    "vital_risk": 0.25,
    "ppg_quality_penalty": 0.20,
}

# Risk seviyesine gore varsayilan onerileri tutar.
RECOMMENDATIONS = {
    "critical": [
        "FALL RISK VERY HIGH — immediate assistance may be needed",
        "Emergency contacts have been notified",
        "Do not move; help is on the way",
        "Consider calling emergency services (112/911)",
    ],
    "warning": [
        "Instability detected — please be careful",
        "Heart rate / SpO2 values are abnormal — rest recommended",
        "Please sit down or move to a safe location",
        "Close contacts will be informed",
    ],
    "watch": [
        "Mild instability signs detected — monitoring",
        "Vital signs are within acceptable range",
        "You may continue your activity carefully",
        "Regular check-up recommended",
    ],
    "normal": [
        "All parameters are within normal range",
        "System is actively monitoring",
        "No risk detected",
    ],
}


# Gelismis risk isleyicisiyle alert ve onerileri bir arada uretir.
class RiskPostprocessorV2:

    # Esik ve agirlik degerlerini yukleyip v2 isleyiciyi hazirlar.
    def __init__(self, cfg=None):
        if cfg is None:
            cfg = {}

        post_cfg = cfg.get("postprocessing", {})
        fw = post_cfg.get("fusion_weights", DEFAULT_FUSION_WEIGHTS)
        self.w_fall = fw.get("fall_probability", 0.35)
        self.w_instability = fw.get("instability_probability", 0.20)
        self.w_vital = fw.get("vital_risk", 0.25)
        self.w_quality = fw.get("ppg_quality_penalty", 0.20)

        th = cfg.get("risk_thresholds", DEFAULT_THRESHOLDS)
        self.thresholds = {**DEFAULT_THRESHOLDS, **th}

    def process(
        self,
        predictions: Dict[str, float],
        vitals: Dict[str, float] = None,
    ) -> Dict:
        vitals = vitals or {}

        fall_prob = predictions.get("fall_prob", 0.0)
        instability_prob = predictions.get("instability_prob", 0.0)
        quality_score = predictions.get("quality_score", 1.0)
        risk_score = predictions.get("risk_score", 0.0)

        # Vital bulgularin olusturdugu riski hesaplar.
        vital_risk = self._compute_vital_risk(vitals)

        # Dusuk kalite durumunda ek ceza uygular.
        quality_penalty = max(0.0, 1.0 - quality_score)

        # Erken risk skorunu agirlikli olarak birlestirir.
        early_risk = (
            self.w_fall * fall_prob
            + self.w_instability * instability_prob
            + self.w_vital * vital_risk
            + self.w_quality * quality_penalty
        )
        early_risk = min(1.0, max(0.0, early_risk))

        # Birden fazla sinyal bozulduysa skoru bir miktar guclendirir.
        n_elevated = sum([
            fall_prob >= self.thresholds["fall_prob_warning"],
            instability_prob >= self.thresholds["instability_warning"],
            vital_risk > 0.3,
        ])
        if n_elevated >= 2:
            early_risk = min(1.0, early_risk * 1.15)

        # Tek kanalli ani sicrama durumunda asiri guveni azaltir.
        if n_elevated <= 1:
            dampen = float(self.thresholds.get("single_signal_dampen", 0.9))
            early_risk = max(0.0, min(1.0, early_risk * dampen))

        # Son skora gore risk seviyesini belirler.
        if early_risk >= self.thresholds["risk_critical"] or fall_prob >= self.thresholds["fall_prob_critical"]:
            risk_level = "critical"
        elif early_risk >= self.thresholds["risk_warning"]:
            risk_level = "warning"
        elif early_risk >= self.thresholds["risk_watch"]:
            risk_level = "watch"
        else:
            risk_level = "normal"

        # Acil bildirim gerekip gerekmedigini ayrica hesaplar.
        immediate_alert = (
            fall_prob >= self.thresholds["immediate_alert_fall"]
            or early_risk >= self.thresholds["immediate_alert_risk"]
            or (instability_prob >= 0.7 and vital_risk >= 0.5)
        )

        # Aciklayici nedenleri bir liste halinde toplar.
        reasons = self._build_reasons(
            fall_prob, instability_prob, quality_score, vital_risk, vitals
        )

        # Risk seviyesine uygun onerileri secip kaliteye gore zenginlestirir.
        recommendations = list(RECOMMENDATIONS.get(risk_level, RECOMMENDATIONS["normal"]))
        if quality_score < self.thresholds["quality_unreliable"]:
            recommendations.append("Sensor contact should be checked — signal quality is low")
        elif quality_score < self.thresholds["quality_low"]:
            recommendations.append("Please check sensor positioning")

        # Sonucun guven derecesini hesaplar.
        confidence = quality_score * 0.7 + 0.3

        return {
            "fall_probability": round(fall_prob, 4),
            "instability_probability": round(instability_prob, 4),
            "ppg_quality_score": round(quality_score, 4),
            "vital_confidence_score": round(1.0 - quality_penalty, 4),
            "early_risk_score": round(early_risk, 4),
            "final_risk_level": risk_level,
            "immediate_alert": immediate_alert,
            "reasons": reasons,
            "recommendations": recommendations,
            "raw_scores": {
                "fall_prob": round(fall_prob, 4),
                "instability_prob": round(instability_prob, 4),
                "quality_score": round(quality_score, 4),
                "risk_score": round(risk_score, 4),
                "vital_risk": round(vital_risk, 4),
                "quality_penalty": round(quality_penalty, 4),
                "n_elevated_signals": int(n_elevated),
            },
            "confidence": round(confidence, 4),
        }

    # Vital verilerin toplam risk katkisini hesaplar.
    def _compute_vital_risk(self, vitals: Dict) -> float:
        risk = 0.0
        hr = vitals.get("heart_rate", 75)
        spo2 = vitals.get("spo2", 98)

        if hr < self.thresholds["hr_low"]:
            risk += 0.4 * (self.thresholds["hr_low"] - hr) / self.thresholds["hr_low"]
        elif hr > self.thresholds["hr_high"]:
            risk += 0.3 * (hr - self.thresholds["hr_high"]) / self.thresholds["hr_high"]

        if spo2 < self.thresholds["spo2_low"]:
            risk += 0.5 * (self.thresholds["spo2_low"] - spo2) / self.thresholds["spo2_low"]

        return min(1.0, risk)

    # Kullaniciya gosterilecek neden metinlerini toplar.
    def _build_reasons(
        self,
        fall_prob: float,
        instability_prob: float,
        quality_score: float,
        vital_risk: float,
        vitals: Dict,
    ) -> List[str]:
        reasons: List[str] = []

        if fall_prob >= self.thresholds["fall_prob_critical"]:
            reasons.append(f"Fall probability is very high ({fall_prob:.0%})")
        elif fall_prob >= self.thresholds["fall_prob_warning"]:
            reasons.append(f"Fall risk is elevated ({fall_prob:.0%})")

        if instability_prob >= self.thresholds["instability_warning"]:
            reasons.append(f"Motion instability detected ({instability_prob:.0%})")

        hr = vitals.get("heart_rate", 75)
        if hr < self.thresholds["hr_low"]:
            reasons.append(f"Heart rate is too low ({hr:.0f} bpm)")
        elif hr > self.thresholds["hr_high"]:
            reasons.append(f"Heart rate is too high ({hr:.0f} bpm)")

        spo2 = vitals.get("spo2", 98)
        if spo2 < self.thresholds["spo2_low"]:
            reasons.append(f"SpO2 is low ({spo2:.0f}%)")

        if quality_score < self.thresholds["quality_unreliable"]:
            reasons.append("PPG quality is poor, confidence reduced")
        elif quality_score < self.thresholds["quality_low"]:
            reasons.append("SpO2 reliability is low")

        # Birden fazla sinyal birlikte bozulduysa bunu vurgular.
        if vital_risk > 0.3 and instability_prob > 0.3:
            reasons.append("Combined deterioration pattern observed")

        if not reasons:
            reasons.append("All parameters are within normal range")

        return reasons
