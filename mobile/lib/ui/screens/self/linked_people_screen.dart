import 'package:flutter/material.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import 'generate_code_screen.dart';
class LinkedPeopleScreen extends StatefulWidget {
  const LinkedPeopleScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<LinkedPeopleScreen> createState() => _LinkedPeopleScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _LinkedPeopleScreenState extends State<LinkedPeopleScreen> {
  bool _loading = false;

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    _load();
  }
  Future<void> _load({bool isRefresh = false}) async {
    final app = AppScope.of(context);
    final hasData = app.relations.isNotEmpty;
    if (!isRefresh || !hasData) {
      if (mounted) setState(() => _loading = true);
    }
    try {
      await app.loadRelations();
    } catch (e) {
      debugPrint('[LinkedPeople] _load error: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Hasta bağlantı kodu veya ilişki akışındaki ilgili işlemi yürütür.
  Future<void> _removeRelation(String relationId, String name) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppTheme.surface,
        title: const Text('Bağlantıyı Kaldır',
            style: TextStyle(color: Colors.white)),
        content: Text(
          '$name kişisini bağlantılarından kaldırmak istiyor musun?',
          style: const TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child:
                  const Text('İptal', style: TextStyle(color: Colors.white54))),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Kaldır',
                  style: TextStyle(color: Colors.redAccent))),
        ],
      ),
    );
    if (confirm != true || !mounted) return;
    final app = AppScope.of(context);
    await app.removeRelation(relationId);
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final relations = app.relations;
    final relatives =
        relations.where((r) => r.relationType == 'RELATIVE').toList();
    final doctors = relations.where((r) => r.relationType == 'DOCTOR').toList();

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Bağlantılarım'),
        actions: [
          IconButton(
            tooltip: 'Kod oluştur',
            onPressed: () async {
              await Navigator.push(
                  context,
                  MaterialPageRoute(
                      builder: (_) => const GenerateCodeScreen()));
              _load(isRefresh: true);
            },
            icon:
                const Icon(Icons.person_add_outlined, color: AppTheme.primary),
          ),
        ],
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: AppTheme.primary))
          : RefreshIndicator(
              onRefresh: () => _load(isRefresh: true),
              color: AppTheme.primary,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  if (relatives.isEmpty && doctors.isEmpty) ...[
                    const SizedBox(height: 80),
                    Center(
                      child: Column(
                        children: [
                          const Icon(Icons.people_outline,
                              size: 64, color: Colors.white24),
                          const SizedBox(height: 16),
                          const Text('Henüz bağlı kişi bulunmuyor',
                              style: TextStyle(
                                  color: Colors.white38, fontSize: 16)),
                          const SizedBox(height: 8),
                          const Text(
                              'Yakın veya doktor bağlantısı kurmak için kod oluşturup paylaşın.',
                              style: TextStyle(
                                  color: Colors.white24, fontSize: 13),
                              textAlign: TextAlign.center),
                          const SizedBox(height: 24),
                          ElevatedButton.icon(
                            onPressed: () async {
                              await Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                      builder: (_) =>
                                          const GenerateCodeScreen()));
                              _load();
                            },
                            icon: const Icon(Icons.qr_code_2),
                            label: const Text('Kod Oluştur'),
                            style: ElevatedButton.styleFrom(
                                backgroundColor: AppTheme.primary),
                          ),
                        ],
                      ),
                    ),
                  ] else ...[
                    if (relatives.isNotEmpty) ...[
                      _sectionHeader('Yakınlar', Icons.family_restroom,
                          Colors.greenAccent),
                      const SizedBox(height: 8),
                      ...relatives.map((r) => _relationTile(
                          r.id,
                          r.linkedUserName,
                          Icons.family_restroom,
                          Colors.greenAccent)),
                      const SizedBox(height: 20),
                    ],
                    if (doctors.isNotEmpty) ...[
                      _sectionHeader('Doktorlar', Icons.medical_services,
                          Colors.amberAccent),
                      const SizedBox(height: 8),
                      ...doctors.map((r) => _relationTile(
                          r.id,
                          r.linkedUserName,
                          Icons.medical_services,
                          Colors.amberAccent)),
                      const SizedBox(height: 20),
                    ],
                    Center(
                      child: OutlinedButton.icon(
                        onPressed: () async {
                          await Navigator.push(
                              context,
                              MaterialPageRoute(
                                  builder: (_) => const GenerateCodeScreen()));
                          _load();
                        },
                        icon: const Icon(Icons.add, color: AppTheme.primary),
                        label: const Text('Yeni kod oluştur',
                            style: TextStyle(color: AppTheme.primary)),
                        style: OutlinedButton.styleFrom(
                          side: BorderSide(
                              color: AppTheme.primary.withOpacity(0.5)),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12)),
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
    );
  }
  Widget _sectionHeader(String title, IconData icon, Color color) {
    return Row(
      children: [
        Icon(icon, size: 16, color: color),
        const SizedBox(width: 8),
        Text(title,
            style: TextStyle(
                color: color,
                fontSize: 13,
                fontWeight: FontWeight.bold,
                letterSpacing: 1)),
      ],
    );
  }

  /// Hasta bağlantı kodu veya ilişki akışındaki ilgili işlemi yürütür.
  Widget _relationTile(String id, String name, IconData icon, Color color) {
    return GlassCard(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
                shape: BoxShape.circle, color: color.withOpacity(0.15)),
            child: Icon(icon, color: color, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(name,
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.w600)),
          ),
          IconButton(
            icon: const Icon(Icons.remove_circle_outline,
                color: Colors.redAccent, size: 20),
            tooltip: 'Kaldır',
            onPressed: () => _removeRelation(id, name),
          ),
        ],
      ),
    );
  }
}
