class ClinicalNote {
  const ClinicalNote({
    required this.id,
    required this.doctorId,
    required this.patientId,
    required this.note,
    this.recommendation,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String doctorId;
  final String patientId;
  final String note;
  final String? recommendation;
  final DateTime createdAt;
  final DateTime updatedAt;

  static ClinicalNote fromJson(Map<String, dynamic> json) => ClinicalNote(
        id: json['id'] as String,
        doctorId: json['doctor_id'] as String,
        patientId: json['patient_id'] as String,
        note: json['note'] as String,
        recommendation: json['recommendation'] as String?,
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'doctor_id': doctorId,
        'patient_id': patientId,
        'note': note,
        'recommendation': recommendation,
        'created_at': createdAt.toIso8601String(),
        'updated_at': updatedAt.toIso8601String(),
      };
}
