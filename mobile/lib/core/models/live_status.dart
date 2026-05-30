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
    this.mlBaseScore,
    this.personalAdjustment,
    this.fusionMode,
    this.modelVersion,
    this.mlConfidence,
    this.signalQuality,
    this.fingerPresent,
    this.heartRateValid,
    this.spo2Valid,
    this.accelX,
    this.accelY,
    this.accelZ,
    this.gyroX,
    this.gyroY,
    this.gyroZ,
    this.accTotal,
    this.gyroTotal,
    this.irValue,
    this.redValue,
    this.perfusionIndex,
    this.rRatio,
    this.irRangePercent,
    this.source,
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
  final double? mlBaseScore;
  final double? personalAdjustment;
  final String? fusionMode;
  final String? modelVersion;
  final double? mlConfidence;
  final double? signalQuality;
  final bool? fingerPresent;
  final bool? heartRateValid;
  final bool? spo2Valid;
  final double? accelX;
  final double? accelY;
  final double? accelZ;
  final double? gyroX;
  final double? gyroY;
  final double? gyroZ;
  final double? accTotal;
  final double? gyroTotal;
  final int? irValue;
  final int? redValue;
  final double? perfusionIndex;
  final double? rRatio;
  final double? irRangePercent;
  final String? source;

  static LiveStatus fromJson(Map<String, dynamic> json) => LiveStatus(
        id: json['id'] as String? ?? '',
        userId: json['user_id'] as String? ?? '',
        heartRate: (json['heart_rate'] as num?)?.toDouble() ?? 0,
        spo2: (json['spo2'] as num?)?.toDouble() ?? 0,
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
        modelWindowStatus: (json['model_window_status'])?.toString(),
        mlBaseScore: (json['ml_base_score'] as num?)?.toDouble(),
        personalAdjustment: (json['personal_adjustment'] as num?)?.toDouble(),
        fusionMode: json['fusion_mode'] as String?,
        modelVersion: json['model_version'] as String?,
        mlConfidence: (json['ml_confidence'] as num?)?.toDouble(),
        signalQuality: (json['signal_quality'] as num?)?.toDouble(),
        fingerPresent: (json['finger_present'] as bool?) ??
            (json['finger_detected'] as bool?),
        heartRateValid: json['hr_valid'] as bool? ?? json['bpm_valid'] as bool?,
        spo2Valid: json['spo2_valid'] as bool?,
        accelX: (json['accel_x'] as num?)?.toDouble(),
        accelY: (json['accel_y'] as num?)?.toDouble(),
        accelZ: (json['accel_z'] as num?)?.toDouble(),
        gyroX: (json['gyro_x'] as num?)?.toDouble(),
        gyroY: (json['gyro_y'] as num?)?.toDouble(),
        gyroZ: (json['gyro_z'] as num?)?.toDouble(),
        accTotal: (json['acc_total'] as num?)?.toDouble(),
        gyroTotal: (json['gyro_total'] as num?)?.toDouble(),
        irValue: (json['ir_value'] as num?)?.toInt(),
        redValue: (json['red_value'] as num?)?.toInt(),
        perfusionIndex: (json['pi_percent'] as num?)?.toDouble(),
        rRatio: (json['r_ratio'] as num?)?.toDouble(),
        irRangePercent: (json['ir_range_percent'] as num?)?.toDouble(),
        source: json['source'] as String?,
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
      case 'ble_live':
        return 'BLE Canlı';
      default:
        return 'Normal';
    }
  }

  bool get isAlert => scenario == 'warning' || scenario == 'critical';

  /// Creates a copy of this LiveStatus with selected fields replaced.
  /// Only the fields used for BLE enrichment are exposed; all others are
  /// carried over unchanged.
  LiveStatus copyWith({
    double? heartRate,
    bool? heartRateValid,
    double? spo2,
    bool? spo2Valid,
    double? motionScore,
    double? riskScore,
    String? source,
  }) =>
      LiveStatus(
        id: id,
        userId: userId,
        heartRate: heartRate ?? this.heartRate,
        spo2: spo2 ?? this.spo2,
        motionScore: motionScore ?? this.motionScore,
        riskScore: riskScore ?? this.riskScore,
        scenario: scenario,
        timestamp: timestamp,
        heartRateValid: heartRateValid ?? this.heartRateValid,
        spo2Valid: spo2Valid ?? this.spo2Valid,
        finalRiskScore: finalRiskScore,
        personalizedRiskScore: personalizedRiskScore,
        mlEvidenceScore: mlEvidenceScore,
        mlAdjustment: mlAdjustment,
        fusionApplied: fusionApplied,
        modelWindowStatus: modelWindowStatus,
        mlBaseScore: mlBaseScore,
        personalAdjustment: personalAdjustment,
        fusionMode: fusionMode,
        modelVersion: modelVersion,
        mlConfidence: mlConfidence,
        signalQuality: signalQuality,
        fingerPresent: fingerPresent,
        accelX: accelX,
        accelY: accelY,
        accelZ: accelZ,
        gyroX: gyroX,
        gyroY: gyroY,
        gyroZ: gyroZ,
        accTotal: accTotal,
        gyroTotal: gyroTotal,
        irValue: irValue,
        redValue: redValue,
        perfusionIndex: perfusionIndex,
        rRatio: rRatio,
        irRangePercent: irRangePercent,
        source: source ?? this.source,
      );
}
