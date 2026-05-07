from typing import Dict, List


# Risk seviyesine gore varsayilan v2 onerilerini tutar.
DEFAULT_RECOMMENDATIONS: Dict[str, List[str]] = {
    "critical": [
        "FALL RISK VERY HIGH — immediate assistance may be needed",
        "Emergency contacts have been automatically notified",
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
        "Mild instability signs detected — monitoring continues",
        "Vital signs are within acceptable range",
        "You may continue your activity carefully",
        "Regular check-up recommended",
    ],
    "normal": [
        "All values are normal",
        "System is actively monitoring",
        "No risk detected",
    ],
}


# V2 risk sonucuna gore onerileri ve acil uyarilari uretir.
class RecommendationEngineV2:

    # Ozellestirilmis öneri seti verilmezse varsayilanlari kullanir.
    def __init__(self, custom_recommendations: Dict[str, List[str]] = None):
        self.recommendations = custom_recommendations or DEFAULT_RECOMMENDATIONS

    def get_recommendations(
        self,
        risk_assessment: Dict,
    ) -> List[str]:
        risk_level = risk_assessment.get("final_risk_level", "normal")
        base_recs = self.recommendations.get(risk_level, self.recommendations["normal"])

        recs = list(base_recs)

        # Düşük kalite durumunda sensör kontrol önerisi ekler.
        quality = risk_assessment.get("ppg_quality_score", 1.0)
        if quality < 0.3:
            recs.append("Sensor contact should be checked — signal quality is poor")
        elif quality < 0.5:
            recs.append("Please check sensor positioning")

        # Acil durumlarda uyarıyı listenin başına taşır.
        if risk_assessment.get("immediate_alert", False):
            recs.insert(0, "⚠ IMMEDIATE ATTENTION REQUIRED — critical condition detected")

        return recs
