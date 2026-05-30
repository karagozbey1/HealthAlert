import '../models/live_status.dart';
import 'api_client.dart';
import 'package:flutter/foundation.dart';

/// Sağlık asistanı özet, trend ve alarm açıklama verilerini hazırlar.
class HealthAssistantService {
  HealthAssistantService({this.apiClient});

  final ApiClient? apiClient;

  /// Canlı veriye göre backend veya yerel sağlık asistanı özeti üretir.
  Future<AssistantSummary> getSummary({
    LiveStatus? liveStatus,
    String? userId,
    String role = 'SELF',
    bool isBackendMode = false,
  }) async {
    if (isBackendMode && apiClient != null) {
      try {
        final path = userId != null
            ? '/assistant/summary?user_id=$userId'
            : '/assistant/summary';
        final data = await apiClient!.get(path) as Map<String, dynamic>;
        return AssistantSummary.fromJson(data);
      } catch (error) {
        debugPrint('[HealthAssistantService] Summary load failed: $error');
      }
    }

    return _generateLocalSummary(liveStatus, role);
  }

  /// Alarm için backend veya yerel açıklama ve aksiyon önerisi üretir.
  Future<AlertExplanation> explainAlert({
    required String alertId,
    required String alertTitle,
    required String alertDescription,
    required String severity,
    required String status,
    LiveStatus? liveStatus,
    bool isBackendMode = false,
  }) async {
    if (isBackendMode && apiClient != null) {
      try {
        final data =
            await apiClient!.get('/assistant/alert-explanation/$alertId')
                as Map<String, dynamic>;
        return AlertExplanation.fromJson(data);
      } catch (error) {
        debugPrint(
            '[HealthAssistantService] Alert explanation load failed: $error');
      }
    }

    return _generateLocalAlertExplanation(
      alertTitle,
      alertDescription,
      severity,
      status,
      liveStatus,
    );
  }

  /// Günlük sağlık özetini backend'den getirir veya boş yerel özet döndürür.
  Future<DailySummary> getDailySummary({
    String? userId,
    String role = 'SELF',
    bool isBackendMode = false,
  }) async {
    if (isBackendMode && apiClient != null) {
      try {
        final path = userId != null
            ? '/assistant/daily-summary?user_id=$userId'
            : '/assistant/daily-summary';
        final data = await apiClient!.get(path) as Map<String, dynamic>;
        return DailySummary.fromJson(data);
      } catch (error) {
        debugPrint(
            '[HealthAssistantService] Daily summary load failed: $error');
      }
    }

    return DailySummary(
      summary: 'Günlük veri özeti için yeterli veri bulunmuyor.',
      overallStatus: 'veri_yetersiz',
      anomalyCount: 0,
      alertCount: 0,
      hasLiveData: false,
    );
  }

  /// Canlı sağlık trendini backend'den getirir veya yerel olarak hesaplar.
  Future<TrendAnalysis> getTrends({
    String? userId,
    String role = 'SELF',
    bool isBackendMode = false,
    LiveStatus? liveStatus,
  }) async {
    if (isBackendMode && apiClient != null) {
      try {
        final path = userId != null
            ? '/assistant/trends?user_id=$userId'
            : '/assistant/trends';
        final data = await apiClient!.get(path) as Map<String, dynamic>;
        return TrendAnalysis.fromJson(data);
      } catch (error) {
        debugPrint('[HealthAssistantService] Trends load failed: $error');
      }
    }

    return _generateLocalTrend(liveStatus);
  }

  /// Mevcut canlı veriden senkron trend analizi üretir.
  TrendAnalysis getTrendSync(LiveStatus? live) => _generateLocalTrend(live);

  /// Canlı veriden güvenli yerel sağlık özeti ve öneri listesi üretir.
  AssistantSummary _generateLocalSummary(LiveStatus? live, String role) {
    if (live == null) {
      return AssistantSummary(
        summary:
            'Yeterli canlı veri bulunmadığı için genel öneri gösteriliyor.',
        recommendations: [
          const AssistantRecommendation(
            title: 'Cihaz Bağlantısı',
            action: 'Sensörünüzü takın ve uygulamayı yenileyin.',
            urgency: 'info',
          ),
        ],
        reasoning: [],
        riskLevel: 'unknown',
        confidence: 'low',
      );
    }

    final recs = <AssistantRecommendation>[];
    final reasoning = <String>[];
    final summaryLines = <String>[];
    String riskLevel = 'normal';

    if (live.riskScore > 0.8) {
      riskLevel = 'critical';
      summaryLines.add('Kritik risk seviyesi tespit edildi.');
      reasoning.add(
          'Risk skoru %${(live.riskScore * 100).toStringAsFixed(0)} ile kritik eşiğin üzerinde.');
      recs.add(const AssistantRecommendation(
        title: 'Acil Durum',
        action: 'Bulunduğunuz yerde kalın. Gerekiyorsa acil yardım isteyin.',
        urgency: 'critical',
      ));
    } else if (live.riskScore > 0.6) {
      riskLevel = 'warning';
      summaryLines.add('Uyarı seviyesinde risk algılandı.');
      reasoning.add(
          'Risk skoru %${(live.riskScore * 100).toStringAsFixed(0)} ile uyarı bölgesinde.');
      recs.add(const AssistantRecommendation(
        title: 'Dikkat',
        action: 'Oturun ve sakin olun. Vital değerlerinizi izleyin.',
        urgency: 'warning',
      ));
    } else if (live.riskScore > 0.3) {
      riskLevel = 'watch';
      summaryLines.add('Bazı değerler izlem gerektiriyor.');
    } else {
      summaryLines.add('Genel durumunuz stabil görünüyor.');
    }

    if (live.heartRate > 130) {
      summaryLines
          .add('Nabız ${live.heartRate.toStringAsFixed(0)} bpm — çok yüksek.');
      reasoning.add('Nabız 130 bpm üzerinde.');
      recs.add(const AssistantRecommendation(
        title: 'Yüksek Nabız',
        action: 'Dinlenin, derin nefes alın.',
        urgency: 'critical',
      ));
    } else if (live.heartRate > 100) {
      summaryLines
          .add('Nabız ${live.heartRate.toStringAsFixed(0)} bpm — yüksek.');
      reasoning.add('Nabız normal üst sınırın üzerinde.');
      recs.add(const AssistantRecommendation(
        title: 'Yükselen Nabız',
        action: 'Fiziksel aktiviteyi azaltın, su için.',
        urgency: 'warning',
      ));
    } else if (live.heartRate < 50) {
      summaryLines
          .add('Nabız ${live.heartRate.toStringAsFixed(0)} bpm — düşük.');
      recs.add(const AssistantRecommendation(
        title: 'Düşük Nabız',
        action: 'Dinlenin. Belirtiler devam ederse doktorunuza bildirin.',
        urgency: 'warning',
      ));
    }

    if (live.spo2 < 90) {
      summaryLines
          .add('Oksijen doygunluğu %${live.spo2.toStringAsFixed(1)} — kritik.');
      reasoning.add('SpO2 %90 altında.');
      recs.add(const AssistantRecommendation(
        title: 'Kritik Oksijen',
        action:
            'Oturarak dinlenin ve derin nefes alın. Doktorunuza derhal haber verin.',
        urgency: 'critical',
      ));
    } else if (live.spo2 < 94) {
      summaryLines
          .add('Oksijen doygunluğu %${live.spo2.toStringAsFixed(1)} — düşük.');
      recs.add(const AssistantRecommendation(
        title: 'Düşük Oksijen',
        action: 'Oturarak dinlenin ve tekrar ölçüm bekleyin.',
        urgency: 'warning',
      ));
    }

    if (live.motionScore > 0.75) {
      summaryLines.add('Hareket dengesizliği tespit edildi.');
      recs.add(const AssistantRecommendation(
        title: 'Hareket Uyarısı',
        action: 'Ani hareketlerden kaçının. Oturmaya çalışın.',
        urgency: 'warning',
      ));
    }

    if (recs.isEmpty) {
      recs.add(const AssistantRecommendation(
        title: 'Durum Stabil',
        action: 'Günlük takibe devam edin.',
        urgency: 'normal',
      ));
    }

    final rolePrefix = role == 'RELATIVE'
        ? 'İzlediğiniz kişi için: '
        : role == 'DOCTOR'
            ? 'Hastanız için: '
            : '';

    return AssistantSummary(
      summary: '$rolePrefix${summaryLines.join(' ')}',
      recommendations: recs,
      reasoning: reasoning,
      riskLevel: riskLevel,
      confidence: 'high',
    );
  }

  /// Alarm bilgisi ve canlı ölçümlerden yerel açıklama üretir.
  AlertExplanation _generateLocalAlertExplanation(
    String title,
    String description,
    String severity,
    String status,
    LiveStatus? live,
  ) {
    final lines = <String>[];
    final actions = <String>[];

    lines.add("'$title' alarmı tetiklendi.");
    if (description.isNotEmpty) lines.add('Neden: $description');

    if (severity == 'critical') {
      lines.add('Bu alarm kritik seviyededir ve acil dikkat gerektirir.');
      actions
          .add('Bulunduğunuz yerde kalın ve gerekiyorsa acil yardım isteyin.');
      actions.add('Yakınlarınız otomatik olarak bilgilendirilmektedir.');
    } else if (severity == 'warning') {
      lines.add('Bu alarm uyarı seviyesindedir.');
      actions.add('Oturun ve sakin olun. Vital değerlerinizi izleyin.');
      actions.add('Belirtiler devam ederse yakınlarınıza haber verin.');
    } else {
      lines.add('Bu alarm izleme seviyesindedir.');
      actions.add('Normal aktivitelerinize dikkatli devam edebilirsiniz.');
    }

    final statusLabels = {
      'countdown': 'Geri sayım devam ediyor.',
      'acknowledged': 'Kullanıcı durumu onayladı.',
      'escalated': 'Acil yardım istendi.',
      'post_event_monitoring': 'Olay sonrası izleme aktif.',
      'resolved': 'Alarm çözüldü.',
      'closed': 'Alarm kapatıldı.',
    };
    if (statusLabels.containsKey(status)) {
      lines.add(statusLabels[status]!);
    }

    if (live != null) {
      lines.add('Güncel nabız: ${live.heartRate.toStringAsFixed(0)} bpm');
      lines.add('Güncel oksijen: %${live.spo2.toStringAsFixed(1)}');
    }

    return AlertExplanation(
      explanation: lines.join(' '),
      suggestedActions: actions,
      severity: severity,
      status: status,
    );
  }

  /// Canlı risk skoruna göre yerel trend etiketi ve özetini üretir.
  TrendAnalysis _generateLocalTrend(LiveStatus? live) {
    if (live == null) {
      return const TrendAnalysis(
        trendLabel: 'veri_yetersiz',
        trendLabelTr: 'Veri Yetersiz',
        summary: 'Trend analizi için yeterli veri bulunmuyor.',
        hasSufficientData: false,
      );
    }

    String label;
    String labelTr;
    String summary;

    if (live.riskScore > 0.6) {
      label = 'artan_risk';
      labelTr = 'Artan Risk';
      summary = 'Risk skoru yüksek seyrediyor. Dikkatli olun.';
    } else if (live.riskScore > 0.3) {
      label = 'izlem_gerektiren';
      labelTr = 'İzlem Gerektiren';
      summary = 'Bazı değerler normal üst sınıra yakın.';
    } else {
      label = 'stabil';
      labelTr = 'Stabil';
      summary = 'Değerler normal aralıkta seyrediyor.';
    }

    return TrendAnalysis(
      trendLabel: label,
      trendLabelTr: labelTr,
      summary: summary,
      hasSufficientData: true,
    );
  }
}

/// Sağlık asistanı özetini öneri, gerekçe ve risk bilgileriyle taşır.
class AssistantSummary {
  final String summary;
  final List<AssistantRecommendation> recommendations;
  final List<String> reasoning;
  final String riskLevel;
  final String confidence;
  final String disclaimer;

  const AssistantSummary({
    required this.summary,
    required this.recommendations,
    required this.reasoning,
    required this.riskLevel,
    required this.confidence,
    this.disclaimer =
        'Bu bilgiler sensör verileri ve algoritmalar tarafından otomatik üretilmiştir. Kesin tıbbi teşhis yerine geçmez.',
  });

  factory AssistantSummary.fromJson(Map<String, dynamic> json) {
    return AssistantSummary(
      summary: json['summary'] as String? ?? '',
      recommendations: (json['recommendations'] as List<dynamic>?)
              ?.map((e) =>
                  AssistantRecommendation.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      reasoning: (json['reasoning'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      riskLevel: json['risk_level'] as String? ?? 'unknown',
      confidence: json['confidence'] as String? ?? 'low',
      disclaimer: json['disclaimer'] as String? ?? '',
    );
  }
}

/// Asistanın kullanıcıya göstereceği kısa öneri aksiyonunu taşır.
class AssistantRecommendation {
  final String title;
  final String action;
  final String urgency;

  const AssistantRecommendation({
    required this.title,
    required this.action,
    required this.urgency,
  });

  factory AssistantRecommendation.fromJson(Map<String, dynamic> json) {
    return AssistantRecommendation(
      title: json['title'] as String? ?? '',
      action: json['action'] as String? ?? '',
      urgency: json['urgency'] as String? ?? 'info',
    );
  }
}

/// Alarm açıklamasını önerilen aksiyonlar ve durum bilgisiyle taşır.
class AlertExplanation {
  final String explanation;
  final List<String> suggestedActions;
  final String severity;
  final String status;
  final String disclaimer;

  const AlertExplanation({
    required this.explanation,
    required this.suggestedActions,
    required this.severity,
    required this.status,
    this.disclaimer =
        'Bu bilgiler sensör verileri ve algoritmalar tarafından otomatik üretilmiştir. Kesin tıbbi teşhis yerine geçmez.',
  });

  factory AlertExplanation.fromJson(Map<String, dynamic> json) {
    return AlertExplanation(
      explanation: json['explanation'] as String? ?? '',
      suggestedActions: (json['suggested_actions'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      severity: json['severity'] as String? ?? 'normal',
      status: json['status'] as String? ?? 'unknown',
      disclaimer: json['disclaimer'] as String? ?? '',
    );
  }
}

/// Günlük sağlık özetini alarm, anomali ve veri durumu alanlarıyla taşır.
class DailySummary {
  final String summary;
  final String overallStatus;
  final int anomalyCount;
  final int alertCount;
  final bool hasLiveData;

  const DailySummary({
    required this.summary,
    required this.overallStatus,
    required this.anomalyCount,
    required this.alertCount,
    required this.hasLiveData,
  });

  factory DailySummary.fromJson(Map<String, dynamic> json) {
    return DailySummary(
      summary: json['summary'] as String? ?? '',
      overallStatus: json['overall_status'] as String? ?? 'unknown',
      anomalyCount: json['anomaly_count'] as int? ?? 0,
      alertCount: json['alert_count'] as int? ?? 0,
      hasLiveData: json['has_live_data'] as bool? ?? false,
    );
  }
}

/// Canlı veriden üretilen trend etiketini ve özetini taşır.
class TrendAnalysis {
  final String trendLabel;
  final String trendLabelTr;
  final String summary;
  final bool hasSufficientData;
  final String? topConcern;

  const TrendAnalysis({
    required this.trendLabel,
    required this.trendLabelTr,
    required this.summary,
    required this.hasSufficientData,
    this.topConcern,
  });

  factory TrendAnalysis.fromJson(Map<String, dynamic> json) {
    final label = json['trend_label'] as String? ?? 'unknown';
    final labelsTr = {
      'artan_risk': 'Artan Risk',
      'stabil': 'Stabil',
      'iyilesiyor': 'İyileşiyor',
      'izlem_gerektiren': 'İzlem Gerektiren',
      'olcum_kalitesi_dusuk': 'Ölçüm Kalitesi Düşük',
      'veri_yetersiz': 'Veri Yetersiz',
    };
    return TrendAnalysis(
      trendLabel: label,
      trendLabelTr: labelsTr[label] ?? label,
      summary: json['summary'] as String? ?? '',
      hasSufficientData: json['has_sufficient_data'] as bool? ?? false,
      topConcern: json['top_concern'] as String?,
    );
  }
}
