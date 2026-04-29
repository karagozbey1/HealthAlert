import 'package:flutter/material.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import '../login_screen.dart';
import '../profile_screen.dart';
import 'relative_generate_code_screen.dart';

class RelativeSettingsScreen extends StatefulWidget {
  const RelativeSettingsScreen({super.key});

  @override
  State<RelativeSettingsScreen> createState() => _RelativeSettingsScreenState();
}

class _RelativeSettingsScreenState extends State<RelativeSettingsScreen> {
  bool _notif = true;
  bool _initialized = false;

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

  /// Widget ağacını oluşturur.
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

          GlassCard(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 28,
                  backgroundColor: Colors.greenAccent.withOpacity(0.15),
                  child: Text(
                    user?.fullName.isNotEmpty == true ? user!.fullName[0].toUpperCase() : '?',
                    style: const TextStyle(
                        color: Colors.greenAccent, fontWeight: FontWeight.bold, fontSize: 22),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(user?.fullName ?? '',
                          style: const TextStyle(
                              color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16)),
                      Text(user?.email ?? '',
                          style: const TextStyle(color: Colors.white38, fontSize: 12)),
                      const SizedBox(height: 4),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: Colors.greenAccent.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: Colors.greenAccent.withOpacity(0.3)),
                        ),
                        child: const Text('YAKIN',
                            style: TextStyle(
                                color: Colors.greenAccent, fontSize: 10, fontWeight: FontWeight.bold)),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.edit_outlined, color: Colors.greenAccent, size: 20),
                  onPressed: () => Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const ProfileScreen()),
                  ),
                  tooltip: 'Profili düzenle',
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          GlassCard(
            padding: EdgeInsets.zero,
            child: ListTile(
              leading: const Icon(Icons.person_outlined, color: Colors.greenAccent),
                title: const Text('Hesabım', style: TextStyle(color: Colors.white)),
                subtitle: const Text('Profil ve hesap detaylarını düzenle',
                  style: TextStyle(color: Colors.white38, fontSize: 12)),
              trailing: const Icon(Icons.chevron_right, color: Colors.white30),
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const ProfileScreen()),
              ),
            ),
          ),
          const SizedBox(height: 24),

            Text('BİLDİRİMLER',
              style: AppTheme.darkTheme.textTheme.labelSmall?.copyWith(letterSpacing: 2)),
          const SizedBox(height: 8),
          GlassCard(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: SwitchListTile(
                title: const Text('Bildirimleri etkinleştir',
                  style: TextStyle(color: Colors.white, fontSize: 14)),
              value: _notif,
              onChanged: (v) {
                setState(() => _notif = v);
                _persist();
              },
              activeThumbColor: Colors.greenAccent,
            ),
          ),
          const SizedBox(height: 24),

            Text('BAĞLANTI KODU',
              style: AppTheme.darkTheme.textTheme.labelSmall?.copyWith(letterSpacing: 2)),
          const SizedBox(height: 8),
          GlassCard(
            padding: EdgeInsets.zero,
            child: ListTile(
              leading: const Icon(Icons.link, color: Colors.greenAccent),
                title: const Text('Bağlantı kodu gir', style: TextStyle(color: Colors.white)),
                subtitle: const Text('Asıl kişinin paylaştığı kod ile bağlan',
                  style: TextStyle(color: Colors.white38, fontSize: 12)),
              trailing: const Icon(Icons.chevron_right, color: Colors.white30),
              onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                      builder: (_) => const RelativeGenerateCodeScreen())),
            ),
          ),
          const SizedBox(height: 24),

          Text('ÇALIŞMA MODU',
              style: AppTheme.darkTheme.textTheme.labelSmall?.copyWith(letterSpacing: 2)),
          const SizedBox(height: 8),
          GlassCard(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  app.isBackendMode ? 'Canlı Mod aktif' : 'Demo Mod aktif',
                  style: TextStyle(
                    color: app.isBackendMode ? AppTheme.success : Colors.orangeAccent,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: app.isBackendMode
                            ? null
                            : () async {
                                final err = await app.switchToLive(url: app.backendUrl);
                                if (!context.mounted) return;
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(content: Text(err ?? 'Canlı moda geçildi.')),
                                );
                              },
                        child: const Text('Canlı Mod'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton(
                        onPressed: !app.isBackendMode
                            ? null
                            : () {
                                app.switchToDemo();
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(content: Text('Demo moda geçildi.')),
                                );
                              },
                        child: const Text('Demo Mod'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 32),

          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: () async {
                await app.logout();
                if (!context.mounted) return;
                Navigator.of(context).pushAndRemoveUntil(
                  MaterialPageRoute(builder: (_) => const LoginScreen()),
                  (_) => false,
                );
              },
              icon: const Icon(Icons.logout, color: Colors.redAccent),
              label: const Text('Çıkış yap', style: TextStyle(color: Colors.redAccent)),
              style: OutlinedButton.styleFrom(
                side: BorderSide(color: Colors.redAccent.withOpacity(0.4)),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
