class LinkCode {
  const LinkCode({
    required this.id,
    required this.code,
    required this.codeType,
    required this.isActive,
    required this.usesRemaining,
    required this.expiresAt,
    required this.createdAt,
  });

  final String id;
  final String code;
  final String codeType; // RELATIVE | DOCTOR
  final bool isActive;
  final int usesRemaining;
  final DateTime expiresAt;
  final DateTime createdAt;

  static LinkCode fromJson(Map<String, dynamic> json) => LinkCode(
        id: json['id'] as String,
        code: json['code'] as String,
        codeType: json['code_type'] as String,
        isActive: json['is_active'] as bool? ?? true,
        usesRemaining: json['uses_remaining'] as int? ?? 0,
        expiresAt: DateTime.parse(json['expires_at'] as String),
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  bool get isExpired => expiresAt.isBefore(DateTime.now());
  bool get canUse => isActive && !isExpired && usesRemaining > 0;
}
