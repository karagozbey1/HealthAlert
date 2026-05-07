import logging
from typing import Dict, List

logger = logging.getLogger("healthalert.inference.postprocessor")


# Ham model ciktilarini yapilandirilmis risk degerlendirmesine donusturur.
class RiskPostprocessor:

    # Esik ve agirlik ayarlarini yukleyip isleyici durumunu kurar.
    def __init__(self, cfg=None):
        if cfg is None:
            cfg = {}

        post_cfg = cfg.get("postprocessing", {})
        fusion_weights = post_cfg.get("fusion_weights", {})
        self.w_fall = fusion_weights.get("fall_probability", 0.35)
        self.w_instability = fusion_weights.get("instability_probability", 0.20)
        self.w_vital = fusion_weights.get("vital_risk", 0.25)
        self.w_quality = fusion_weights.get("ppg_quality_penalty", 0.20)

        thresholds = cfg.get("risk_thresholds", {})
        self.hr_low = thresholds.get("hr_low", 50)
        self.hr_high = thresholds.get("hr_high", 120)
        self.spo2_low = thresholds.get("spo2_low", 92)

    def process(
        self,
        predictions: Dict[str, float],
        vitals: Dict[str, float] = None,
    ) -> Dict:
        fall_prob = predictions.get("fall_prob", 0.0)
        instability_prob = predictions.get("instability_prob", 0.0)
        quality_score = predictions.get("quality_score", 1.0)
        risk_score = predictions.get("risk_score", 0.0)

        # Vital bulgularin olusturdugu ek riski hesaplar.
        vital_risk = self._compute_vital_risk(vitals or {})

        # Dusuk kalite durumunda vital yorumuna guveni azaltir.
        quality_penalty = max(0, 1.0 - quality_score)

        # Tum sinyalleri agirlikli skor olarak birlestirir.
        early_risk_score = (
            self.w_fall * fall_prob
            + self.w_instability * instability_prob
            + self.w_vital * vital_risk
            + self.w_quality * quality_penalty
        )
        early_risk_score = min(1.0, max(0.0, early_risk_score))

        # Hesaplanan skoru nihai risk seviyesine esler.
        if early_risk_score >= 0.7 or fall_prob >= 0.8:
            risk_level = "critical"
        elif early_risk_score >= 0.5:
            risk_level = "warning"
        elif early_risk_score >= 0.3:
            risk_level = "watch"
        else:
            risk_level = "normal"

        # Kullaniciya gosterilecek gerekce listesini uretir.
        reasons = self._build_reasons(
            fall_prob, instability_prob, quality_score, vital_risk, vitals or {}
        )

        # Kalite ve veri varligina gore guven puani olusturur.
        confidence = quality_score * 0.7 + 0.3

        return {
            "fall_probability": round(fall_prob, 4),
            "instability_probability": round(instability_prob, 4),
            "ppg_quality_score": round(quality_score, 4),
            "vital_confidence_score": round(1.0 - quality_penalty, 4),
            "early_risk_score": round(early_risk_score, 4),
            "final_risk_level": risk_level,
            "reasons": reasons,
            "confidence": round(confidence, 4),
        }

    # Vital bulgulardan gelen risk katkisini tek sayiya indirger.
    def _compute_vital_risk(self, vitals: Dict) -> float:
        risk = 0.0
        hr = vitals.get("heart_rate", 75)
        spo2 = vitals.get("spo2", 98)

        if hr < self.hr_low:
            risk += 0.4 * (self.hr_low - hr) / self.hr_low
        elif hr > self.hr_high:
            risk += 0.3 * (hr - self.hr_high) / self.hr_high

        if spo2 < self.spo2_low:
            risk += 0.5 * (self.spo2_low - spo2) / self.spo2_low

        return min(1.0, risk)

    # Risk skorunu aciklayan kisa neden metinlerini toplar.
    def _build_reasons(
        self,
        fall_prob: float,
        instability_prob: float,
        quality_score: float,
        vital_risk: float,
        vitals: Dict,
    ) -> List[str]:
        reasons = []

        if fall_prob >= 0.8:
            reasons.append(f"Düşme olasılığı çok yüksek ({fall_prob:.0%})")
        elif fall_prob >= 0.5:
            reasons.append(f"Düşme riski yüksek ({fall_prob:.0%})")

        if instability_prob >= 0.4:
            reasons.append(f"Denge bozukluğu tespit edildi ({instability_prob:.0%})")

        hr = vitals.get("heart_rate", 75)
        if hr < self.hr_low:
            reasons.append(f"Nabız çok düşük ({hr} bpm)")
        elif hr > self.hr_high:
            reasons.append(f"Nabız çok yüksek ({hr} bpm)")

        spo2 = vitals.get("spo2", 98)
        if spo2 < self.spo2_low:
            reasons.append(f"SpO2 düşük ({spo2}%)")

        if quality_score < 0.3:
            reasons.append("Sinyal kalitesi zayıf - sonuçlar güvenilirliği düşük")

        if not reasons:
            reasons.append("Tüm parametreler normal aralıkta")

        return reasons
