import 'dart:async';

import 'package:flutter/material.dart';
import '../../../core/models/enums.dart';
import '../../../core/models/live_status.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import 'doctor_alerts_screen.dart';
import 'doctor_dashboard_screen.dart';
import 'patient_detail_screen.dart';

class DoctorOverviewScreen extends StatefulWidget {
  const DoctorOverviewScreen({super.key});

  @override
  State<DoctorOverviewScreen> createState() => _DoctorOverviewScreenState();
}

class _DoctorOverviewScreenState extends State<DoctorOverviewScreen> {
  bool _loading = true;
  bool _refreshing = false;
  bool _loadInProgress = false;
  final Map<String, LiveStatus?> _liveData = {};
  Timer? _autoRefreshTimer;

  /// Widget durumunu başlatır.
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _load();
    });
    _startAutoRefresh();
  }

  /// Kaynakları serbest bırakır.
  @override
  void dispose() {
    _autoRefreshTimer?.cancel();
    super.dispose();
  }

  void _startAutoRefresh() {
    _autoRefreshTimer?.cancel();
    _autoRefreshTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (!mounted) return;
      _load(isRefresh: true);
    });
  }

  Future<void> _load({bool isRefresh = false}) async {
    if (_loadInProgress) return;
    _loadInProgress = true;
    try {
      if (!mounted) return;
      final app = AppScope.of(context);
      final hasData = app.monitoredUsers.isNotEmpty;
      if (!isRefresh || !hasData) {
        if (mounted) setState(() => _loading = true);
      } else {
        if (mounted) setState(() => _refreshing = true);
      }
      await app.loadMonitoredUsers();
      final users = List.from(app.monitoredUsers);
      for (final u in users) {
        if (!mounted) break;
        try {
          final live = await app.getLiveStatusForUser(u.id);
          _liveData[u.id] = live;
        } catch (_) {}
      }
    } catch (e) {
      debugPrint('[DoctorOverview] _load error: $e');
    } finally {
      _loadInProgress = false;
      if (mounted)
        setState(() {
          _loading = false;
          _refreshing = false;
        });
    }
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final name = app.user?.fullName.split(' ').first ?? 'Doktor';
    final patients = app.monitoredUsers;
    final statuses = <String, LiveStatus>{
      for (final p in patients)
        if ((app.monitoredLiveStatuses[p.id] ?? _liveData[p.id]) != null)
          p.id: (app.monitoredLiveStatuses[p.id] ?? _liveData[p.id])!,
    };

    final int criticalCount = statuses.values
        .where((s) => s.scenario == 'critical' || s.riskScore >= 0.8)
        .length;
    final int warningCount = statuses.values.where((s) => s.isAlert).length;
    final unread = app.unreadNotifications;

    final recentAlerts = app.monitoredAlerts.values
        .expand((list) => list)
        .where((a) =>
            a.status != AlertLifecycleStatus.closed &&
            a.status != AlertLifecycleStatus.acknowledged)
        .take(5)
        .toList();

    return SingleChildScrollView(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16, bottom: 100),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Dr. $name', style: AppTheme.darkTheme.textTheme.displayMedium),
          const SizedBox(height: 4),
          Text(
            app.isBackendMode
                ? 'Canlı sunucuya bağlı'
                : 'Demo / simülasyon modu',
            style: AppTheme.darkTheme.textTheme.bodyMedium?.copyWith(
              color: app.isBackendMode ? AppTheme.success : Colors.orangeAccent,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 20),
          if (_loading)
            const Center(
                child: Padding(
              padding: EdgeInsets.all(32),
              child: CircularProgressIndicator(color: Colors.amberAccent),
            ))
          else ...[
            Row(
              children: [
                _statBox('${patients.length}', 'Hasta', Icons.people_outline,
                    Colors.amberAccent),
                const SizedBox(width: 12),
                _statBox('$criticalCount', 'Kritik', Icons.dangerous_outlined,
                    AppTheme.critical),
                const SizedBox(width: 12),
                _statBox('$warningCount', 'Uyarı', Icons.warning_amber_rounded,
                    AppTheme.warning),
                const SizedBox(width: 12),
                _statBox('$unread', 'Bildirim', Icons.notifications_outlined,
                    AppTheme.primary),
              ],
            ),
            const SizedBox(height: 20),
            if (criticalCount > 0 || warningCount > 0) ...[
              _sectionHeader(
                  'Dikkat Gerektiren Hastalar', Icons.priority_high_outlined),
              const SizedBox(height: 10),
              ...patients.where((p) {
                final s = statuses[p.id];
                return s != null && s.isAlert;
              }).map(
                (p) {
                  final s = statuses[p.id]!;
                  return GestureDetector(
                    onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                            builder: (_) => PatientDetailScreen(patient: p))),
                    child: Container(
                      margin: const EdgeInsets.only(bottom: 10),
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: AppTheme.critical.withOpacity(0.08),
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                            color: AppTheme.critical.withOpacity(0.35)),
                      ),
                      child: Row(
                        children: [
                          CircleAvatar(
                            radius: 18,
                            backgroundColor:
                                Colors.amberAccent.withOpacity(0.15),
                            child: Text(
                              p.fullName.isNotEmpty
                                  ? p.fullName[0].toUpperCase()
                                  : '?',
                              style: const TextStyle(
                                  color: Colors.amberAccent,
                                  fontWeight: FontWeight.bold),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(p.fullName,
                                    style: const TextStyle(
                                        color: Colors.white,
                                        fontWeight: FontWeight.w600,
                                        fontSize: 14)),
                                Text(
                                  s.scenario == 'critical'
                                      ? 'Kritik – Müdahale gerekebilir'
                                      : 'Uyarı – Takip öneriliyor',
                                  style: TextStyle(
                                      color: s.scenario == 'critical'
                                          ? AppTheme.critical
                                          : AppTheme.warning,
                                      fontSize: 12),
                                ),
                              ],
                            ),
                          ),
                          const Icon(Icons.chevron_right,
                              color: Colors.white30),
                        ],
                      ),
                    ),
                  );
                },
              ),
              const SizedBox(height: 12),
            ],
            if (recentAlerts.isNotEmpty) ...[
              _sectionHeader(
                  'Aktif Alarmlar', Icons.notifications_active_outlined),
              const SizedBox(height: 10),
              ...recentAlerts.map((a) => Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppTheme.warning.withOpacity(0.08),
                      borderRadius: BorderRadius.circular(12),
                      border:
                          Border.all(color: AppTheme.warning.withOpacity(0.3)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.warning_amber_rounded,
                            color: AppTheme.warning, size: 16),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(a.title,
                              style: const TextStyle(
                                  color: Colors.white, fontSize: 13)),
                        ),
                      ],
                    ),
                  )),
              const SizedBox(height: 12),
            ],
            if (patients.isEmpty)
              _buildEmpty()
            else if (criticalCount == 0 &&
                warningCount == 0 &&
                recentAlerts.isEmpty)
              GlassCard(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    const Icon(Icons.check_circle_outline,
                        color: AppTheme.success, size: 28),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: const [
                          Text('Tüm hastalar stabil',
                              style: TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.bold)),
                          SizedBox(height: 4),
                          Text(
                              'Şu an dikkat gerektiren kritik durum bulunmuyor.',
                              style: TextStyle(
                                  color: Colors.white54, fontSize: 12)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 20),
            _sectionHeader('Hızlı Erişim', Icons.flash_on_outlined),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                    child: _quickButton(
                        'Hastalar', Icons.people_outline, Colors.amberAccent,
                        () {
                  Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => const DoctorDashboardScreen()));
                })),
                const SizedBox(width: 12),
                Expanded(
                    child: _quickButton(
                        'Uyarılar',
                        Icons.notification_important_outlined,
                        AppTheme.warning, () {
                  Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => const DoctorAlertsScreen()));
                })),
              ],
            ),
            if (_refreshing) ...[
              const SizedBox(height: 12),
              const LinearProgressIndicator(
                color: Colors.amberAccent,
                backgroundColor: Colors.transparent,
              ),
            ],
          ],
        ],
      ),
    );
  }

  Widget _statBox(String value, String label, IconData icon, Color color) {
    return Expanded(
      child: GlassCard(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(height: 6),
            Text(value,
                style: TextStyle(
                    color: color, fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 2),
            Text(label,
                style: const TextStyle(color: Colors.white38, fontSize: 10)),
          ],
        ),
      ),
    );
  }

  Widget _sectionHeader(String title, IconData icon) {
    return Row(
      children: [
        Icon(icon, size: 16, color: Colors.white54),
        const SizedBox(width: 8),
        Text(title, style: AppTheme.darkTheme.textTheme.titleLarge),
      ],
    );
  }

  Widget _quickButton(
      String label, IconData icon, Color color, VoidCallback onTap) {
    return GlassCard(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Column(
          children: [
            Icon(icon, color: color, size: 24),
            const SizedBox(height: 8),
            Text(label,
                style: TextStyle(
                    color: color, fontWeight: FontWeight.bold, fontSize: 13)),
          ],
        ),
      ),
    );
  }

  Widget _buildEmpty() {
    final app = AppScope.of(context);
    return GlassCard(
      padding: const EdgeInsets.all(32),
      child: Column(
        children: [
          const Icon(Icons.people_outline, size: 48, color: Colors.white24),
          const SizedBox(height: 16),
          const Text('Henüz bağlı hasta yok',
              style: TextStyle(color: Colors.white54, fontSize: 16)),
          const SizedBox(height: 8),
          Text(
            app.isBackendMode
                ? 'Henüz bağlı kişi bulunmuyor. Asıl kişinin paylaştığı kodu girerek bağlanabilirsiniz.'
                : 'Asıl kişinin paylaştığı kodu girerek bağlantı kurabilirsiniz.',
            style: const TextStyle(color: Colors.white30, fontSize: 12),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
