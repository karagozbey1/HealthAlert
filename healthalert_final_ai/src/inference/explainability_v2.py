import numpy as np
from typing import Dict, List


# V2 aciklama katmani icin neden sablonlarini tutar.
REASON_TEMPLATES = {
    "fall_high": "Fall probability is very high ({prob:.0%})",
    "fall_elevated": "Fall risk is elevated ({prob:.0%})",
    "instability": "Motion instability detected ({prob:.0%})",
    "accel_spike": "High acceleration detected (SVM={svm:.1f}g)",
    "sudden_impact": "Sudden impact detected (jerk={jerk:.0f})",
    "bradycardia": "Heart rate is too low ({hr:.0f} bpm)",
    "tachycardia": "Heart rate is too high ({hr:.0f} bpm)",
    "hr_rising": "Heart rate trend is rising",
    "hypoxemia": "SpO2 is dangerously low ({spo2:.0f}%)",
    "spo2_falling": "SpO2 reliability is low",
    "ppg_poor": "PPG quality is poor, confidence reduced",
    "ppg_moderate": "PPG signal quality is moderate",
    "combined_deterioration": "Combined deterioration pattern observed",
    "inactivity_after_motion": "Inactivity detected after unstable period",
    "all_normal": "All parameters are within normal range. No risk detected.",
}


# V2 tahmin sonucunu kullaniciya aciklanabilir hale getirir.
class ExplainableOutputV2:

    # Esik degerlerini ayarlayip v2 aciklayiciyi kurar.
    def __init__(self, risk_thresholds: Dict = None):
        self.thresholds = risk_thresholds or {
            "hr_low": 50, "hr_high": 120,
            "spo2_low": 92, "fall_prob_warning": 0.5,
        }

    def explain(
        self,
        predictions: Dict[str, float],
        vitals: Dict[str, float] = None,
        imu_features: Dict[str, float] = None,
    ) -> Dict:
        vitals = vitals or {}
        imu_features = imu_features or {}

        contributions: List[Dict] = []

        # Dusme olasiligi yuksekse bunu ana katkilar arasina ekler.
        fall_prob = predictions.get("fall_prob", 0.0)
        if fall_prob > 0.8:
            contributions.append({
                "feature": "fall_detection_model",
                "importance": fall_prob,
                "direction": "risk_increase",
                "explanation": REASON_TEMPLATES["fall_high"].format(prob=fall_prob),
            })
        elif fall_prob > 0.5:
            contributions.append({
                "feature": "fall_detection_model",
                "importance": fall_prob,
                "direction": "risk_increase",
                "explanation": REASON_TEMPLATES["fall_elevated"].format(prob=fall_prob),
            })

        # Denge bozulmasi sinyalini ayri katkı olarak ele alir.
        inst_prob = predictions.get("instability_prob", 0.0)
        if inst_prob > 0.4:
            contributions.append({
                "feature": "instability_detection",
                "importance": inst_prob,
                "direction": "risk_increase",
                "explanation": REASON_TEMPLATES["instability"].format(prob=inst_prob),
            })

        # IMU tarafindaki ani ivme ve darbe ozelliklerini degerlendirir.
        svm_max = imu_features.get("svm_max", imu_features.get("accel_magnitude_max", 0))
        if svm_max > 3.0:
            contributions.append({
                "feature": "acceleration_spike",
                "importance": min(svm_max / 10.0, 1.0),
                "direction": "risk_increase",
                "explanation": REASON_TEMPLATES["accel_spike"].format(svm=svm_max),
            })

        jerk_max = imu_features.get("jerk_max", imu_features.get("jerk_estimate_max", 0))
        if jerk_max > 50:
            contributions.append({
                "feature": "sudden_impact",
                "importance": min(jerk_max / 200.0, 1.0),
                "direction": "risk_increase",
                "explanation": REASON_TEMPLATES["sudden_impact"].format(jerk=jerk_max),
            })

        inactivity = imu_features.get("inactivity_after_instability_proxy", 0)
        if inactivity > 0.5:
            contributions.append({
                "feature": "post_instability_inactivity",
                "importance": 0.5,
                "direction": "risk_increase",
                "explanation": REASON_TEMPLATES["inactivity_after_motion"],
            })

        # Nabiz degerleri ve egilimini aciklama listesine ekler.
        hr = vitals.get("heart_rate", 75)
        if hr < self.thresholds["hr_low"]:
            contributions.append({
                "feature": "bradycardia",
                "importance": 0.7,
                "direction": "risk_increase",
                "explanation": REASON_TEMPLATES["bradycardia"].format(hr=hr),
            })
        elif hr > self.thresholds["hr_high"]:
            contributions.append({
                "feature": "tachycardia",
                "importance": 0.5,
                "direction": "risk_increase",
                "explanation": REASON_TEMPLATES["tachycardia"].format(hr=hr),
            })

        hr_slope = imu_features.get("hr_slope", 0)
        if hr_slope > 0.5:
            contributions.append({
                "feature": "hr_trend",
                "importance": 0.4,
                "direction": "risk_increase",
                "explanation": REASON_TEMPLATES["hr_rising"],
            })

        # SpO2 dususunu bagimsiz risk etkisi olarak ele alir.
        spo2 = vitals.get("spo2", 98)
        if spo2 < self.thresholds["spo2_low"]:
            contributions.append({
                "feature": "hypoxemia",
                "importance": 0.8,
                "direction": "risk_increase",
                "explanation": REASON_TEMPLATES["hypoxemia"].format(spo2=spo2),
            })

        # Sinyal kalitesine gore guven azaltici katkilar ekler.
        quality = predictions.get("quality_score", 1.0)
        if quality < 0.3:
            contributions.append({
                "feature": "signal_quality",
                "importance": 0.4,
                "direction": "confidence_decrease",
                "explanation": REASON_TEMPLATES["ppg_poor"],
            })
        elif quality < 0.5:
            contributions.append({
                "feature": "signal_quality",
                "importance": 0.2,
                "direction": "confidence_decrease",
                "explanation": REASON_TEMPLATES["ppg_moderate"],
            })

        # Birden fazla bozulma birlikte varsa bunu da ozet katkıya ekler.
        risk_factors = [c for c in contributions if c["direction"] == "risk_increase"]
        if len(risk_factors) >= 3:
            contributions.append({
                "feature": "combined_pattern",
                "importance": 0.6,
                "direction": "risk_increase",
                "explanation": REASON_TEMPLATES["combined_deterioration"],
            })

        # Katkilari onem derecesine gore siralar.
        contributions.sort(key=lambda x: x["importance"], reverse=True)

        # Katkilardan tek cumlelik bir ozet cikarir.
        if not contributions:
            summary = REASON_TEMPLATES["all_normal"]
        else:
            top = contributions[0]
            summary = f"Primary factor: {top['explanation']}"

        return {
            "contributions": contributions,
            "summary": summary,
            "n_risk_factors": len(risk_factors) if risk_factors else 0,
        }
