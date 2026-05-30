import 'package:flutter/material.dart';
import '../../core/models/enums.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class BatteryOptimizationScreen extends StatefulWidget {
  const BatteryOptimizationScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<BatteryOptimizationScreen> createState() =>
      _BatteryOptimizationScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _BatteryOptimizationScreenState extends State<BatteryOptimizationScreen> {
  String _selectedMode = "Dengeli";
  bool _dimBrightness = false;
  bool _backgroundMode = true;
  String _uploadInterval = "5 Dakika";
  bool _loaded = false;

  /// Inherited bağımlılıklar değiştiğinde ekran ayarlarını günceller.
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_loaded) return;
    final s = AppScope.of(context).settings;
    _selectedMode = _modeToLabel(s.batteryMode);
    _dimBrightness = s.dimBrightness;
    _backgroundMode = s.backgroundMonitoring;
    _uploadInterval = '${s.uploadIntervalMinutes} Dakika';
    _loaded = true;
  }

  /// Ekranda gösterilecek kullanıcı dostu durum etiketini seçer.
  String _modeToLabel(BatteryMode mode) {
    switch (mode) {
      case BatteryMode.performance:
        return 'Performans';
      case BatteryMode.balanced:
        return 'Dengeli';
      case BatteryMode.saver:
        return 'Tasarruf';
    }
  }

  /// Ekranda gösterilecek kullanıcı dostu durum etiketini seçer.
  BatteryMode _labelToMode(String label) {
    switch (label) {
      case 'Performans':
        return BatteryMode.performance;
      case 'Tasarruf':
        return BatteryMode.saver;
      default:
        return BatteryMode.balanced;
    }
  }

  /// Kullanıcının seçtiği ayar veya veriyi kalıcı kaynağa yazar.
  Future<void> _save() async {
    final app = AppScope.of(context);
    final current = app.settings;
    final mins = int.tryParse(_uploadInterval.split(' ').first) ?? 5;
    await app.saveSettings(
      current.copyWith(
        batteryMode: _labelToMode(_selectedMode),
        dimBrightness: _dimBrightness,
        backgroundMonitoring: _backgroundMode,
        uploadIntervalMinutes: mins,
      ),
    );
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        title: const Text("Pil Optimizasyonu"),
        backgroundColor: Colors.transparent,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Column(
                children: [
                  const Icon(Icons.battery_saver,
                      size: 80, color: AppTheme.success),
                  const SizedBox(height: 16),
                  Text(
                    "Tahmini Süre: 22s 15dk",
                    style: AppTheme.darkTheme.textTheme.displayMedium,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    "Şarj Durumu: %92",
                    style: AppTheme.darkTheme.textTheme.bodyMedium
                        ?.copyWith(color: Colors.grey),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 32),
            Text(
              "GÜÇ PROFİLLERİ",
              style: AppTheme.darkTheme.textTheme.labelSmall
                  ?.copyWith(letterSpacing: 2),
            ),
            const SizedBox(height: 16),
            GlassCard(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  _buildModeRadio("Yüksek Performans",
                      "En sık ölçüm, maksimum doğruluk.", "Performans"),
                  const Divider(color: Colors.white10),
                  _buildModeRadio("Dengeli (Önerilen)",
                      "Standart kullanım için optimize edilmiş.", "Dengeli"),
                  const Divider(color: Colors.white10),
                  _buildModeRadio("Güç Tasarrufu",
                      "Daha az ölçüm, maksimum pil ömrü.", "Tasarruf"),
                ],
              ),
            ),
            const SizedBox(height: 24),
            Text(
              "GENEL AYARLAR",
              style: AppTheme.darkTheme.textTheme.labelSmall
                  ?.copyWith(letterSpacing: 2),
            ),
            const SizedBox(height: 16),
            GlassCard(
              child: Column(
                children: [
                  SwitchListTile(
                    activeColor: AppTheme.primary,
                    title: const Text("Ekran Parlaklığını Azalt",
                        style: TextStyle(color: Colors.white)),
                    subtitle: const Text(
                        "Uygulama açıkken pil tasarrufu sağlar.",
                        style: TextStyle(fontSize: 12, color: Colors.grey)),
                    value: _dimBrightness,
                    onChanged: (val) async {
                      setState(() => _dimBrightness = val);
                      await _save();
                    },
                  ),
                  const Divider(color: Colors.white10),
                  SwitchListTile(
                    activeColor: AppTheme.primary,
                    title: const Text("Arka Planda Çalış",
                        style: TextStyle(color: Colors.white)),
                    subtitle: const Text(
                        "Uygulama kapalıyken bile izlemeye devam et.",
                        style: TextStyle(fontSize: 12, color: Colors.grey)),
                    value: _backgroundMode,
                    onChanged: (val) async {
                      setState(() => _backgroundMode = val);
                      await _save();
                    },
                  ),
                  const Divider(color: Colors.white10),
                  ListTile(
                    title: const Text("Veri Gönderim Sıklığı",
                        style: TextStyle(color: Colors.white)),
                    trailing: DropdownButton<String>(
                      value: _uploadInterval,
                      dropdownColor: AppTheme.surface,
                      style: const TextStyle(color: Colors.white),
                      underline: const SizedBox(),
                      items: ["1 Dakika", "5 Dakika", "15 Dakika", "Saatlik"]
                          .map(
                              (e) => DropdownMenuItem(value: e, child: Text(e)))
                          .toList(),
                      onChanged: (val) {
                        if (val != null) {
                          setState(() => _uploadInterval = val);
                          _save();
                        }
                      },
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.warning.withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppTheme.warning.withOpacity(0.3)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.info, color: AppTheme.warning, size: 20),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      "Kritik uyarılar (Düşme vb.) seçilen moddan bağımsız olarak anında iletilir.",
                      style: TextStyle(fontSize: 12, color: Colors.white70),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildModeRadio(String title, String subtitle, String value) {
    final bool isSelected = _selectedMode == value;
    final titleColor = isSelected ? AppTheme.primary : Colors.white;
    final titleWeight = isSelected ? FontWeight.bold : FontWeight.normal;

    return RadioListTile<String>(
      title: Text(
        title,
        style: TextStyle(color: titleColor, fontWeight: titleWeight),
      ),
      subtitle: Text(subtitle,
          style: const TextStyle(color: Colors.grey, fontSize: 12)),
      value: value,
      groupValue: _selectedMode,
      activeColor: AppTheme.primary,
      contentPadding: EdgeInsets.zero,
      onChanged: (val) {
        if (val != null) {
          setState(() => _selectedMode = val);
          _save();
        }
      },
    );
  }
}
