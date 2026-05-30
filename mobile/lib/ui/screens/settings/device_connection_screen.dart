import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/services/ble_device_service.dart';
import '../../../core/state/app_scope.dart';
import '../../../ui/theme/app_theme.dart';
import '../../../ui/widgets/glass_card.dart';

const _kConnectionPrefKey = 'connection_mode';
class DeviceConnectionScreen extends StatefulWidget {
  const DeviceConnectionScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<DeviceConnectionScreen> createState() => _DeviceConnectionScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _DeviceConnectionScreenState extends State<DeviceConnectionScreen> {
  String _selected = 'auto';
  bool _saving = false;

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    _loadPreference();
  }
  Future<void> _loadPreference() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_kConnectionPrefKey) ?? 'auto';
    if (mounted) setState(() => _selected = saved);
  }
  Future<void> _applySelection(String mode) async {
    if (_saving) return;
    setState(() {
      _selected = mode;
      _saving = true;
    });
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kConnectionPrefKey, mode);

      if (mounted) {
        final app = AppScope.of(context);
        await app.setConnectionMode(mode);
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final bleState = app.bleService.state;
    final connected = bleState == BleConnectionState.connected;
    final connecting = bleState == BleConnectionState.scanning ||
        bleState == BleConnectionState.connecting;

    final statusLabel = connected
        ? (app.bleService.connectedDeviceName ?? 'HealthAlert cihazı')
        : connecting
            ? 'Cihaz aranıyor'
            : 'Bağlantı bekleniyor';
    final statusColor = connected
        ? AppTheme.success
        : connecting
            ? Colors.orangeAccent
            : Colors.white38;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Cihaz Bağlantısı'),
        leading: const BackButton(),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            GlassCard(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: statusColor.withOpacity(0.12),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: statusColor.withOpacity(0.28)),
                    ),
                    child: Icon(
                      connected
                          ? Icons.bluetooth_connected
                          : connecting
                              ? Icons.bluetooth_searching
                              : Icons.bluetooth_disabled,
                      color: statusColor,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Giyilebilir cihaz',
                          style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: 15,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          statusLabel,
                          style: TextStyle(color: statusColor, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            Text(
              'Bağlantı tercihi'.toUpperCase(),
              style: AppTheme.darkTheme.textTheme.labelSmall,
            ),
            const SizedBox(height: 8),
            GlassCard(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  _ModeOption(
                    value: 'auto',
                    selected: _selected,
                    icon: Icons.auto_mode,
                    title: 'Otomatik',
                    subtitle: 'Uygulama en uygun bağlantıyı kendisi seçer.',
                    onTap: () => _applySelection('auto'),
                    recommended: true,
                  ),
                  const Divider(color: Colors.white10, height: 1),
                  _ModeOption(
                    value: 'ble',
                    selected: _selected,
                    icon: Icons.watch_outlined,
                    title: 'BLE cihazı',
                    subtitle:
                        'Telefonun yakınındaki giyilebilir cihazı kullanır.',
                    onTap: () => _applySelection('ble'),
                  ),
                  const Divider(color: Colors.white10, height: 1),
                  _ModeOption(
                    value: 'wifi',
                    selected: _selected,
                    icon: Icons.cloud_queue_outlined,
                    title: 'Wi-Fi / Bulut',
                    subtitle:
                        'Canlı verileri güvenli bulut bağlantısından alır.',
                    onTap: () => _applySelection('wifi'),
                  ),
                ],
              ),
            ),
            if (_saving) ...[
              const SizedBox(height: 16),
              const Center(
                child: SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: AppTheme.primary,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
class _ModeOption extends StatelessWidget {
  const _ModeOption({
    required this.value,
    required this.selected,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.recommended = false,
  });

  final String value;
  final String selected;
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final bool recommended;

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final isSelected = value == selected;
    final color = isSelected ? AppTheme.primary : Colors.white38;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          title,
                          style: TextStyle(
                            color: isSelected ? AppTheme.primary : Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: 14,
                          ),
                        ),
                      ),
                      if (recommended) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 7,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: AppTheme.primary.withOpacity(0.14),
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(
                              color: AppTheme.primary.withOpacity(0.32),
                            ),
                          ),
                          child: const Text(
                            'Önerilen',
                            style: TextStyle(
                              color: AppTheme.primary,
                              fontSize: 10,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    subtitle,
                    style: const TextStyle(color: Colors.white38, fontSize: 12),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 10),
            Icon(
              isSelected ? Icons.check_circle : Icons.radio_button_unchecked,
              color: isSelected ? AppTheme.primary : Colors.white24,
              size: 20,
            ),
          ],
        ),
      ),
    );
  }
}
