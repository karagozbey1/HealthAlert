import 'package:flutter/material.dart';
import '../../../core/services/ble_device_service.dart';
import '../../../core/state/app_scope.dart';
import '../../../ui/theme/app_theme.dart';
import '../../../ui/widgets/connection_status_card.dart';
import '../../../ui/widgets/glass_card.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class AdvancedDebugScreen extends StatelessWidget {
  const AdvancedDebugScreen({super.key});

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final isLive = app.isBackendMode;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Geliştirici Araçları'),
        leading: const BackButton(),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'BAĞLANTI DURUMU',
              style: Theme.of(context)
                  .textTheme
                  .labelSmall
                  ?.copyWith(letterSpacing: 2, color: Colors.white38),
            ),
            const SizedBox(height: 8),
            ConnectionStatusCard(
              isBackendMode: isLive,
              isBackendReachable: isLive,
              bleState: app.bleService.state,
              activeTransport: app.activeTransport,
              isFirestoreAvailable: app.isFirestoreSyncAvailable,
              bleDeviceName: app.bleService.connectedDeviceName,
              blePacketsReceived: app.bleService.packetsReceived,
              wifiPolls: app.transportOrchestrator?.wifiPolls ?? 0,
            ),
            const SizedBox(height: 24),
            Text(
              'TRANSPORT DETAYLARI',
              style: Theme.of(context)
                  .textTheme
                  .labelSmall
                  ?.copyWith(letterSpacing: 2, color: Colors.white38),
            ),
            const SizedBox(height: 8),
            GlassCard(
              padding: const EdgeInsets.all(14),
              child: Column(
                children: [
                  _DebugRow('Aktif transport', app.transportLabel),
                  const Divider(color: Colors.white10, height: 16),
                  _DebugRow(
                    'BLE durumu',
                    _bleStateLabel(app.bleService.state),
                  ),
                  const Divider(color: Colors.white10, height: 16),
                  _DebugRow(
                    'Wi-Fi fallback aktif',
                    (app.transportOrchestrator?.autoFallbackEnabled ?? false)
                        ? 'Evet'
                        : 'Hayır',
                  ),
                  const Divider(color: Colors.white10, height: 16),
                  _DebugRow(
                    'Veri alımı',
                    (app.transportOrchestrator?.isReceivingData ?? false)
                        ? 'Aktif'
                        : 'Pasif',
                  ),
                  const Divider(color: Colors.white10, height: 16),
                  _DebugRow(
                      'BLE paketleri', '${app.bleService.packetsReceived}'),
                  const Divider(color: Colors.white10, height: 16),
                  _DebugRow(
                    'Wi-Fi sorguları',
                    '${app.transportOrchestrator?.wifiPolls ?? 0}',
                  ),
                  if (app.transportOrchestrator?.lastDataTime != null) ...[
                    const Divider(color: Colors.white10, height: 16),
                    _DebugRow(
                      'Son veri',
                      _ago(app.transportOrchestrator!.lastDataTime!),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 24),
            Text(
              'BACKEND',
              style: Theme.of(context)
                  .textTheme
                  .labelSmall
                  ?.copyWith(letterSpacing: 2, color: Colors.white38),
            ),
            const SizedBox(height: 8),
            GlassCard(
              padding: const EdgeInsets.all(14),
              child: Column(
                children: [
                  _DebugRow('Mod', app.modeLabel),
                  const Divider(color: Colors.white10, height: 16),
                  _DebugRow('Backend URL', app.backendUrl),
                  const Divider(color: Colors.white10, height: 16),
                  _DebugRow(
                    'Firebase',
                    app.isFirestoreSyncAvailable ? 'Bağlı' : 'Devre dışı',
                  ),
                  const Divider(color: Colors.white10, height: 16),
                  _DebugRow(
                    'Kullanıcı ID',
                    app.user?.id ?? '--',
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            GlassCard(
              padding: const EdgeInsets.all(14),
              child: Row(
                children: [
                  OutlinedButton.icon(
                    onPressed: () => app.bleService.startScan(),
                    icon: const Icon(Icons.bluetooth_searching, size: 16),
                    label: const Text('BLE Tara'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.amberAccent,
                      side: BorderSide(
                          color: Colors.amberAccent.withOpacity(0.5)),
                    ),
                  ),
                  const SizedBox(width: 12),
                  OutlinedButton.icon(
                    onPressed:
                        app.bleService.state == BleConnectionState.connected
                            ? () => app.bleService.disconnect()
                            : null,
                    icon: const Icon(Icons.bluetooth_disabled, size: 16),
                    label: const Text('Bağlantıyı Kes'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.redAccent,
                      side:
                          BorderSide(color: Colors.redAccent.withOpacity(0.4)),
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

  /// Ekranda gösterilecek kullanıcı dostu durum etiketini seçer.
  static String _bleStateLabel(BleConnectionState state) {
    switch (state) {
      case BleConnectionState.connected:
        return 'Bağlı';
      case BleConnectionState.scanning:
        return 'Taranıyor';
      case BleConnectionState.connecting:
        return 'Bağlanıyor';
      case BleConnectionState.disconnected:
        return 'Bağlı değil';
      case BleConnectionState.error:
        return 'Hata';
    }
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  static String _ago(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inSeconds < 60) return '${diff.inSeconds}s önce';
    if (diff.inMinutes < 60) return '${diff.inMinutes} dk önce';
    return '${diff.inHours} sa önce';
  }
}

/// HealthAlert içinde bu dosyanın ana sorumluluğunu taşıyan yapıdır.
class _DebugRow extends StatelessWidget {
  final String label;
  final String value;
  const _DebugRow(this.label, this.value);

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(label,
              style: const TextStyle(color: Colors.white38, fontSize: 12)),
        ),
        Text(
          value,
          style: const TextStyle(
              color: Colors.white70, fontSize: 12, fontWeight: FontWeight.bold),
        ),
      ],
    );
  }
}
