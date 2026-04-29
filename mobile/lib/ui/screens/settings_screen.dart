import 'package:flutter/material.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';
import '../../ui/widgets/connection_status_card.dart';
import 'battery_optimization_screen.dart';
import 'profile_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _notificationsEnabled = true;
  bool _backgroundMonitoring = true;
  bool _initialized = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_initialized) return;
    final settings = AppScope.of(context).settings;
    _notificationsEnabled = settings.notificationsEnabled;
    _backgroundMonitoring = settings.backgroundMonitoring;
    _initialized = true;
  }

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

  Future<void> _switchMode({required bool live}) async {
    final app = AppScope.of(context);
    if (live) {
      final err = await app.switchToLive(url: app.backendUrl);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(err ?? 'Canlı moda geçildi.'),
          backgroundColor: err == null ? AppTheme.success : Colors.redAccent,
        ),
      );
      return;
    }

    app.switchToDemo();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Demo moda geçildi.'),
        backgroundColor: Colors.orangeAccent,
      ),
    );
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final isLive = app.isBackendMode;

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
              Text(
                'HESAP VE UYGULAMA',
                style: AppTheme.darkTheme.textTheme.labelSmall?.copyWith(letterSpacing: 2),
              ),
              const SizedBox(height: 8),
              GlassCard(
                child: Column(
                  children: [
                    ListTile(
                      title: const Text('Hesabım', style: TextStyle(color: Colors.white)),
                      subtitle: const Text('Profil bilgilerini düzenle',
                          style: TextStyle(color: Colors.white38, fontSize: 12)),
                      leading: const Icon(Icons.person, color: AppTheme.primary),
                      trailing:
                          const Icon(Icons.arrow_forward_ios, size: 16, color: Colors.grey),
                      onTap: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(builder: (_) => const ProfileScreen()),
                        );
                      },
                    ),
                    const Divider(color: Colors.white10),
                    ListTile(
                      title:
                          const Text('Pil Optimizasyonu', style: TextStyle(color: Colors.white)),
                      subtitle: const Text('Pil kullanımı ve çalışma modu',
                          style: TextStyle(color: Colors.white38, fontSize: 12)),
                      leading: const Icon(Icons.battery_saver, color: Colors.white70),
                      trailing:
                          const Icon(Icons.arrow_forward_ios, size: 16, color: Colors.grey),
                      onTap: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(builder: (_) => const BatteryOptimizationScreen()),
                        );
                      },
                    ),
                    const Divider(color: Colors.white10),
                    SwitchListTile(
                      activeThumbColor: AppTheme.primary,
                      title: const Text('Bildirimler', style: TextStyle(color: Colors.white)),
                      subtitle: const Text('Uyarıları ve bildirimleri al',
                          style: TextStyle(color: Colors.white38, fontSize: 12)),
                      value: _notificationsEnabled,
                      onChanged: (val) async {
                        setState(() => _notificationsEnabled = val);
                        await _persist();
                      },
                    ),
                    const Divider(color: Colors.white10),
                    SwitchListTile(
                      activeThumbColor: AppTheme.primary,
                      title:
                          const Text('Arka Plan İzleme', style: TextStyle(color: Colors.white)),
                      subtitle: const Text('Uygulama kapalıyken izlemeyi sürdür',
                          style: TextStyle(color: Colors.white38, fontSize: 12)),
                      value: _backgroundMonitoring,
                      onChanged: (val) async {
                        setState(() => _backgroundMonitoring = val);
                        await _persist();
                      },
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              Text(
                'ÇALIŞMA MODU',
                style: AppTheme.darkTheme.textTheme.labelSmall?.copyWith(letterSpacing: 2),
              ),
              const SizedBox(height: 8),
              GlassCard(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isLive ? 'Canlı Mod aktif' : 'Demo Mod aktif',
                      style: TextStyle(
                        color: isLive ? AppTheme.success : Colors.orangeAccent,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'Canlı Mod gerçek sunucu verilerini kullanır. Demo Mod örnek verilerle çalışır.',
                      style: TextStyle(color: Colors.white54, fontSize: 12),
                    ),
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton(
                            onPressed: isLive ? null : () => _switchMode(live: true),
                            style: OutlinedButton.styleFrom(
                              side: BorderSide(
                                color: isLive ? Colors.white24 : AppTheme.success,
                              ),
                            ),
                            child: Text(
                              'Canlı Mod',
                              style: TextStyle(
                                color: isLive ? Colors.white38 : AppTheme.success,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: OutlinedButton(
                            onPressed: !isLive ? null : () => _switchMode(live: false),
                            style: OutlinedButton.styleFrom(
                              side: BorderSide(
                                color: !isLive ? Colors.white24 : Colors.orangeAccent,
                              ),
                            ),
                            child: Text(
                              'Demo Mod',
                              style: TextStyle(
                                color: !isLive ? Colors.white38 : Colors.orangeAccent,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              Text(
                'BAĞLANTI DURUMU',
                style: AppTheme.darkTheme.textTheme.labelSmall?.copyWith(letterSpacing: 2),
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
              Center(
                child: Text('Sürüm 3.0.0 (Final)', style: AppTheme.darkTheme.textTheme.labelSmall),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
