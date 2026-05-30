import 'package:flutter/material.dart';
import '../../../core/models/link_code.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import '../../widgets/gradient_button.dart';
class GenerateCodeScreen extends StatefulWidget {
  const GenerateCodeScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<GenerateCodeScreen> createState() => _GenerateCodeScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _GenerateCodeScreenState extends State<GenerateCodeScreen> {
  bool _loading = false;
  String _selectedType = 'RELATIVE';

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadExisting());
  }
  Future<void> _loadExisting() async {
    await AppScope.of(context).loadLinkCodes();
    if (mounted) setState(() {});
  }
  Future<void> _generate() async {
    setState(() => _loading = true);
    try {
      final app = AppScope.of(context);
      final generated = await app.generateLinkCode(relationType: _selectedType);
      if (!mounted) return;
      if (generated == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
              content: Text('Kod oluşturulamadı. Lütfen tekrar deneyin.')),
        );
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Kod oluşturuldu: ${generated.code}')),
      );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final codes = app.linkCodes.where((c) => c.isActive && c.canUse).toList();

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Bağlantı Kodu Oluştur'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            GlassCard(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Kodu kimin kullanacağını seçin',
                    style: TextStyle(
                        color: Colors.white, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: _typeButton('RELATIVE', 'Yakın'),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _typeButton('DOCTOR', 'Doktor'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  SizedBox(
                    width: double.infinity,
                    child: GradientButton(
                      text: _loading ? 'OLUŞTURULUYOR...' : 'KOD OLUŞTUR',
                      isLoading: _loading,
                      onPressed: _generate,
                    ),
                  ),
                  const SizedBox(height: 10),
                  const Text(
                    'Bu kodu yalnız seçtiğiniz role sahip kişi kullanabilir.',
                    style: TextStyle(color: Colors.white38, fontSize: 11),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 18),
            const Text(
              'Aktif Kodlar',
              style: TextStyle(
                color: AppTheme.primary,
                fontSize: 12,
                fontWeight: FontWeight.bold,
                letterSpacing: 1,
              ),
            ),
            const SizedBox(height: 8),
            if (codes.isEmpty)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: Text(
                  'Henüz aktif kod bulunmuyor.',
                  style: TextStyle(color: Colors.white38),
                ),
              )
            else
              ...codes.map(_codeCard),
          ],
        ),
      ),
    );
  }
  Widget _typeButton(String value, String label) {
    final selected = _selectedType == value;
    return OutlinedButton(
      onPressed: () => setState(() => _selectedType = value),
      style: OutlinedButton.styleFrom(
        side: BorderSide(color: selected ? AppTheme.primary : Colors.white24),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: selected ? AppTheme.primary : Colors.white70,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }

  /// Hasta bağlantı kodu veya ilişki akışındaki ilgili işlemi yürütür.
  Widget _codeCard(LinkCode code) {
    final hoursLeft = code.expiresAt.difference(DateTime.now()).inHours;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        color: AppTheme.surface.withOpacity(0.4),
        border: Border.all(color: AppTheme.primary.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SelectableText(
                  code.code,
                  style: const TextStyle(
                    color: AppTheme.primary,
                    fontSize: 26,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 4,
                  ),
                ),
                Text(
                  code.codeType == 'DOCTOR' ? 'Doktor kodu' : 'Yakın kodu',
                  style: const TextStyle(color: Colors.white54, fontSize: 11),
                ),
                const SizedBox(height: 4),
                Text(
                  hoursLeft > 0
                      ? '${hoursLeft}s içinde sona erer'
                      : 'Süresi doldu',
                  style: TextStyle(
                    color: hoursLeft > 0 ? Colors.white38 : Colors.redAccent,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
          const Icon(Icons.copy_outlined, color: Colors.white30, size: 18),
        ],
      ),
    );
  }
}
