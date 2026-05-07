import 'package:flutter/material.dart';
import '../../core/models/enums.dart';
import '../../core/services/health_assistant_service.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';
import '../../ui/widgets/metric_card.dart';
import '../../ui/widgets/recommendations_card.dart';
import '../../ui/widgets/severity_badge.dart';
import '../../ui/widgets/trend_card.dart';
import '../../ui/widgets/empty_state_widget.dart';
import '../../ui/widgets/assistant_card.dart';
import '../../core/models/assistant_state.dart';
import '../../core/services/care_assistant_service.dart';
import 'package:fl_chart/fl_chart.dart';
import 'self/history_detail_screen.dart';
import 'health_assistant_screen.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final app = AppScope.of(context);
        final userName = app.user?.fullName.split(' ').first ?? 'Kullanıcı';
        final live = app.latestLiveStatus;
        final activeAlert = app.activeAlert;
        final recentHistory = app.history.take(3).toList();
        final recentNotifs = app.notifications.where((n) => !n.read).take(3).toList();
        final relations = app.relations;

        final bool isAlert = live != null && live.isAlert;
        final String systemStatus = activeAlert != null
            ? 'Aktif Alarm!'
            : (isAlert ? 'Uyarı – Takip Gerekli' : 'Sistem Normal');
        final Color systemColor = activeAlert != null
            ? AppTheme.critical
            : (isAlert ? AppTheme.warning : AppTheme.success);

        return SingleChildScrollView(
          padding: const EdgeInsets.only(top: 60, left: 16, right: 16, bottom: 100),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Merhaba, $userName',
                          style: AppTheme.darkTheme.textTheme.displayMedium),
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          Container(
                            width: 8,
                            height: 8,
                            margin: const EdgeInsets.only(right: 6),
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: systemColor,
                            ),
                          ),
                          Text(
                            systemStatus,
                            style: AppTheme.darkTheme.textTheme.bodyMedium?.copyWith(
                              color: systemColor,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  CircleAvatar(
                    radius: 22,
                    backgroundColor: AppTheme.primary.withOpacity(0.15),
                    child: Text(
                      userName.isNotEmpty ? userName[0].toUpperCase() : 'K',
                      style: const TextStyle(
                          color: AppTheme.primary,
                          fontWeight: FontWeight.bold,
                          fontSize: 18),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),

              GlassCard(
                borderRadius: BorderRadius.circular(14),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    if (live != null)
                      Text(
                        'Son güncelleme: ${_ago(live.timestamp)}',
                        style: const TextStyle(color: Colors.white38, fontSize: 11),
                      ),
                    Row(
                      children: [
                        Icon(Icons.battery_std,
                            color: app.isBackendMode ? Colors.white38 : AppTheme.success,
                            size: 16),
                        const SizedBox(width: 4),
                        Text(
                          app.isBackendMode ? '--' : '%${app.deviceState.batteryPercent}',
                          style: AppTheme.darkTheme.textTheme.bodyMedium
                              ?.copyWith(fontWeight: FontWeight.bold),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),

              if (activeAlert != null)
                GestureDetector(
                  onTap: () => Navigator.pushNamed(context, '/alert'),
                  child: Container(
                    width: double.infinity,
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                    decoration: BoxDecoration(
                      color: AppTheme.critical.withOpacity(0.12),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: AppTheme.critical.withOpacity(0.5)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.notification_important,
                            color: AppTheme.critical, size: 22),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'AKTİF ALARM!',
                                style: TextStyle(
                                    color: AppTheme.critical,
                                    fontWeight: FontWeight.bold,
                                    fontSize: 13),
                              ),
                              Text(
                                activeAlert.title,
                                style: const TextStyle(
                                    color: Colors.white70, fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                        const Icon(Icons.chevron_right,
                            color: AppTheme.critical, size: 20),
                      ],
                    ),
                  ),
                ),

              if (app.isBackendMode && live == null)
                Container(
                  width: double.infinity,
                  margin: const EdgeInsets.only(bottom: 12),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: Colors.orangeAccent.withOpacity(0.08),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.orangeAccent.withOpacity(0.3)),
                  ),
                  child: const Row(
                    children: [
                      Icon(Icons.info_outline, size: 16, color: Colors.orangeAccent),
                      SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          'Henüz canlı veri alınmadı. Bağlı cihazdan veri bekleniyor.',
                          style: TextStyle(color: Colors.orangeAccent, fontSize: 12),
                        ),
                      ),
                    ],
                  ),
                ),

              GridView.count(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisCount: 2,
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: 1.1,
                children: [
                  MetricCard(
                    title: 'KALP ATIŞI',
                    value: live != null
                        ? live.heartRate.toStringAsFixed(0)
                        : '--',
                    unit: 'BPM',
                    icon: Icons.favorite,
                    accentColor: (live != null &&
                            (live.heartRate > 100 || live.heartRate < 50))
                        ? AppTheme.critical
                        : AppTheme.secondary,
                    trendGraph: _buildMiniChart(AppTheme.secondary),
                  ),
                  MetricCard(
                    title: 'OKSİJEN',
                    value: live != null ? live.spo2.toStringAsFixed(1) : '--',
                    unit: '%',
                    icon: Icons.air,
                    accentColor: (live != null && live.spo2 < 94)
                        ? AppTheme.critical
                        : AppTheme.primary,
                    trendGraph: _buildMiniChart(AppTheme.primary),
                  ),
                  MetricCard(
                    title: 'RİSK SKORU',
                    value: live != null
                        ? '%${(live.riskScore * 100).toStringAsFixed(0)}'
                        : '--',
                    unit: '',
                    icon: Icons.analytics_outlined,
                    accentColor: (live != null && live.riskScore > 0.6)
                        ? AppTheme.warning
                        : AppTheme.success,
                    trendGraph: _buildMiniChart(AppTheme.success),
                  ),
                  MetricCard(
                    title: 'HAREKET',
                    value: live != null
                        ? '%${(live.motionScore * 100).toStringAsFixed(0)}'
                        : '--',
                    unit: '',
                    icon: Icons.directions_walk_outlined,
                    accentColor: (live != null && live.motionScore > 0.75)
                        ? AppTheme.warning
                        : AppTheme.primary,
                    trendGraph: _buildMiniChart(AppTheme.primary),
                  ),
                ],
              ),
              if (live != null)
                Container(
                  width: double.infinity,
                  margin: const EdgeInsets.only(top: 12),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: AppTheme.surface.withOpacity(0.35),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.white10),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Final risk skoru: ${(live.finalRiskScore ?? live.riskScore).toStringAsFixed(2)}',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (live.mlAdjustment != null)
                        Text(
                          'ML kanit katkisi: ${live.mlAdjustment! >= 0 ? '+' : ''}${live.mlAdjustment!.toStringAsFixed(2)}',
                          style: const TextStyle(color: Colors.white70, fontSize: 12),
                        ),
                      if (live.modelWindowStatus != null)
                        Text(
                          'Model penceresi: ${live.modelWindowStatus}',
                          style: const TextStyle(color: Colors.white54, fontSize: 12),
                        )
                      else
                        const Text(
                          'Model penceresi: 50Hz / 200 sample',
                          style: TextStyle(color: Colors.white54, fontSize: 12),
                        ),
                    ],
                  ),
                ),
              const SizedBox(height: 24),
              // Part 5C — Care Assistant Orchestrator card
              if (app.user != null && app.apiClient != null)
                _AssistantCardLoader(
                  userId: app.user!.id,
                  service: CareAssistantService(app.apiClient!),
                ),
              RecommendationsCard(live: live),
              const SizedBox(height: 16),

              _sectionHeader('Trend Analizi', Icons.trending_up),
              const SizedBox(height: 10),
              TrendCard(
                trend: HealthAssistantService().getTrendSync(live),
              ),
              const SizedBox(height: 16),

              GestureDetector(
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const HealthAssistantScreen()),
                ),
                child: GlassCard(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: AppTheme.primary.withOpacity(0.15),
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(Icons.health_and_safety, color: AppTheme.primary, size: 20),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Sağlık Asistanına Sor',
                              style: TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.bold,
                                fontSize: 14,
                              ),
                            ),
                            Text(
                              'Sonuçlarınızı açıklayın, öneriler alın',
                              style: TextStyle(color: Colors.white38, fontSize: 12),
                            ),
                          ],
                        ),
                      ),
                      const Icon(Icons.chevron_right, color: AppTheme.primary, size: 20),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 24),

              _sectionHeader('Son Bildirimler', Icons.notifications_outlined),
              const SizedBox(height: 10),
              if (recentNotifs.isEmpty)
                _emptyRow('Henüz bildirim yok.')
              else
                ...recentNotifs.map(
                  (n) => _notifRow(n.title, n.body, n.read),
                ),
              const SizedBox(height: 20),

              _sectionHeader('Son Olaylar', Icons.history_outlined),
              const SizedBox(height: 10),
              if (recentHistory.isEmpty)
                _emptyRow('Henüz kayıtlı olay yok.')
              else
                ...recentHistory.map((h) => GestureDetector(
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                            builder: (_) => HistoryDetailScreen(item: h)),
                      ),
                      child: Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 10),
                        decoration: BoxDecoration(
                          color: AppTheme.surface.withOpacity(0.35),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: Colors.white10),
                        ),
                        child: Row(
                          children: [
                            Icon(_historyIcon(h.type),
                                size: 16,
                                color: _severityColor(h.severity)),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(h.title,
                                  style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 13,
                                      fontWeight: FontWeight.w500)),
                            ),
                            SeverityBadge(
                                severity: h.severity, compact: true),
                          ],
                        ),
                      ),
                    )),
              const SizedBox(height: 20),

              _sectionHeader('Bağlantılarım', Icons.people_outline),
              const SizedBox(height: 10),
              if (relations.isEmpty)
                _emptyRow(
                    'Henüz bağlı kişi bulunmuyor.'),
              if (relations.isNotEmpty)
                ...relations.take(3).map((r) {
                  final isDoc = r.relationType == 'DOCTOR';
                  return Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppTheme.surface.withOpacity(0.35),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.white10),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          isDoc
                              ? Icons.medical_services_outlined
                              : Icons.family_restroom_outlined,
                          size: 16,
                          color: isDoc
                              ? Colors.amberAccent
                              : Colors.greenAccent,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            r.linkedUserName ?? (isDoc ? 'Doktor' : 'Yakın'),
                            style: const TextStyle(
                                color: Colors.white,
                                fontSize: 13,
                                fontWeight: FontWeight.w500),
                          ),
                        ),
                        Text(
                          isDoc ? 'Doktor' : 'Yakın',
                          style: TextStyle(
                              color: isDoc
                                  ? Colors.amberAccent
                                  : Colors.greenAccent,
                              fontSize: 11,
                              fontWeight: FontWeight.bold),
                        ),
                      ],
                    ),
                  );
                }),
              const SizedBox(height: 12),

            ],
          ),
        );
      },
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

  Widget _emptyRow(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(text,
          style: const TextStyle(color: Colors.white30, fontSize: 12)),
    );
  }

  Widget _notifRow(String title, String body, bool read) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: read
            ? Colors.transparent
            : AppTheme.surface.withOpacity(0.4),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: read ? Colors.white10 : AppTheme.primary.withOpacity(0.25),
        ),
      ),
      child: Row(
        children: [
          Icon(
            read
                ? Icons.notifications_none_outlined
                : Icons.notifications_outlined,
            size: 16,
            color: read ? Colors.white30 : AppTheme.primary,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.w600)),
                if (body.isNotEmpty)
                  Text(body,
                      style: const TextStyle(
                          color: Colors.white38, fontSize: 11),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
              ],
            ),
          ),
          if (!read)
            Container(
              width: 6,
              height: 6,
              decoration: const BoxDecoration(
                  shape: BoxShape.circle, color: AppTheme.primary),
            ),
        ],
      ),
    );
  }

  Color _severityColor(AlertSeverity s) {
    switch (s) {
      case AlertSeverity.critical:
        return AppTheme.critical;
      case AlertSeverity.warning:
        return AppTheme.warning;
      case AlertSeverity.watch:
        return AppTheme.primary;
      case AlertSeverity.normal:
        return AppTheme.success;
    }
  }

  IconData _historyIcon(HistoryItemType t) {
    switch (t) {
      case HistoryItemType.alert:
        return Icons.notification_important_outlined;
      case HistoryItemType.anomaly:
        return Icons.monitor_heart_outlined;
      case HistoryItemType.status:
        return Icons.info_outline;
      case HistoryItemType.notification:
        return Icons.notifications_outlined;
    }
  }

  String _ago(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inSeconds < 60) return '${diff.inSeconds}s önce';
    if (diff.inMinutes < 60) return '${diff.inMinutes} dk önce';
    if (diff.inHours < 24) return '${diff.inHours} sa önce';
    return '${diff.inDays} gün önce';
  }

  Widget _buildMiniChart(Color color) {
    return LineChart(
      LineChartData(
        gridData: const FlGridData(show: false),
        titlesData: const FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        minX: 0,
        maxX: 5,
        minY: 0,
        maxY: 5,
        lineBarsData: [
          LineChartBarData(
            spots: const [
              FlSpot(0, 2),
              FlSpot(1, 3),
              FlSpot(2, 2.5),
              FlSpot(3, 4),
              FlSpot(4, 3.5),
              FlSpot(5, 4),
            ],
            isCurved: true,
            color: color,
            barWidth: 2,
            isStrokeCapRound: true,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(show: false),
          ),
        ],
      ),
    );
  }
}

// AssistantCard verisini durumlu olarak yukleyip yeniler.
class _AssistantCardLoader extends StatefulWidget {
  final String userId;
  final CareAssistantService service;

  const _AssistantCardLoader({
    required this.userId,
    required this.service,
  });

  @override
  State<_AssistantCardLoader> createState() => _AssistantCardLoaderState();
}

class _AssistantCardLoaderState extends State<_AssistantCardLoader> {
  AssistantState? _state;
  List<AssistantAction> _actions = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final state = await widget.service.getAssistantState(widget.userId);
    final actions = await widget.service.getAssistantActions(widget.userId);
    if (mounted) {
      setState(() {
        _state = state;
        _actions = actions;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AssistantCard(
      state: _state,
      actions: _actions,
      service: widget.service,
      onAckSent: _load,
    );
  }
}
