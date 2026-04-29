"""Recommendation engine based on risk level (v2 — English).

Default language: English.
All recommendation strings are in English for consistency.
"""

from typing import Dict, List


# English recommendations keyed by risk level
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


class RecommendationEngineV2:
    """Generate context-aware recommendations based on risk assessment.

    Language: English (default). Override via custom_recommendations.
    """

    def __init__(self, custom_recommendations: Dict[str, List[str]] = None):
        self.recommendations = custom_recommendations or DEFAULT_RECOMMENDATIONS

    def get_recommendations(
        self,
        risk_assessment: Dict,
    ) -> List[str]:
        """Generate recommendations based on risk assessment.

        Args:
            risk_assessment: Output from RiskPostprocessorV2.

        Returns:
            List of recommendation strings.
        """
        risk_level = risk_assessment.get("final_risk_level", "normal")
        base_recs = self.recommendations.get(risk_level, self.recommendations["normal"])

        recs = list(base_recs)

        # Quality warning
        quality = risk_assessment.get("ppg_quality_score", 1.0)
        if quality < 0.3:
            recs.append("Sensor contact should be checked — signal quality is poor")
        elif quality < 0.5:
            recs.append("Please check sensor positioning")

        # Immediate alert
        if risk_assessment.get("immediate_alert", False):
            recs.insert(0, "⚠ IMMEDIATE ATTENTION REQUIRED — critical condition detected")

        return recs
