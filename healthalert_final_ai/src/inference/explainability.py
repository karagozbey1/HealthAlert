"""Explainability module for model predictions."""

import numpy as np
from typing import Dict, List


class ExplainableOutput:
    """Generate human-readable explanations of model predictions.

    Provides feature importance and decision reasoning without
    requiring complex SHAP/LIME (those can be added later).
    """

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
        """Generate explainability report.

        Args:
            predictions: Model output probabilities.
            vitals: Current vital values.
            imu_features: Extracted IMU features.

        Returns:
            Dict with importance scores and natural language explanations.
        """
        vitals = vitals or {}
        imu_features = imu_features or {}

        # Feature contributions (rule-based approximation)
        contributions = []

        fall_prob = predictions.get("fall_prob", 0.0)
        if fall_prob > 0.5:
            contributions.append({
                "feature": "fall_detection_model",
                "importance": fall_prob,
                "direction": "risk_increase",
                "explanation": f"Model {fall_prob:.0%} düşme olasılığı hesapladı",
            })

        svm_max = imu_features.get("svm_max", 0)
        if svm_max > 3.0:
            contributions.append({
                "feature": "acceleration_spike",
                "importance": min(svm_max / 10.0, 1.0),
                "direction": "risk_increase",
                "explanation": f"Yüksek ivme tespit edildi (SVM={svm_max:.1f}g)",
            })

        jerk_max = imu_features.get("jerk_max", 0)
        if jerk_max > 50:
            contributions.append({
                "feature": "sudden_impact",
                "importance": min(jerk_max / 200.0, 1.0),
                "direction": "risk_increase",
                "explanation": "Ani darbe/çarpma tespit edildi",
            })

        hr = vitals.get("heart_rate", 75)
        if hr < self.thresholds["hr_low"]:
            contributions.append({
                "feature": "bradycardia",
                "importance": 0.7,
                "direction": "risk_increase",
                "explanation": f"Düşük nabız ({hr} bpm) - bradikardi riski",
            })
        elif hr > self.thresholds["hr_high"]:
            contributions.append({
                "feature": "tachycardia",
                "importance": 0.5,
                "direction": "risk_increase",
                "explanation": f"Yüksek nabız ({hr} bpm) - taşikardi",
            })

        spo2 = vitals.get("spo2", 98)
        if spo2 < self.thresholds["spo2_low"]:
            contributions.append({
                "feature": "hypoxemia",
                "importance": 0.8,
                "direction": "risk_increase",
                "explanation": f"Düşük oksijen satürasyonu ({spo2}%)",
            })

        quality = predictions.get("quality_score", 1.0)
        if quality < 0.3:
            contributions.append({
                "feature": "signal_quality",
                "importance": 0.4,
                "direction": "confidence_decrease",
                "explanation": "Düşük sinyal kalitesi - sonuçlar güvenilir olmayabilir",
            })

        # Sort by importance
        contributions.sort(key=lambda x: x["importance"], reverse=True)

        # Summary
        if not contributions:
            summary = "Tüm parametreler normal sınırlarda. Risk tespit edilmedi."
        else:
            top = contributions[0]
            summary = f"En önemli faktör: {top['explanation']}"

        return {
            "contributions": contributions,
            "summary": summary,
            "n_risk_factors": len([c for c in contributions if c["direction"] == "risk_increase"]),
        }
