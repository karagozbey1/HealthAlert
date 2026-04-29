import 'enums.dart';

class UserProfile {
  const UserProfile({
    required this.id,
    required this.fullName,
    required this.email,
    required this.phone,
    required this.birthDate,
    required this.deviceId,
    this.role = UserRole.self,
  });

  final String id;
  final String fullName;
  final String email;
  final String phone;
  final String birthDate;
  final String deviceId;
  final UserRole role;

  UserProfile copyWith({
    String? fullName,
    String? email,
    String? phone,
    String? birthDate,
    String? deviceId,
    UserRole? role,
  }) {
    return UserProfile(
      id: id,
      fullName: fullName ?? this.fullName,
      email: email ?? this.email,
      phone: phone ?? this.phone,
      birthDate: birthDate ?? this.birthDate,
      deviceId: deviceId ?? this.deviceId,
      role: role ?? this.role,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'fullName': fullName,
        'email': email,
        'phone': phone,
        'birthDate': birthDate,
        'deviceId': deviceId,
        'role': role.name,
      };

  static UserProfile fromJson(Map<String, dynamic> json) => UserProfile(
        id: json['id'] as String,
        fullName: (json['fullName'] ?? json['full_name'] ?? '') as String,
        email: json['email'] as String,
        phone: (json['phone'] ?? '') as String,
        birthDate: (json['birthDate'] ?? json['birth_date'] ?? '') as String,
        deviceId: (json['deviceId'] ?? '') as String,
        role: UserRole.values.firstWhere(
          (e) => e.name == (json['role'] as String?)?.toLowerCase(),
          orElse: () => UserRole.self,
        ),
      );
}
