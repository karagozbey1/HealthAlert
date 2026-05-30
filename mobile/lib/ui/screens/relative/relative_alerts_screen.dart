import 'dart:async';
import 'package:flutter/material.dart';
import '../../../core/models/alert_event.dart';
import '../../../core/models/enums.dart';
import '../../../core/models/user_profile.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import '../../widgets/severity_badge.dart';

class RelativeAlertsScreen extends StatefulWidget {
  const RelativeAlertsScreen({super.key});

  @override
  State<RelativeAlertsScreen> createState() => _RelativeAlertsScreenState();
}

class _RelativeAlertsScreenState extends State<RelativeAlertsScreen> {
  bool _loading = false;
  bool _refreshing = false;
  final Map<String, _UserAlerts> _data = {};
  String? _error;
  Timer? _autoRefreshTimer;

  /// Widget durumunu başlatır.
  @override
  void initState() {
    super.initState();
    _loadAlerts();
    // Auto-refresh: alerts should surface within the final presentation SLA.
    _autoRefreshTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (mounted) _loadAlerts(isRefresh: true);
    });
  }

  /// Kaynakları serbest bırakır.
  @override
  void dispose() {
    _autoRefreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadAlerts({bool isRefresh = false}) async {
    if (!mounted) return;
    if (!isRefresh || _data.isEmpty) {
      setState(() {
        _loading = true;
        _error = null;
      });
    } else {
      setState(() {
        _refreshing = true;
        _error = null;
      });
    }

    try {
      final app = AppScope.of(context);
      await app.loadMonitoredUsers();
      final users = List.from(app.monitoredUsers);

      final Map<String, _UserAlerts> result = {};
      for (final user in users) {
        if (!mounted) break;
        try {
          final alerts = await app.getAlertsForUser(user.id);
          result[user.id] = _UserAlerts(user: user, alerts: alerts);
        } catch (_) {}
      }

      if (mounted) {
        _data
          ..clear()
          ..addAll(result);
      }
    } catch (e) {
      debugPrint('[RelativeAlerts] _loadAlerts error: $e');
    } finally {
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
    final linkedPatients = app.monitoredUsers;
    final hasAlerts = _data.values.any((d) => d.alerts.isNotEmpty);

    return SingleChildScrollView(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16, bottom: 100),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Alarm Akışı',
              style: AppTheme.darkTheme.textTheme.displayMedium),
          const SizedBox(height: 4),
          Text(
            'Bağlı hastalardan gelen son alarmlar',
            style: AppTheme.darkTheme.textTheme.bodyMedium
                ?.copyWith(color: Colors.white54),
          ),
          const SizedBox(height: 20),
          if (_loading)
            const Center(
                child: Padding(
              padding: EdgeInsets.all(48),
              child: CircularProgressIndicator(color: Colors.greenAccent),
            ))
          else if (_error != null)
            _buildErrorState()
          else if (linkedPatients.isEmpty)
            _buildEmptyState('Henüz bağlı hasta yok.',
                'Asıl kişinin paylaştığı kodu girerek bağlantı kurun.')
          else if (!hasAlerts)
            _buildEmptyState('Aktif uyarı yok.',
                'Bağlı hastalarınızda aktif alarm bulunmuyor.')
          else ...[
            for (final entry in _data.entries)
              if (entry.value.alerts.isNotEmpty)
                _buildPatientSection(entry.value),
          ],
          const SizedBox(height: 16),
          if (_refreshing)
            const LinearProgressIndicator(
                color: Colors.greenAccent, backgroundColor: Colors.transparent),
        ],
      ),
    );
  }

  Widget _buildPatientSection(_UserAlerts d) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(
            children: [
              CircleAvatar(
                radius: 14,
                backgroundColor: Colors.greenAccent.withOpacity(0.15),
                child: Text(
                  d.user.fullName.isNotEmpty
                      ? d.user.fullName[0].toUpperCase()
                      : '?',
                  style: const TextStyle(
                      color: Colors.greenAccent,
                      fontWeight: FontWeight.bold,
                      fontSize: 12),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                d.user.fullName,
                style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                    fontSize: 14),
              ),
              const SizedBox(width: 8),
              Text(
                '${d.alerts.length} alarm',
                style: const TextStyle(color: Colors.white38, fontSize: 12),
              ),
            ],
          ),
        ),
        ...d.alerts.map((a) => _buildAlertTile(a)),
        const SizedBox(height: 16),
      ],
    );
  }

  Widget _buildAlertTile(AlertEvent alert) {
    final color = _severityColor(alert.severity);
    final statusLabel = _statusLabel(alert.status);
    final isPending = alert.status == AlertLifecycleStatus.detected ||
        alert.status == AlertLifecycleStatus.raised ||
        alert.status == AlertLifecycleStatus.countdown;

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: GlassCard(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 4,
                  height: 44,
                  margin: const EdgeInsets.only(right: 12),
                  decoration: BoxDecoration(
                    color: color,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              alert.title,
                              style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.bold,
                                  fontSize: 14),
                            ),
                          ),
                          SeverityBadge(severity: alert.severity),
                        ],
                      ),
                      const SizedBox(height: 2),
                      Text(
                        alert.description,
                        style: const TextStyle(
                            color: Colors.white60, fontSize: 12),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Icon(Icons.access_time, size: 12, color: Colors.white30),
                const SizedBox(width: 4),
                Text(
                  _formatTime(alert.createdAt),
                  style: const TextStyle(color: Colors.white30, fontSize: 11),
                ),
                const Spacer(),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: (isPending ? Colors.orangeAccent : Colors.white10)
                        .withOpacity(0.1),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                        color:
                            (isPending ? Colors.orangeAccent : Colors.white24)
                                .withOpacity(0.3)),
                  ),
                  child: Text(
                    statusLabel,
                    style: TextStyle(
                        color: isPending ? Colors.orangeAccent : Colors.white38,
                        fontSize: 10,
                        fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyState(String title, String subtitle) {
    return GlassCard(
      padding: const EdgeInsets.all(32),
      child: Column(
        children: [
          const Icon(Icons.notifications_none_outlined,
              size: 48, color: Colors.white24),
          const SizedBox(height: 16),
          Text(title,
              style: const TextStyle(color: Colors.white54, fontSize: 16)),
          const SizedBox(height: 8),
          Text(subtitle,
              style: const TextStyle(color: Colors.white30, fontSize: 12),
              textAlign: TextAlign.center),
        ],
      ),
    );
  }

  Widget _buildErrorState() {
    return GlassCard(
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [
          const Icon(Icons.error_outline, size: 40, color: Colors.redAccent),
          const SizedBox(height: 12),
          Text(_error!,
              style: const TextStyle(color: Colors.redAccent, fontSize: 13),
              textAlign: TextAlign.center),
        ],
      ),
    );
  }

  Color _severityColor(AlertSeverity s) {
    switch (s) {
      case AlertSeverity.critical:
        return Colors.redAccent;
      case AlertSeverity.warning:
        return Colors.orangeAccent;
      case AlertSeverity.watch:
        return Colors.yellowAccent;
      case AlertSeverity.normal:
        return Colors.greenAccent;
    }
  }

  String _statusLabel(AlertLifecycleStatus s) {
    switch (s) {
      case AlertLifecycleStatus.detected:
        return 'TESPİT EDİLDİ';
      case AlertLifecycleStatus.raised:
        return 'YÜKSELTİLDİ';
      case AlertLifecycleStatus.countdown:
        return 'GERİ SAYIM';
      case AlertLifecycleStatus.acknowledged:
        return 'ONAYLANDI';
      case AlertLifecycleStatus.emergencyRequested:
        return 'ACİL DURUM';
      case AlertLifecycleStatus.timedOut:
        return 'SÜRE AŞIMI';
      case AlertLifecycleStatus.postEventMonitoring:
        return 'İZLENİYOR';
      case AlertLifecycleStatus.closed:
        return 'KAPATILDI';
    }
  }

  String _formatTime(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inMinutes < 1) return 'az önce';
    if (diff.inMinutes < 60) return '${diff.inMinutes} dk önce';
    if (diff.inHours < 24) return '${diff.inHours} sa önce';
    return '${diff.inDays} gün önce';
  }
}

class _UserAlerts {
  const _UserAlerts({required this.user, required this.alerts});
  final UserProfile user;
  final List<AlertEvent> alerts;
}
