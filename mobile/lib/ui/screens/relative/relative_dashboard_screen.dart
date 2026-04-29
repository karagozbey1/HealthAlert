import 'dart:async';

import 'package:flutter/material.dart';
import '../../../core/models/live_status.dart';
import '../../../core/models/user_profile.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import 'monitored_user_live_screen.dart';
import '../self/redeem_code_screen.dart';

class RelativeDashboardScreen extends StatefulWidget {
  const RelativeDashboardScreen({super.key});

  @override
  State<RelativeDashboardScreen> createState() => _RelativeDashboardScreenState();
}

class _RelativeDashboardScreenState extends State<RelativeDashboardScreen> {
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
      _loadData();
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
    _autoRefreshTimer = Timer.periodic(const Duration(seconds: 12), (_) {
      if (!mounted) return;
      _loadData(isRefresh: true);
    });
  }

  Future<void> _loadData({bool isRefresh = false}) async {
    if (_loadInProgress) return;
    _loadInProgress = true;
    try {
      final app = AppScope.of(context);
      final hasData = app.monitoredUsers.isNotEmpty;
      if (!isRefresh || !hasData) {
        if (mounted) setState(() => _loading = true);
      } else {
        if (mounted) setState(() => _refreshing = true);
      }
      await app.loadMonitoredUsers();
      final users = List<UserProfile>.from(app.monitoredUsers);
      for (final user in users) {
        if (!mounted) break;
        try {
          final live = await app.getLiveStatusForUser(user.id);
          _liveData[user.id] = live;
        } catch (_) {
        }
      }
    } catch (e) {
      debugPrint('[RelativeDashboard] _loadData error: $e');
    } finally {
      _loadInProgress = false;
      if (mounted) setState(() { _loading = false; _refreshing = false; });
    }
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final users = app.monitoredUsers;
    final name = app.user?.fullName.split(' ').first ?? 'yakın';
    final statuses = users
      .map((u) => app.monitoredLiveStatuses[u.id] ?? _liveData[u.id])
        .whereType<LiveStatus>()
        .toList();
    final alertCount = statuses.where((s) => s.isAlert).length;
    final avgRisk = statuses.isEmpty
        ? 0.0
        : statuses.map((s) => s.riskScore).reduce((a, b) => a + b) / statuses.length;
    final avgSpo2 = statuses.isEmpty
        ? 0.0
        : statuses.map((s) => s.spo2).reduce((a, b) => a + b) / statuses.length;

    return SingleChildScrollView(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16, bottom: 100),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Merhaba, $name', style: AppTheme.darkTheme.textTheme.displayMedium),
          const SizedBox(height: 4),
          Text(
            '${users.length} hasta izleniyor',
            style: AppTheme.darkTheme.textTheme.bodyMedium?.copyWith(color: Colors.white54),
          ),
          const SizedBox(height: 14),
          GlassCard(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  app.isBackendMode ? 'Canlı izleme özeti' : 'Demo izleme özeti',
                  style: const TextStyle(
                    color: Colors.white70,
                    fontWeight: FontWeight.w600,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: _summaryMetric('Alarm', '$alertCount', AppTheme.warning),
                    ),
                    Expanded(
                      child: _summaryMetric('Ort. Risk', '%${(avgRisk * 100).toStringAsFixed(0)}',
                          AppTheme.primary),
                    ),
                    Expanded(
                      child: _summaryMetric('Ort. SpO₂',
                          statuses.isEmpty ? '--' : avgSpo2.toStringAsFixed(1), AppTheme.success),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),

          if (_loading)
            const Center(child: Padding(
              padding: EdgeInsets.all(48),
              child: CircularProgressIndicator(color: Colors.greenAccent),
            ))
          else if (users.isEmpty)
            _buildEmptyState()
          else ...[
            if (alertCount > 0)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Text(
                  'Öncelikli takip gereken hastalar listeleniyor.',
                  style: const TextStyle(color: AppTheme.warning, fontSize: 12),
                ),
              ),
            ...users.map((u) => _buildUserCard(u)),
          ],

          const SizedBox(height: 16),
          if (_refreshing)
            const LinearProgressIndicator(color: Colors.greenAccent, backgroundColor: Colors.transparent)
          else
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () => _loadData(isRefresh: true),
                icon: const Icon(Icons.refresh, color: Colors.greenAccent),
                label: const Text('Yenile', style: TextStyle(color: Colors.greenAccent)),
                style: OutlinedButton.styleFrom(
                  side: BorderSide(color: Colors.greenAccent.withOpacity(0.4)),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
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
          const SizedBox(height: 20),
          ElevatedButton.icon(
            onPressed: () async {
              await Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => const _RedeemCodeLauncher(),
                ),
              );
              if (mounted) _loadData(isRefresh: true);
            },
            icon: const Icon(Icons.link),
            label: const Text('Kod Gir ve Hasta Ekle'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.greenAccent,
              foregroundColor: Colors.black87,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildUserCard(UserProfile user) {
    final appCtrl = AppScope.of(context);
    final live = appCtrl.monitoredLiveStatuses[user.id] ?? _liveData[user.id];
    final hasAlert = live?.isAlert ?? false;

    return GestureDetector(
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => MonitoredUserLiveScreen(user: user),
        ),
      ),
      child: Container(
        margin: const EdgeInsets.only(bottom: 16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          color: AppTheme.surface.withOpacity(0.5),
          border: Border.all(
            color: hasAlert ? Colors.redAccent.withOpacity(0.6) : Colors.white12,
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Row(
                children: [
                  CircleAvatar(
                    radius: 22,
                    backgroundColor: Colors.greenAccent.withOpacity(0.15),
                    child: Text(
                      user.fullName.isNotEmpty ? user.fullName[0].toUpperCase() : '?',
                      style: const TextStyle(
                          color: Colors.greenAccent, fontWeight: FontWeight.bold, fontSize: 18),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(user.fullName,
                            style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.bold,
                                fontSize: 15)),
                        Text(user.email,
                            style: const TextStyle(color: Colors.white38, fontSize: 12)),
                      ],
                    ),
                  ),
                  if (hasAlert)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: Colors.redAccent.withOpacity(0.15),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.redAccent.withOpacity(0.4)),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.warning_amber_rounded, size: 12, color: Colors.redAccent),
                          SizedBox(width: 4),
                            Text('ALARM',
                              style: TextStyle(
                                  color: Colors.redAccent,
                                  fontSize: 10,
                                  fontWeight: FontWeight.bold)),
                        ],
                      ),
                    ),
                  const SizedBox(width: 8),
                  const Icon(Icons.chevron_right, color: Colors.white30),
                ],
              ),
              if (live != null) ...[
                const SizedBox(height: 12),
                const Divider(color: Colors.white12),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: hasAlert
                            ? AppTheme.warning.withOpacity(0.15)
                            : AppTheme.success.withOpacity(0.12),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: hasAlert
                              ? AppTheme.warning.withOpacity(0.4)
                              : AppTheme.success.withOpacity(0.35),
                        ),
                      ),
                      child: Text(
                        live.scenarioLabel,
                        style: TextStyle(
                          color: hasAlert ? AppTheme.warning : AppTheme.success,
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    const Spacer(),
                    Text(
                      _ago(live.timestamp),
                      style: const TextStyle(color: Colors.white38, fontSize: 11),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    _metric('HR', live.heartRate.toStringAsFixed(0), 'bpm', AppTheme.secondary),
                    _metric('SpO₂', live.spo2.toStringAsFixed(1), '%', AppTheme.primary),
                    _metric(
                      'Risk',
                      '${(live.riskScore * 100).toStringAsFixed(0)}%',
                      '',
                      live.riskScore > 0.6 ? AppTheme.warning : AppTheme.success),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _summaryMetric(String label, String value, Color color) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white38, fontSize: 10)),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 16),
        ),
      ],
    );
  }

  Widget _metric(String label, String value, String unit, Color color) {
    return Column(
      children: [
        Text(label, style: const TextStyle(color: Colors.white38, fontSize: 10)),
        const SizedBox(height: 2),
        RichText(
          text: TextSpan(
            children: [
              TextSpan(
                  text: value,
                  style: TextStyle(
                      color: color, fontWeight: FontWeight.bold, fontSize: 18)),
              if (unit.isNotEmpty)
                TextSpan(
                    text: ' $unit',
                    style: const TextStyle(color: Colors.white38, fontSize: 11)),
            ],
          ),
        ),
      ],
    );
  }

  String _ago(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inSeconds < 60) return '${diff.inSeconds}s önce';
    if (diff.inMinutes < 60) return '${diff.inMinutes} dk önce';
    if (diff.inHours < 24) return '${diff.inHours} sa önce';
    return '${diff.inDays} gün önce';
  }
}

class _RedeemCodeLauncher extends StatelessWidget {
  const _RedeemCodeLauncher();
  @override
  Widget build(BuildContext context) => const RedeemCodeScreen();
}
