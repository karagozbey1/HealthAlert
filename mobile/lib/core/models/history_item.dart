import 'enums.dart';

/// Mobil uygulamada kullanılan ilgili veri modelini temsil eder.
class HistoryItem {
  const HistoryItem({
    required this.id,
    required this.type,
    required this.title,
    required this.subtitle,
    required this.timestamp,
    required this.severity,
  });

  final String id;
  final HistoryItemType type;
  final String title;
  final String subtitle;
  final DateTime timestamp;
  final AlertSeverity severity;

  /// Uygulama modelini API veya Firestore payload formatına dönüştürür.
  Map<String, dynamic> toJson() => {
        'id': id,
        'type': type.name,
        'title': title,
        'subtitle': subtitle,
        'timestamp': timestamp.toIso8601String(),
        'severity': severity.name,
      };

  /// API, BLE veya Firestore verisini uygulama modeline dönüştürür.
  static HistoryItem fromJson(Map<String, dynamic> json) => HistoryItem(
        id: json['id'] as String,
        type: HistoryItemType.values.firstWhere(
          (e) =>
              e.name ==
              (json['item_type'] ?? json['type'] as String?)
                  ?.toString()
                  .toLowerCase(),
          orElse: () => HistoryItemType.status,
        ),
        title: json['title'] as String? ?? '',
        subtitle: json['subtitle'] as String? ?? '',
        timestamp: json['timestamp'] != null
            ? DateTime.parse(json['timestamp'] as String)
            : DateTime.now(),
        severity: AlertSeverity.values.firstWhere(
          (e) => e.name == (json['severity'] as String?)?.toLowerCase(),
          orElse: () => AlertSeverity.normal,
        ),
      );
}
