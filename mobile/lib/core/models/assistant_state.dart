// Asistan durumunu ve eylemlerini mobil tarafta taşıyan veri modelleridir.

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class AssistantState {
  final String id;
  final String userId;
  final String currentMode;
  final String? previousMode;
  final double lastRiskScore;
  final String? lastSeverity;
  final String monitoringIntensity;
  final int recommendedPollIntervalSec;
  final bool awaitingUserAck;
  final DateTime? ackDeadlineAt;
  final String? lastUserResponse;

  const AssistantState({
    required this.id,
    required this.userId,
    required this.currentMode,
    this.previousMode,
    required this.lastRiskScore,
    this.lastSeverity,
    required this.monitoringIntensity,
    required this.recommendedPollIntervalSec,
    required this.awaitingUserAck,
    this.ackDeadlineAt,
    this.lastUserResponse,
  });

  // JSON yanıtını uygulama içinde kullanılacak durum modeline dönüştürür.
  factory AssistantState.fromJson(Map<String, dynamic> json) {
    return AssistantState(
      id: json['id'] as String? ?? '',
      userId: json['user_id'] as String? ?? '',
      currentMode: json['current_mode'] as String? ?? 'normal',
      previousMode: json['previous_mode'] as String?,
      lastRiskScore: (json['last_risk_score'] as num?)?.toDouble() ?? 0.0,
      lastSeverity: json['last_severity'] as String?,
      monitoringIntensity: json['monitoring_intensity'] as String? ?? 'normal',
      recommendedPollIntervalSec:
          json['recommended_poll_interval_sec'] as int? ?? 60,
      awaitingUserAck: json['awaiting_user_ack'] as bool? ?? false,
      ackDeadlineAt: json['ack_deadline_at'] != null
          ? DateTime.tryParse(json['ack_deadline_at'] as String)
          : null,
      lastUserResponse: json['last_user_response'] as String?,
    );
  }

  // Mevcut modun normal izleme durumu olup olmadığını söyler.
  bool get isNormal => currentMode == 'normal';

  // Mevcut modun dikkatli izleme durumu olup olmadığını söyler.
  bool get isWatch => currentMode == 'watch';

  // Mevcut modun uyarı düzeyinde olup olmadığını söyler.
  bool get isWarning => currentMode == 'warning';

  // Mevcut modun kritik müdahale gerektirip gerektirmediğini söyler.
  bool get isCritical => currentMode == 'critical';
}

/// Mobil uygulamada kullanılan ilgili veri modelini temsil eder.
class AssistantAction {
  final String id;
  final String userId;
  final String mode;
  final String actionType;
  final String message;
  final String priority;
  final bool requiresAck;
  final Map<String, dynamic>? ackOptions;
  final DateTime createdAt;
  final DateTime? expiresAt;

  const AssistantAction({
    required this.id,
    required this.userId,
    required this.mode,
    required this.actionType,
    required this.message,
    required this.priority,
    required this.requiresAck,
    this.ackOptions,
    required this.createdAt,
    this.expiresAt,
  });

  // JSON içeriğini kullanıcıya gösterilecek asistan eylemine dönüştürür.
  factory AssistantAction.fromJson(Map<String, dynamic> json) {
    return AssistantAction(
      id: json['id'] as String? ?? '',
      userId: json['user_id'] as String? ?? '',
      mode: json['mode'] as String? ?? 'normal',
      actionType: json['action_type'] as String? ?? '',
      message: json['message'] as String? ?? '',
      priority: json['priority'] as String? ?? 'low',
      requiresAck: json['requires_ack'] as bool? ?? false,
      ackOptions: json['ack_options'] != null
          ? Map<String, dynamic>.from(json['ack_options'] as Map)
          : null,
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String) ?? DateTime.now()
          : DateTime.now(),
      expiresAt: json['expires_at'] != null
          ? DateTime.tryParse(json['expires_at'] as String)
          : null,
    );
  }
}
