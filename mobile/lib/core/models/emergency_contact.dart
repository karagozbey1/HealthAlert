/// Mobil uygulamada kullanılan ilgili veri modelini temsil eder.
class EmergencyContact {
  const EmergencyContact({
    required this.id,
    required this.name,
    required this.relation,
    required this.phone,
    required this.isPrimary,
  });

  final String id;
  final String name;
  final String relation;
  final String phone;
  final bool isPrimary;
}
