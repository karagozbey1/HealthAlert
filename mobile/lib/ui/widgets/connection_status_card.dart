import 'package:flutter/material.dart';
import '../../core/services/ble_device_service.dart';
import '../../core/services/transport_orchestrator.dart';
import '../theme/app_theme.dart';
import 'glass_card.dart';

class ConnectionStatusCard extends StatelessWidget {
  const ConnectionStatusCard({
    super.key,
    required this.isBackendMode,
    required this.isBackendReachable,
    this.bleState = BleConnectionState.disconnected,
    this.activeTransport = TransportType.none,
    this.isFirestoreAvailable = false,
    this.bleDeviceName,
    this.blePacketsReceived = 0,
    this.wifiPolls = 0,
  });

  final bool isBackendMode;
  final bool isBackendReachable;
  final BleConnectionState bleState;
  final TransportType activeTransport;
  final bool isFirestoreAvailable;
  final String? bleDeviceName;
  final int blePacketsReceived;
  final int wifiPolls;

  String get _bleSubtitle {
    if (!isBackendMode && activeTransport == TransportType.ble) {
      return 'BLE local live mode aktif - $blePacketsReceived paket alindi';
    }
    if (!isBackendMode) return 'Demo modu - BLE baglantisi beklenebilir.';
    switch (bleState) {
      case BleConnectionState.connected:
        return 'Bağlı: ${bleDeviceName ?? "HealthAlert"} — $blePacketsReceived paket alındı';
      case BleConnectionState.scanning:
        return 'Cihaz aranıyor...';
      case BleConnectionState.connecting:
        return 'Bağlanıyor...';
      case BleConnectionState.error:
        return 'BLE hatası — tekrar deneyin.';
      case BleConnectionState.disconnected:
        return activeTransport == TransportType.wifi
            ? 'BLE bağlı değil — Wi-Fi fallback aktif'
            : 'BLE birincil transport — bağlantı bekleniyor.';
    }
  }

  String get _wifiSubtitle {
    if (!isBackendMode && activeTransport == TransportType.ble) {
      return 'Backend yok - veri telefonda yerel olarak gosteriliyor';
    }
    if (!isBackendMode) return 'Ag baglantisi gerekli degil - yerel demo modu.';
    if (activeTransport == TransportType.wifi) {
      return 'Wi-Fi fallback AKTİF — backend üzerinden veri alınıyor ($wifiPolls sorgu)';
    }
    if (activeTransport == TransportType.ble) {
      return 'Wi-Fi fallback hazır — BLE bağlantısı kesilirse otomatik geçiş';
    }
    return 'Wi-Fi fallback hazır — BLE kullanılamazsa otomatik geçiş';
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    final bleActive = bleState == BleConnectionState.connected;
    final wifiActive = activeTransport == TransportType.wifi;

    return GlassCard(
      child: Column(
        children: [
          _buildRow(
            title: 'Backend Bağlantısı',
            subtitle: isBackendMode
                ? (isBackendReachable
                    ? 'Canlı sunucuya bağlı'
                    : 'Sunucuya ulaşılamıyor')
                : 'Demo modu — sunucu bağlantısı yok',
            icon: isBackendMode ? Icons.cloud_done : Icons.cloud_off,
            isActive: isBackendMode && isBackendReachable,
            color: isBackendMode
                ? (isBackendReachable ? AppTheme.success : AppTheme.critical)
                : Colors.orangeAccent,
          ),
          const Divider(color: Colors.white10),
          _buildRow(
            title: 'Bluetooth (BLE)',
            subtitle: _bleSubtitle,
            icon: bleActive
                ? Icons.bluetooth_connected
                : Icons.bluetooth_searching,
            isActive: bleActive,
            color: bleActive
                ? AppTheme.success
                : (bleState == BleConnectionState.scanning
                    ? Colors.orangeAccent
                    : Colors.white38),
          ),
          const Divider(color: Colors.white10),
          _buildRow(
            title: 'Wi-Fi (Fallback)',
            subtitle: _wifiSubtitle,
            icon: wifiActive ? Icons.wifi : Icons.wifi_off,
            isActive: wifiActive,
            color: wifiActive ? AppTheme.success : Colors.white38,
          ),
          const Divider(color: Colors.white10),
          _buildRow(
            title: 'Firebase Sync',
            subtitle: isFirestoreAvailable
                ? 'Firestore senkronizasyonu aktif — çok rollü görünürlük sağlanıyor'
                : isBackendMode
                    ? 'Veri HTTP üzerinden backend\'e gönderiliyor'
                    : 'Demo modu — bulut senkronizasyonu yok',
            icon: isFirestoreAvailable ? Icons.sync : Icons.sync_disabled,
            isActive: isFirestoreAvailable,
            color: isFirestoreAvailable ? AppTheme.success : Colors.white38,
          ),
          if (isBackendMode) ...[
            const Divider(color: Colors.white10),
            _buildTransportIndicator(),
          ],
        ],
      ),
    );
  }

  Widget _buildTransportIndicator() {
    final String label;
    final Color color;
    final IconData icon;

    switch (activeTransport) {
      case TransportType.ble:
        label = 'Aktif Transport: BLE (birincil)';
        color = AppTheme.success;
        icon = Icons.bluetooth;
        break;
      case TransportType.wifi:
        label = 'Aktif Transport: Wi-Fi (fallback)';
        color = Colors.orangeAccent;
        icon = Icons.wifi;
        break;
      case TransportType.none:
        label = 'Aktif Transport: Yok — bağlantı bekleniyor';
        color = AppTheme.critical;
        icon = Icons.link_off;
        break;
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
      child: Row(
        children: [
          Icon(icon, color: color, size: 16),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                  color: color, fontSize: 12, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRow({
    required String title,
    required String subtitle,
    required IconData icon,
    required bool isActive,
    required Color color,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: color.withOpacity(0.12),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, color: color, size: 18),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: TextStyle(
                    color: isActive ? color : Colors.white38,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: isActive
                  ? AppTheme.success.withOpacity(0.12)
                  : Colors.white.withOpacity(0.04),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: isActive
                    ? AppTheme.success.withOpacity(0.4)
                    : Colors.white12,
              ),
            ),
            child: Text(
              isActive ? 'Aktif' : 'Etkin Değil',
              style: TextStyle(
                color: isActive ? AppTheme.success : Colors.white30,
                fontSize: 10,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
