import 'package:flutter/material.dart';

import '../../core/models/enums.dart';
import '../../core/services/ble_device_service.dart';
import '../../core/services/transport_orchestrator.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';
import 'profile_screen.dart';
import 'self/generate_code_screen.dart';
import 'self/linked_people_screen.dart';
import 'settings/cloud_sync_screen.dart';
import 'settings/device_connection_screen.dart';
import 'settings/work_mode_settings_screen.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _SettingsScreenState extends State<SettingsScreen> {
  bool _notificationsEnabled = true;
  bool _backgroundMonitoring = true;
  bool _initialized = false;

  /// Inherited bağımlılıklar değiştiğinde ekran ayarlarını günceller.
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_initialized) return;
    final settings = AppScope.of(context).settings;
    _notificationsEnabled = settings.notificationsEnabled;
    _backgroundMonitoring = settings.backgroundMonitoring;
    _initialized = true;
  }

  /// Kullanıcının seçtiği ayar veya veriyi kalıcı kaynağa yazar.
  Future<void> _persist() async {
    final app = AppScope.of(context);
    final current = app.settings;
    await app.saveSettings(
      current.copyWith(
        notificationsEnabled: _notificationsEnabled,
        backgroundMonitoring: _backgroundMonitoring,
      ),
    );
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final user = app.user;
    final isLive = app.isBackendMode;

    final bleState = app.bleService.state;
    final bleConnected = bleState == BleConnectionState.connected;
    final bleScanning = bleState == BleConnectionState.scanning ||
        bleState == BleConnectionState.connecting;

    final cloudLabel = app.isFirestoreSyncAvailable
        ? 'Güncel ve eşitleniyor'
        : isLive
            ? 'Canlı bulut bağlantısı açık'
            : 'Bulut bağlantısı beklemede';
    final cloudColor = app.isFirestoreSyncAvailable || isLive
        ? AppTheme.success
        : Colors.white38;

    final deviceLabel = switch (app.activeTransport) {
      TransportType.ble => 'Cihaz bağlı',
      TransportType.wifi => 'Ağ üzerinden izleniyor',
      TransportType.none => bleScanning
          ? 'Cihaz aranıyor'
          : bleConnected
              ? 'Cihaz bağlı'
              : 'Bağlantı bekleniyor',
    };

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 16),
              Text('Ayarlar', style: AppTheme.darkTheme.textTheme.displaySmall),
              const SizedBox(height: 24),
              _sectionTitle('Hesabım ve Uygulama'),
              _settingsCard([
                _accountTile(
                  name: user?.fullName ?? 'Kullanıcı',
                  email: user?.email ?? '',
                  role: _roleLabel(user?.role),
                ),
                const Divider(color: Colors.white10, height: 1),
                _settingsTile(
                  icon: Icons.tune,
                  iconColor: Colors.amberAccent,
                  title: 'Çalışma Modu',
                  subtitle:
                      isLive ? 'Canlı İzleme aktif' : 'Demo Gösterim aktif',
                  subtitleColor:
                      isLive ? AppTheme.success : Colors.orangeAccent,
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => const WorkModeSettingsScreen(),
                    ),
                  ),
                ),
                const Divider(color: Colors.white10, height: 1),
                SwitchListTile(
                  activeThumbColor: AppTheme.primary,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16),
                  title: const Text(
                    'Bildirimler',
                    style: TextStyle(color: Colors.white),
                  ),
                  subtitle: const Text(
                    'Uyarıları ve önemli bildirimleri al',
                    style: TextStyle(color: Colors.white38, fontSize: 12),
                  ),
                  value: _notificationsEnabled,
                  onChanged: (val) async {
                    setState(() => _notificationsEnabled = val);
                    await _persist();
                  },
                ),
              ]),
              const SizedBox(height: 24),
              _sectionTitle('Cihaz ve Bağlantı'),
              _settingsCard([
                _settingsTile(
                  icon: bleConnected
                      ? Icons.bluetooth_connected
                      : bleScanning
                          ? Icons.bluetooth_searching
                          : Icons.bluetooth_disabled,
                  iconColor: bleConnected
                      ? AppTheme.success
                      : bleScanning
                          ? Colors.orangeAccent
                          : Colors.white38,
                  title: 'Cihaz Bağlantısı',
                  subtitle: deviceLabel,
                  subtitleColor:
                      bleConnected ? AppTheme.success : Colors.white38,
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => const DeviceConnectionScreen(),
                    ),
                  ),
                ),
                const Divider(color: Colors.white10, height: 1),
                _settingsTile(
                  icon: app.isFirestoreSyncAvailable
                      ? Icons.cloud_done_outlined
                      : Icons.cloud_sync_outlined,
                  iconColor: cloudColor,
                  title: 'Bulut Senkronizasyonu',
                  subtitle: cloudLabel,
                  subtitleColor: cloudColor,
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => const CloudSyncScreen(),
                    ),
                  ),
                ),
              ]),
              const SizedBox(height: 24),
              _sectionTitle('Güvenlik ve Erişim'),
              _settingsCard([
                _settingsTile(
                  icon: Icons.health_and_safety_outlined,
                  iconColor: AppTheme.primary,
                  title: 'Doktor / Yakın Erişimi',
                  subtitle: 'Paylaşım ve erişim izinlerini yönet',
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                        builder: (_) => const LinkedPeopleScreen()),
                  ),
                ),
                const Divider(color: Colors.white10, height: 1),
                _settingsTile(
                  icon: Icons.shield_outlined,
                  iconColor: AppTheme.success,
                  title: 'Gizlilik ve Güvenlik',
                  subtitle: 'Hesap ve veri paylaşımı tercihleri',
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => const _PrivacySecurityScreen(),
                    ),
                  ),
                ),
              ]),
              const SizedBox(height: 24),
              _sectionTitle('Bağlantılar'),
              _settingsCard([
                _settingsTile(
                  icon: Icons.qr_code_2,
                  iconColor: AppTheme.primary,
                  title: 'Bağlantı kodu oluştur',
                  subtitle: 'Doktor veya yakın için güvenli erişim kodu üret',
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                        builder: (_) => const GenerateCodeScreen()),
                  ),
                ),
                const Divider(color: Colors.white10, height: 1),
                _settingsTile(
                  icon: Icons.people_outline,
                  iconColor: Colors.greenAccent,
                  title: 'Bağlı kişilerim',
                  subtitle: 'Doktor ve yakın bağlantılarını görüntüle',
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                        builder: (_) => const LinkedPeopleScreen()),
                  ),
                ),
              ]),
              const SizedBox(height: 24),
              Center(
                child: Text(
                  'Sürüm 3.0.0 (Final)',
                  style: AppTheme.darkTheme.textTheme.labelSmall,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Widget _sectionTitle(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        text.toUpperCase(),
        style: AppTheme.darkTheme.textTheme.labelSmall,
      ),
    );
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Widget _settingsCard(List<Widget> children) {
    return GlassCard(
      padding: EdgeInsets.zero,
      child: Column(children: children),
    );
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Widget _accountTile({
    required String name,
    required String email,
    required String role,
  }) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      leading: CircleAvatar(
        radius: 20,
        backgroundColor: AppTheme.primary.withOpacity(0.15),
        child: Text(
          name.isNotEmpty ? name[0].toUpperCase() : 'K',
          style: const TextStyle(
            color: AppTheme.primary,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      title: const Text('Hesabım', style: TextStyle(color: Colors.white)),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 3),
          Text(name,
              style: const TextStyle(color: Colors.white70, fontSize: 12)),
          if (email.isNotEmpty)
            Text(email,
                style: const TextStyle(color: Colors.white38, fontSize: 12)),
          const SizedBox(height: 6),
          _rolePill(role),
        ],
      ),
      trailing:
          const Icon(Icons.edit_outlined, color: Colors.white54, size: 20),
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => const ProfileScreen()),
      ),
    );
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Widget _settingsTile({
    required IconData icon,
    required Color iconColor,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
    Color subtitleColor = Colors.white38,
  }) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      leading: Icon(icon, color: iconColor),
      title: Text(title, style: const TextStyle(color: Colors.white)),
      subtitle: Text(
        subtitle,
        style: TextStyle(color: subtitleColor, fontSize: 12),
      ),
      trailing:
          const Icon(Icons.arrow_forward_ios, size: 16, color: Colors.grey),
      onTap: onTap,
    );
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Widget _rolePill(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: AppTheme.primary.withOpacity(0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.primary.withOpacity(0.32)),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: AppTheme.primary,
          fontSize: 10,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }

  /// Ekranda gösterilecek kullanıcı dostu durum etiketini seçer.
  String _roleLabel(UserRole? role) {
    switch (role) {
      case UserRole.doctor:
        return 'Doktor';
      case UserRole.relative:
        return 'Yakın';
      case UserRole.self:
      default:
        return 'Hasta';
    }
  }
}

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class _PrivacySecurityScreen extends StatelessWidget {
  const _PrivacySecurityScreen();

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Gizlilik ve Güvenlik'),
        leading: const BackButton(),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: GlassCard(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: const [
              _PrivacyRow(
                icon: Icons.verified_user_outlined,
                title: 'Güvenli erişim',
                text:
                    'Hesabınıza bağlı doktor ve yakın erişimleri ayarlardan yönetilir.',
              ),
              Divider(color: Colors.white10, height: 24),
              _PrivacyRow(
                icon: Icons.cloud_done_outlined,
                title: 'Bulut senkronizasyonu',
                text:
                    'Canlı izleme verileri yalnızca yetkili hesaplarla paylaşılır.',
              ),
              Divider(color: Colors.white10, height: 24),
              _PrivacyRow(
                icon: Icons.notifications_active_outlined,
                title: 'Acil bildirimler',
                text:
                    'Acil durumda yardım çağrısı bağlı doktor ve yakınlara iletilir.',
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// HealthAlert içinde bu dosyanın ana sorumluluğunu taşıyan yapıdır.
class _PrivacyRow extends StatelessWidget {
  const _PrivacyRow({
    required this.icon,
    required this.title,
    required this.text,
  });

  final IconData icon;
  final String title;
  final String text;

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, color: AppTheme.primary, size: 20),
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
              const SizedBox(height: 4),
              Text(
                text,
                style: const TextStyle(color: Colors.white54, fontSize: 12),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
