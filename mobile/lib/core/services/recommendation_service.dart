import '../models/enums.dart';
import '../models/live_status.dart';

/// Alarm şiddetine uygun kullanıcı önerilerini seçer.
class RecommendationService {
  /// Alarm şiddetine uygun öneri metinlerini döndürür.
  List<String> forSeverity(AlertSeverity severity) {
    switch (severity) {
      case AlertSeverity.normal:
        return const ['İzlemeye devam edin. Değerleriniz normal aralıkta.'];
      case AlertSeverity.watch:
        return const [
          '5-10 dakika boyunca fiziksel aktiviteyi azaltın.',
          'Su için ve vital değerlerinizi tekrar kontrol edin.',
        ];
      case AlertSeverity.warning:
        return const [
          'Oturun ve sakin kalmaya çalışın.',
          'Nabzınızı ve oksijen seviyenizi 2 dakika boyunca izleyin.',
          'Belirtiler sürerse yakınınıza veya bakım verenize ulaşın.',
        ];
      case AlertSeverity.critical:
        return const [
          'Acil durum riski tespit edildi.',
          'Bulunduğunuz yerde kalın ve yardım için bekleyin.',
          'Bilinciniz yerindeyse şimdi Acil butona basın.',
        ];
    }
  }

  /// Canlı sağlık verisiyle ilgili okuma veya güncelleme işlemini yürütür.
  List<Recommendation> forLiveStatus(LiveStatus? live) {
    if (live == null) {
      return [
        Recommendation(
          title: 'Sensör Bağlantısı Bekleniyor',
          detail: 'Cihaz bağlantısı kurulduğunda verileriniz görünecek.',
          urgency: RecommendationUrgency.info,
          action: 'Cihazı takın ve uygulamayı yenileyin.',
        ),
      ];
    }

    final recs = <Recommendation>[];

    if (live.heartRate > 110) {
      recs.add(Recommendation(
        title: 'Yüksek Nabız',
        detail:
            'Nabzınız ${live.heartRate.toStringAsFixed(0)} bpm ile yüksek görünüyor.',
        urgency: live.heartRate > 130
            ? RecommendationUrgency.critical
            : RecommendationUrgency.warning,
        action:
            'Oturun, derin nefes alın. Birkaç dakika içinde tekrar kontrol edin.',
      ));
    } else if (live.heartRate < 50) {
      recs.add(Recommendation(
        title: 'Düşük Nabız',
        detail:
            'Nabzınız ${live.heartRate.toStringAsFixed(0)} bpm ile düşük görünüyor.',
        urgency: RecommendationUrgency.warning,
        action:
            'Dinlenin. Belirtiler devam ederse sağlık görevlisine bildirin.',
      ));
    }

    if (live.spo2 < 90) {
      recs.add(Recommendation(
        title: 'Kritik Oksijen Düzeyi',
        detail:
            'Oksijen doygunluğu %${live.spo2.toStringAsFixed(1)} ile kritik seviyede düşük.',
        urgency: RecommendationUrgency.critical,
        action:
            'Oturarak dinlenin ve derin nefes alın. Yakınınıza veya doktorunuza derhal haber verin.',
      ));
    } else if (live.spo2 < 94) {
      recs.add(Recommendation(
        title: 'Düşük Oksijen Seviyesi',
        detail:
            'Oksijen doygunluğu %${live.spo2.toStringAsFixed(1)} — normal altında.',
        urgency: RecommendationUrgency.warning,
        action: 'Oturarak dinlenin ve değerleri tekrar kontrol edin.',
      ));
    }

    if (live.motionScore > 0.75) {
      recs.add(Recommendation(
        title: 'Hareket Dengesizliği',
        detail:
            'Hareket sensörü yüksek dengesizlik algıladı (${(live.motionScore * 100).toStringAsFixed(0)}%).',
        urgency: RecommendationUrgency.warning,
        action: 'Ani hareketlerden kaçının. Oturmaya çalışın.',
      ));
    }

    if (live.riskScore > 0.7 && recs.isEmpty) {
      recs.add(Recommendation(
        title: 'Yüksek Risk Skoru',
        detail:
            'Genel risk skoru %${(live.riskScore * 100).toStringAsFixed(0)} — dikkat gerektirir.',
        urgency: RecommendationUrgency.warning,
        action: 'Dinlenin ve değerlerin düzelmesini bekleyin.',
      ));
    }

    if (live.scenario == 'critical') {
      recs.insert(
          0,
          Recommendation(
            title: 'Kritik Risk Algılandı',
            detail: 'Sistem kritik risk senaryosu tespit etti.',
            urgency: RecommendationUrgency.critical,
            action: 'Bulunduğunuz yerde kalın ve yardım isteyin.',
          ));
    }

    if (recs.isEmpty) {
      recs.add(Recommendation(
        title: 'Değerleriniz Normal',
        detail: 'Şu an tüm vital veriler normal aralıkta.',
        urgency: RecommendationUrgency.normal,
        action: 'Takibe devam edin.',
      ));
    }

    return recs;
  }
}

/// HealthAlert içinde bu dosyanın ana sorumluluğunu taşıyan yapıdır.
enum RecommendationUrgency { normal, info, warning, critical }

/// HealthAlert içinde bu dosyanın ana sorumluluğunu taşıyan yapıdır.
class Recommendation {
  final String title;
  final String detail;
  final RecommendationUrgency urgency;
  final String action;

  const Recommendation({
    required this.title,
    required this.detail,
    required this.urgency,
    required this.action,
  });
}
