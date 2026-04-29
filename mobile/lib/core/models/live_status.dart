class LiveStatus {
  const LiveStatus({
    required this.id,
    required this.userId,
    required this.heartRate,
    required this.spo2,
    required this.motionScore,
    required this.riskScore,
    required this.scenario,
    required this.timestamp,
  });

  final String id;
  final String userId;
  final double heartRate;
  final double spo2;
  final double motionScore;
  final double riskScore;
  final String scenario;
  final DateTime timestamp;

  static LiveStatus fromJson(Map<String, dynamic> json) => LiveStatus(
        id: json['id'] as String? ?? '',
        userId: json['user_id'] as String? ?? '',
        heartRate: (json['heart_rate'] as num?)?.toDouble() ?? 72,
        spo2: (json['spo2'] as num?)?.toDouble() ?? 98,
        motionScore: (json['motion_score'] as num?)?.toDouble() ?? 0.1,
        riskScore: (json['risk_score'] as num?)?.toDouble() ?? 0.05,
        scenario: json['scenario'] as String? ?? 'normal',
        timestamp: json['timestamp'] != null
            ? DateTime.parse(json['timestamp'] as String)
            : DateTime.now(),
      );

  String get scenarioLabel {
    switch (scenario) {
      case 'elevated_hr':
        return 'Yüksek Nabız';
      case 'low_spo2':
        return 'Düşük SpO₂';
      case 'warning':
        return 'Uyarı';
      case 'critical':
        return 'Kritik';
      case 'recovery':
        return 'Toparlanma';
      default:
        return 'Normal';
    }
  }

  bool get isAlert => scenario == 'warning' || scenario == 'critical';
}
