from typing import Dict, List


# Risk seviyesine gore varsayilan onerileri tutar.
DEFAULT_RECOMMENDATIONS = {
    "critical": [
        "DÜŞME RİSKİ ÇOK YÜKSEK - Acil müdahale gerekebilir",
        "Yakın kişilere otomatik bildirim gönderildi",
        "Hareket etmeyin, yardım bekleniyor",
        "112 aranması önerilir",
    ],
    "warning": [
        "Dengesizlik tespit edildi - Dikkatli olun",
        "Nabız/SpO2 değerleri anormal - Dinlenin",
        "Oturmanız veya güvenli bir yere geçmeniz önerilir",
        "Yakın kişiler bilgilendirilecek",
    ],
    "watch": [
        "Hafif dengesizlik belirtileri - İzleniyor",
        "Vital değerler normal sınırlarda",
        "Aktivitenize devam edebilirsiniz",
        "Düzenli kontrol önerilir",
    ],
    "normal": [
        "Tüm değerler normal",
        "Sistem aktif olarak izliyor",
        "Herhangi bir risk tespit edilmedi",
    ],
}


# Risk sonucuna gore kullanici onerileri uretir.
class RecommendationEngine:

    # Ozellestirilmis oneriler verilmezse varsayilan seti kullanir.
    def __init__(self, custom_recommendations: Dict[str, List[str]] = None):
        self.recommendations = custom_recommendations or DEFAULT_RECOMMENDATIONS

    def get_recommendations(
        self,
        risk_assessment: Dict,
    ) -> List[str]:
        risk_level = risk_assessment.get("final_risk_level", "normal")
        base_recs = self.recommendations.get(risk_level, self.recommendations["normal"])

        # Risk seviyesine uygun temel onerileri kopyalar.
        recs = list(base_recs)

        # Sinyal kalitesi dustugunde ek yonlendirme ekler.
        quality = risk_assessment.get("ppg_quality_score", 1.0)
        if quality < 0.3:
            recs.append("Sensör teması kontrol edilmeli - sinyal kalitesi düşük")
        elif quality < 0.5:
            recs.append("Sensör konumunu kontrol edin")

        return recs
