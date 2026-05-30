import 'dart:convert';

import 'enums.dart';

/// Uygulamadaki ilgili olay bilgisini taşır.
class AlertEvent {
  const AlertEvent({
    required this.id,
    required this.title,
    required this.description,
    required this.severity,
    required this.status,
    required this.createdAt,
    required this.countdownTotalSec,
    required this.countdownRemainingSec,
    required this.recommendations,
    required this.relatedAnomalyId,
    this.userId,
    this.resolvedAt,
  });

  final String id;
  final String? userId;
  final String title;
  final String description;
  final AlertSeverity severity;
  final AlertLifecycleStatus status;
  final DateTime createdAt;
  final int countdownTotalSec;
  final int countdownRemainingSec;
  final List<String> recommendations;
  final String? relatedAnomalyId;
  final DateTime? resolvedAt;

  bool get isActive => status != AlertLifecycleStatus.closed;

  /// Modelin seçilen alanları değişmiş yeni bir kopyasını üretir.
  AlertEvent copyWith({
    AlertSeverity? severity,
    AlertLifecycleStatus? status,
    int? countdownRemainingSec,
    List<String>? recommendations,
  }) {
    return AlertEvent(
      id: id,
      userId: userId,
      title: title,
      description: description,
      severity: severity ?? this.severity,
      status: status ?? this.status,
      createdAt: createdAt,
      countdownTotalSec: countdownTotalSec,
      countdownRemainingSec:
          countdownRemainingSec ?? this.countdownRemainingSec,
      recommendations: recommendations ?? this.recommendations,
      relatedAnomalyId: relatedAnomalyId,
      resolvedAt: resolvedAt,
    );
  }

  /// Gelen ham veriyi uygulamanın beklediği tipe güvenli şekilde çevirir.
  static AlertLifecycleStatus _parseStatus(String? s) {
    switch (s?.toLowerCase()) {
      case 'raised':
        return AlertLifecycleStatus.raised;
      case 'countdown':
        return AlertLifecycleStatus.countdown;
      case 'acknowledged':
        return AlertLifecycleStatus.acknowledged;
      case 'escalated':
        return AlertLifecycleStatus.emergencyRequested;
      case 'post_event_monitoring':
        return AlertLifecycleStatus.postEventMonitoring;
      case 'resolved':
        return AlertLifecycleStatus.closed;
      default:
        return AlertLifecycleStatus.raised;
    }
  }

  /// Gelen ham veriyi uygulamanın beklediği tipe güvenli şekilde çevirir.
  static AlertSeverity _parseSeverity(String? s) {
    return AlertSeverity.values.firstWhere(
      (e) => e.name == s?.toLowerCase(),
      orElse: () => AlertSeverity.normal,
    );
  }

  /// API, BLE veya Firestore verisini uygulama modeline dönüştürür.
  static AlertEvent fromJson(Map<String, dynamic> json) {
    final recsRaw = json['recommendations'];
    List<String> recs = const [];
    if (recsRaw is List) {
      recs = recsRaw.cast<String>();
    } else if (recsRaw is String) {
      try {
        recs = (jsonDecode(recsRaw) as List<dynamic>).cast<String>();
      } catch (_) {}
    }
    return AlertEvent(
      id: json['id'] as String,
      userId: json['user_id'] as String?,
      title: json['title'] as String? ?? '',
      description: json['description'] as String? ?? '',
      severity: _parseSeverity(json['severity'] as String?),
      status: _parseStatus(json['status'] as String?),
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'] as String)
          : DateTime.now(),
      countdownTotalSec: json['countdown_total_sec'] as int? ?? 30,
      countdownRemainingSec: json['countdown_remaining_sec'] as int? ?? 30,
      recommendations: recs,
      relatedAnomalyId: json['related_anomaly_id'] as String?,
      resolvedAt: json['resolved_at'] != null
          ? DateTime.parse(json['resolved_at'] as String)
          : null,
    );
  }

  /// Uygulama modelini API veya Firestore payload formatına dönüştürür.
  Map<String, dynamic> toJson() => {
        'id': id,
        'user_id': userId,
        'title': title,
        'description': description,
        'severity': severity.name,
        'status': status.name,
        'created_at': createdAt.toIso8601String(),
        'countdown_total_sec': countdownTotalSec,
        'countdown_remaining_sec': countdownRemainingSec,
        'recommendations': recommendations,
        'related_anomaly_id': relatedAnomalyId,
        'resolved_at': resolvedAt?.toIso8601String(),
      };
}
