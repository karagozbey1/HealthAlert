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
    this.finalRiskScore,
    this.personalizedRiskScore,
    this.mlEvidenceScore,
    this.mlAdjustment,
    this.fusionApplied,
    this.modelWindowStatus,
  });

  final String id;
  final String userId;
  final double heartRate;
  final double spo2;
  final double motionScore;
  final double riskScore;
  final String scenario;
  final DateTime timestamp;
  final double? finalRiskScore;
  final double? personalizedRiskScore;
  final double? mlEvidenceScore;
  final double? mlAdjustment;
  final bool? fusionApplied;
  final String? modelWindowStatus;

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
        finalRiskScore: (json['final_risk_score'] as num?)?.toDouble(),
        personalizedRiskScore:
            (json['personalized_risk_score'] as num?)?.toDouble(),
        mlEvidenceScore: (json['ml_evidence_score'] as num?)?.toDouble(),
        mlAdjustment: (json['ml_adjustment'] as num?)?.toDouble(),
        fusionApplied: json['fusion_applied'] as bool?,
        modelWindowStatus: json['model_window_status'] != null
            ? json['model_window_status'].toString()
            : null,
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
