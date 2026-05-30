import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/models/live_status.dart';
import '../../../core/models/user_profile.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import 'monitored_user_live_screen.dart';
import 'relative_alerts_screen.dart';
import 'relative_generate_code_screen.dart';
import 'relative_history_screen.dart';
class RelativeDashboardScreen extends StatefulWidget {
  const RelativeDashboardScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<RelativeDashboardScreen> createState() =>
      _RelativeDashboardScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _RelativeDashboardScreenState extends State<RelativeDashboardScreen> {
  bool _loading = true;
  bool _refreshing = false;
  bool _loadInProgress = false;
  final Map<String, LiveStatus?> _liveData = {};
  Timer? _autoRefreshTimer;

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _loadData();
      _startAutoRefresh();
    });
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  @override
  void dispose() {
    _autoRefreshTimer?.cancel();
    super.dispose();
  }
  void _startAutoRefresh() {
    _autoRefreshTimer?.cancel();
    _autoRefreshTimer = Timer(const Duration(seconds: 3), () {
      if (!mounted) return;
      _loadData(isRefresh: true);
      _startAutoRefresh();
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
        } catch (error) {
          debugPrint(
              '[RelativeDashboard] Live load failed for ${user.id}: $error');
        }
      }
    } catch (e) {
      debugPrint('[RelativeDashboard] _loadData error: $e');
    } finally {
      _loadInProgress = false;
      if (mounted) {
        setState(() {
          _loading = false;
          _refreshing = false;
        });
      }
    }
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
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
        : statuses.map((s) => s.riskScore).reduce((a, b) => a + b) /
            statuses.length;
    final spo2Values = statuses.where((s) => s.spo2 > 0).map((s) => s.spo2);
    final avgSpo2 = spo2Values.isEmpty
        ? 0.0
        : spo2Values.reduce((a, b) => a + b) / spo2Values.length;
    final lastUpdate = _latestUpdate(statuses);

    return RefreshIndicator(
      color: Colors.greenAccent,
      onRefresh: () => _loadData(isRefresh: true),
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding:
            const EdgeInsets.only(top: 8, left: 16, right: 16, bottom: 100),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Merhaba, $name',
              style: AppTheme.darkTheme.textTheme.displayMedium,
            ),
            const SizedBox(height: 4),
            Text(
              '${users.length} hasta izleniyor',
              style: AppTheme.darkTheme.textTheme.bodyMedium?.copyWith(
                color: Colors.white54,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              'Son güncelleme: ${lastUpdate != null ? _ago(lastUpdate) : 'henüz yok'}',
              style: const TextStyle(color: Colors.white38, fontSize: 12),
            ),
            const SizedBox(height: 16),
            _buildSummaryCard(
              alertCount: alertCount,
              avgRisk: avgRisk,
              avgSpo2: avgSpo2,
              lastUpdate: lastUpdate,
            ),
            const SizedBox(height: 16),
            if (_loading)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(48),
                  child: CircularProgressIndicator(color: Colors.greenAccent),
                ),
              )
            else if (users.isEmpty)
              _buildEmptyState()
            else ...[
              ...users.map((u) => _buildUserCard(u)),
              const SizedBox(height: 4),
              _buildQuickActions(users.first),
              const SizedBox(height: 12),
              _buildInfoCard(),
            ],
            const SizedBox(height: 12),
            if (_refreshing)
              const LinearProgressIndicator(
                color: Colors.greenAccent,
                backgroundColor: Colors.transparent,
              )
            else
              Center(
                child: Text(
                  'Otomatik güncelleniyor',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.24),
                    fontSize: 11,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
  Widget _buildSummaryCard({
    required int alertCount,
    required double avgRisk,
    required double avgSpo2,
    required DateTime? lastUpdate,
  }) {
    return GlassCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Canlı izleme özeti',
            style: TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
              fontSize: 15,
            ),
          ),
          const SizedBox(height: 12),
          GridView.count(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisCount: 2,
            crossAxisSpacing: 10,
            mainAxisSpacing: 10,
            childAspectRatio: 2.35,
            children: [
              _summaryMetric(
                'Aktif alarm',
                '$alertCount',
                alertCount > 0 ? AppTheme.warning : AppTheme.success,
                Icons.notifications_active_outlined,
              ),
              _summaryMetric(
                'Ortalama risk',
                '%${(avgRisk * 100).toStringAsFixed(0)}',
                avgRisk > 0.6 ? AppTheme.warning : AppTheme.primary,
                Icons.analytics_outlined,
              ),
              _summaryMetric(
                'Ortalama SpO2',
                avgSpo2 > 0 ? '%${avgSpo2.toStringAsFixed(1)}' : '--',
                AppTheme.success,
                Icons.air,
              ),
              _summaryMetric(
                'Son güncelleme',
                lastUpdate != null ? _ago(lastUpdate) : '--',
                Colors.white70,
                Icons.update,
              ),
            ],
          ),
        ],
      ),
    );
  }
  Widget _buildEmptyState() {
    return GlassCard(
      padding: const EdgeInsets.all(28),
      child: Column(
        children: [
          const Icon(Icons.people_outline, size: 48, color: Colors.white24),
          const SizedBox(height: 16),
          const Text(
            'Henüz bağlı hasta yok',
            style: TextStyle(color: Colors.white70, fontSize: 16),
          ),
          const SizedBox(height: 8),
          const Text(
            'Hasta hesabının paylaştığı bağlantı kodunu girerek izlemeye başlayabilirsiniz.',
            style: TextStyle(color: Colors.white38, fontSize: 12),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 20),
          ElevatedButton.icon(
            onPressed: () async {
              await Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => const RelativeGenerateCodeScreen(),
                ),
              );
              if (mounted) _loadData(isRefresh: true);
            },
            icon: const Icon(Icons.link),
            label: const Text('Bağlantı kodu gir'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.greenAccent,
              foregroundColor: Colors.black87,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ],
      ),
    );
  }
  Widget _buildUserCard(UserProfile user) {
    final app = AppScope.of(context);
    final live = app.monitoredLiveStatuses[user.id] ?? _liveData[user.id];
    final status = _patientStatus(live);

    return GestureDetector(
      onTap: () => _openPatient(user),
      child: Container(
        margin: const EdgeInsets.only(bottom: 14),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          color: AppTheme.surface.withOpacity(0.54),
          border: Border.all(color: status.color.withOpacity(0.42)),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  CircleAvatar(
                    radius: 22,
                    backgroundColor: Colors.greenAccent.withOpacity(0.15),
                    child: Text(
                      user.fullName.isNotEmpty
                          ? user.fullName[0].toUpperCase()
                          : '?',
                      style: const TextStyle(
                        color: Colors.greenAccent,
                        fontWeight: FontWeight.bold,
                        fontSize: 18,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          user.fullName,
                          style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: 15,
                          ),
                        ),
                        Text(
                          user.email.isNotEmpty ? user.email : user.id,
                          style: const TextStyle(
                            color: Colors.white38,
                            fontSize: 12,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  _statusPill(status.label, status.color),
                ],
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: _metric(
                      'HR',
                      live != null && live.heartRate > 0
                          ? live.heartRate.toStringAsFixed(0)
                          : '--',
                      'bpm',
                      AppTheme.secondary,
                    ),
                  ),
                  Expanded(
                    child: _metric(
                      'SpO2',
                      live != null && live.spo2 > 0
                          ? live.spo2.toStringAsFixed(1)
                          : '--',
                      '%',
                      AppTheme.primary,
                    ),
                  ),
                  Expanded(
                    child: _metric(
                      'Risk',
                      live != null
                          ? '${(live.riskScore * 100).toStringAsFixed(0)}'
                          : '--',
                      '%',
                      live != null && live.riskScore > 0.6
                          ? AppTheme.warning
                          : AppTheme.success,
                    ),
                  ),
                  Expanded(
                    child: _metric(
                      'Hareket',
                      live != null
                          ? '${(live.motionScore * 100).toStringAsFixed(0)}'
                          : '--',
                      '%',
                      Colors.greenAccent,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  const Icon(Icons.update, size: 13, color: Colors.white30),
                  const SizedBox(width: 6),
                  Text(
                    live != null
                        ? 'Son güncelleme: ${_ago(live.timestamp)}'
                        : 'Veri bekleniyor',
                    style: const TextStyle(color: Colors.white38, fontSize: 11),
                  ),
                  const Spacer(),
                  const Icon(Icons.chevron_right, color: Colors.white30),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
  Widget _buildQuickActions(UserProfile firstUser) {
    return GlassCard(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Hızlı aksiyonlar',
            style: TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _actionChip(
                Icons.monitor_heart_outlined,
                'Hasta detayını gör',
                () => _openPatient(firstUser),
              ),
              _actionChip(
                Icons.notifications_outlined,
                'Uyarıları gör',
                () => Navigator.push(
                  context,
                  MaterialPageRoute(
                      builder: (_) => const RelativeAlertsScreen()),
                ),
              ),
              _actionChip(
                Icons.history_outlined,
                'Geçmişi gör',
                () => Navigator.push(
                  context,
                  MaterialPageRoute(
                      builder: (_) => const RelativeHistoryScreen()),
                ),
              ),
              _actionChip(
                Icons.link,
                'Bağlantı yönetimi',
                () async {
                  await Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => const RelativeGenerateCodeScreen(),
                    ),
                  );
                  if (mounted) _loadData(isRefresh: true);
                },
              ),
            ],
          ),
        ],
      ),
    );
  }
  Widget _buildInfoCard() {
    return GlassCard(
      padding: const EdgeInsets.all(14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: const [
          Icon(Icons.info_outline, color: Colors.greenAccent, size: 18),
          SizedBox(width: 10),
          Expanded(
            child: Text(
              'Veriler otomatik güncellenir. Acil durumda yardım çağrısı doktor ve yakınlara iletilir.',
              style: TextStyle(color: Colors.white54, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }
  Widget _summaryMetric(
    String label,
    String value,
    Color color,
    IconData icon,
  ) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.04),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.white10),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 17),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  label,
                  style: const TextStyle(color: Colors.white38, fontSize: 10),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  value,
                  style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
  Widget _metric(String label, String value, String unit, Color color) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: const TextStyle(color: Colors.white38, fontSize: 10)),
        const SizedBox(height: 3),
        RichText(
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          text: TextSpan(
            children: [
              TextSpan(
                text: value,
                style: TextStyle(
                  color: color,
                  fontWeight: FontWeight.bold,
                  fontSize: 17,
                ),
              ),
              if (unit.isNotEmpty && value != '--')
                TextSpan(
                  text: ' $unit',
                  style: const TextStyle(color: Colors.white38, fontSize: 10),
                ),
            ],
          ),
        ),
      ],
    );
  }
  Widget _statusPill(String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: color.withOpacity(0.14),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withOpacity(0.34)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }
  Widget _actionChip(IconData icon, String label, VoidCallback onTap) {
    return OutlinedButton.icon(
      onPressed: onTap,
      icon: Icon(icon, size: 16),
      label: Text(label, overflow: TextOverflow.ellipsis),
      style: OutlinedButton.styleFrom(
        foregroundColor: Colors.greenAccent,
        side: BorderSide(color: Colors.greenAccent.withOpacity(0.35)),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      ),
    );
  }

  _PatientStatus _patientStatus(LiveStatus? live) {
    if (live == null) {
      return const _PatientStatus('Veri bekleniyor', Colors.white38);
    }
    if (DateTime.now().difference(live.timestamp).inSeconds > 90) {
      return const _PatientStatus('Veri gecikti', Colors.orangeAccent);
    }
    if (live.isAlert) {
      return const _PatientStatus('Aktif uyarı', AppTheme.warning);
    }
    if (live.scenario == 'recovery') {
      return const _PatientStatus('Toparlanma', AppTheme.primary);
    }
    return const _PatientStatus('Normal', AppTheme.success);
  }
  DateTime? _latestUpdate(List<LiveStatus> statuses) {
    if (statuses.isEmpty) return null;
    return statuses
        .map((s) => s.timestamp)
        .reduce((a, b) => a.isAfter(b) ? a : b);
  }
  void _openPatient(UserProfile user) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => MonitoredUserLiveScreen(user: user),
      ),
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
class _PatientStatus {
  const _PatientStatus(this.label, this.color);

  final String label;
  final Color color;
}
