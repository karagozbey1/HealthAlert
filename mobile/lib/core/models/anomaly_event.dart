import 'enums.dart';

class AnomalyEvent {
  const AnomalyEvent({
    required this.id,
    required this.metric,
    required this.value,
    required this.unit,
    required this.severity,
    required this.detectedAt,
    required this.summary,
    this.userId,
  });

  final String id;
  final String? userId;
  final String metric;
  final double value;
  final String unit;
  final AlertSeverity severity;
  final DateTime detectedAt;
  final String summary;

  static AnomalyEvent fromJson(Map<String, dynamic> json) => AnomalyEvent(
        id: json['id'] as String,
        userId: json['user_id'] as String?,
        metric: json['metric'] as String? ?? '',
        value: (json['value'] as num?)?.toDouble() ?? 0,
        unit: json['unit'] as String? ?? '',
        severity: AlertSeverity.values.firstWhere(
          (e) => e.name == (json['severity'] as String?)?.toLowerCase(),
          orElse: () => AlertSeverity.normal,
        ),
        detectedAt: json['detected_at'] != null
            ? DateTime.parse(json['detected_at'] as String)
            : DateTime.now(),
        summary: json['summary'] as String? ?? '',
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'user_id': userId,
        'metric': metric,
        'value': value,
        'unit': unit,
        'severity': severity.name,
        'detected_at': detectedAt.toIso8601String(),
        'summary': summary,
      };
}
