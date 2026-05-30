import 'package:flutter/material.dart';

import '../../../core/models/enums.dart';
import '../../../core/models/user_profile.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import '../login_screen.dart';
import '../profile_screen.dart';
import 'monitored_user_live_screen.dart';
import 'relative_generate_code_screen.dart';
class RelativeSettingsScreen extends StatefulWidget {
  const RelativeSettingsScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<RelativeSettingsScreen> createState() => _RelativeSettingsScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _RelativeSettingsScreenState extends State<RelativeSettingsScreen> {
  bool _notif = true;
  bool _initialized = false;

  /// Inherited bağımlılıklar değiştiğinde ekran ayarlarını günceller.
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_initialized) return;
    _notif = AppScope.of(context).settings.notificationsEnabled;
    _initialized = true;
  }
  Future<void> _persist() async {
    final app = AppScope.of(context);
    await app.saveSettings(app.settings.copyWith(notificationsEnabled: _notif));
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final user = app.user;

    return SingleChildScrollView(
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
            SwitchListTile(
              contentPadding: const EdgeInsets.symmetric(horizontal: 16),
              title: const Text(
                'Bildirimler',
                style: TextStyle(color: Colors.white, fontSize: 14),
              ),
              subtitle: const Text(
                'Hasta uyarılarını ve önemli bildirimleri al',
                style: TextStyle(color: Colors.white38, fontSize: 12),
              ),
              value: _notif,
              onChanged: (v) {
                setState(() => _notif = v);
                _persist();
              },
              activeThumbColor: Colors.greenAccent,
            ),
            const Divider(color: Colors.white10, height: 1),
            _settingsTile(
              icon: Icons.swap_horiz,
              iconColor: AppTheme.primary,
              title: 'Rol değiştir',
              subtitle: 'Farklı hesap veya rol ile devam et',
              onTap: () => _logoutToLogin(context),
            ),
          ]),
          const SizedBox(height: 24),
          _sectionTitle('Güvenlik ve Erişim'),
          _settingsCard([
            _settingsTile(
              icon: Icons.health_and_safety_outlined,
              iconColor: Colors.greenAccent,
              title: 'Doktor / Yakın erişimi',
              subtitle: 'Hasta bağlantılarınızı ve erişimi yönetin',
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => const _LinkedPatientsScreen(),
                ),
              ),
            ),
            const Divider(color: Colors.white10, height: 1),
            _settingsTile(
              icon: Icons.shield_outlined,
              iconColor: AppTheme.success,
              title: 'Gizlilik ve Güvenlik',
              subtitle: 'Paylaşım ve hesap güvenliği tercihleri',
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => const _RelativePrivacyScreen(),
                ),
              ),
            ),
          ]),
          const SizedBox(height: 24),
          _sectionTitle('Bağlantılar'),
          _settingsCard([
            _settingsTile(
              icon: Icons.link,
              iconColor: Colors.greenAccent,
              title: 'Bağlantı kodu gir',
              subtitle: 'Hasta hesabının paylaştığı kod ile bağlan',
              onTap: () async {
                await Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => const RelativeGenerateCodeScreen(),
                  ),
                );
                if (context.mounted) {
                  AppScope.of(context).loadMonitoredUsers();
                }
              },
            ),
            const Divider(color: Colors.white10, height: 1),
            _settingsTile(
              icon: Icons.people_outline,
              iconColor: AppTheme.primary,
              title: 'Bağlı hastalarım',
              subtitle: '${app.monitoredUsers.length} hasta izleniyor',
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => const _LinkedPatientsScreen(),
                ),
              ),
            ),
          ]),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: () => _logoutToLogin(context),
              icon: const Icon(Icons.logout, color: Colors.redAccent),
              label: const Text(
                'Oturumu kapat',
                style: TextStyle(color: Colors.redAccent),
              ),
              style: OutlinedButton.styleFrom(
                side: BorderSide(color: Colors.redAccent.withOpacity(0.4)),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
            ),
          ),
        ],
      ),
    );
  }
  Widget _sectionTitle(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        text.toUpperCase(),
        style: AppTheme.darkTheme.textTheme.labelSmall,
      ),
    );
  }
  Widget _settingsCard(List<Widget> children) {
    return GlassCard(
      padding: EdgeInsets.zero,
      child: Column(children: children),
    );
  }
  Widget _accountTile({
    required String name,
    required String email,
    required String role,
  }) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      leading: CircleAvatar(
        radius: 20,
        backgroundColor: Colors.greenAccent.withOpacity(0.15),
        child: Text(
          name.isNotEmpty ? name[0].toUpperCase() : '?',
          style: const TextStyle(
            color: Colors.greenAccent,
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
  Widget _settingsTile({
    required IconData icon,
    required Color iconColor,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
  }) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      leading: Icon(icon, color: iconColor),
      title: Text(title, style: const TextStyle(color: Colors.white)),
      subtitle: Text(
        subtitle,
        style: const TextStyle(color: Colors.white38, fontSize: 12),
      ),
      trailing:
          const Icon(Icons.arrow_forward_ios, size: 16, color: Colors.grey),
      onTap: onTap,
    );
  }
  Widget _rolePill(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: Colors.greenAccent.withOpacity(0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.greenAccent.withOpacity(0.32)),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Colors.greenAccent,
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
  Future<void> _logoutToLogin(BuildContext context) async {
    final app = AppScope.of(context);
    await app.logout();
    if (!context.mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
  }
}
class _LinkedPatientsScreen extends StatefulWidget {
  const _LinkedPatientsScreen();

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<_LinkedPatientsScreen> createState() => _LinkedPatientsScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _LinkedPatientsScreenState extends State<_LinkedPatientsScreen> {
  bool _loading = true;

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }
  Future<void> _load() async {
    await AppScope.of(context).loadMonitoredUsers();
    if (mounted) setState(() => _loading = false);
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final users = app.monitoredUsers;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Bağlı hastalarım'),
        leading: const BackButton(),
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: Colors.greenAccent))
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (users.isEmpty)
                  GlassCard(
                    padding: const EdgeInsets.all(28),
                    child: Column(
                      children: const [
                        Icon(Icons.people_outline,
                            size: 44, color: Colors.white24),
                        SizedBox(height: 14),
                        Text(
                          'Henüz bağlı hasta yok',
                          style: TextStyle(color: Colors.white70, fontSize: 16),
                        ),
                        SizedBox(height: 8),
                        Text(
                          'Bağlantı kodu girerek hasta izlemeye başlayabilirsiniz.',
                          style: TextStyle(color: Colors.white38, fontSize: 12),
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  )
                else
                  ...users.map(_patientTile),
              ],
            ),
    );
  }
  Widget _patientTile(UserProfile user) {
    return GlassCard(
      padding: EdgeInsets.zero,
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: Colors.greenAccent.withOpacity(0.15),
          child: Text(
            user.fullName.isNotEmpty ? user.fullName[0].toUpperCase() : '?',
            style: const TextStyle(
              color: Colors.greenAccent,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        title: Text(user.fullName, style: const TextStyle(color: Colors.white)),
        subtitle: Text(
          user.email.isNotEmpty ? user.email : user.id,
          style: const TextStyle(color: Colors.white38, fontSize: 12),
        ),
        trailing: const Icon(Icons.chevron_right, color: Colors.white30),
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => MonitoredUserLiveScreen(user: user),
          ),
        ),
      ),
    );
  }
}
class _RelativePrivacyScreen extends StatelessWidget {
  const _RelativePrivacyScreen();

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
                title: 'Yetkili erişim',
                text:
                    'Yalnızca bağlantı kurduğunuz hasta hesaplarını görüntülersiniz.',
              ),
              Divider(color: Colors.white10, height: 24),
              _PrivacyRow(
                icon: Icons.notifications_active_outlined,
                title: 'Acil bildirimler',
                text:
                    'Acil durumda yardım çağrısı doktor ve yakınlara iletilir.',
              ),
              Divider(color: Colors.white10, height: 24),
              _PrivacyRow(
                icon: Icons.cloud_done_outlined,
                title: 'Otomatik güncelleme',
                text:
                    'Canlı veriler uygun bağlantı olduğunda kendiliğinden yenilenir.',
              ),
            ],
          ),
        ),
      ),
    );
  }
}
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
        Icon(icon, color: Colors.greenAccent, size: 20),
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
