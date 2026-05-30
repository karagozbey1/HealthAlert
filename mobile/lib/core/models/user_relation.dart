/// Mobil uygulamada kullanılan ilgili veri modelini temsil eder.
class UserRelation {
  const UserRelation({
    required this.id,
    required this.selfUserId,
    required this.linkedUserId,
    required this.relationType,
    required this.isActive,
    required this.linkedUserName,
    required this.createdAt,
  });

  final String id;
  final String selfUserId;
  final String linkedUserId;
  final String relationType; // RELATIVE | DOCTOR
  final bool isActive;
  final String linkedUserName;
  final DateTime createdAt;

  /// API, BLE veya Firestore verisini uygulama modeline dönüştürür.
  static UserRelation fromJson(Map<String, dynamic> json) => UserRelation(
        id: json['id'] as String,
        selfUserId: json['self_user_id'] as String,
        linkedUserId: json['linked_user_id'] as String,
        relationType: json['relation_type'] as String,
        isActive: json['is_active'] as bool? ?? true,
        linkedUserName: json['linked_user_name'] as String? ?? 'Unknown',
        createdAt: DateTime.parse(json['created_at'] as String),
      );
}
