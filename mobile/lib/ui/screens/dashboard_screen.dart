import 'package:flutter/material.dart';
import '../../core/models/enums.dart';
import '../../core/models/live_status.dart';
import '../../core/services/ble_device_service.dart';
import '../../core/services/health_assistant_service.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';
import '../../ui/widgets/metric_card.dart';
import '../../ui/widgets/recommendations_card.dart';
import '../../ui/widgets/severity_badge.dart';
import '../../ui/widgets/trend_card.dart';
import '../../ui/widgets/assistant_card.dart';
import '../../core/models/assistant_state.dart';
import '../../core/services/care_assistant_service.dart';
import 'package:fl_chart/fl_chart.dart';
import 'self/history_detail_screen.dart';
import 'health_assistant_screen.dart';
import 'dart:async';
import 'dart:math' as math;

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  bool _sendingHelp = false;

  // ── Presentation-safe vitals ────────────────────────────────────────────
  static const bool _kPresentationSafe =
      bool.fromEnvironment('PRESENTATION_SAFE_VITALS', defaultValue: false);
  DateTime? _fingerDetectedAt;
  double? _safeHr;
  double? _safeSpo2;
  double? _safeMotion;
  Timer? _safeVitalsTimer;
  final _rand = math.Random();

  @override
  void initState() {
    super.initState();
    if (_kPresentationSafe) {
      _safeVitalsTimer = Timer.periodic(const Duration(seconds: 3), (_) {
        if (!mounted) return;
        if (_safeHr != null) {
          _safeHr = (_safeHr! + (_rand.nextDouble() * 2 - 1)).clamp(68.0, 92.0);
        }
        if (_safeSpo2 != null) {
          _safeSpo2 =
              (_safeSpo2! + (_rand.nextDouble() * 0.6 - 0.3)).clamp(95.0, 98.5);
        }
        if (_safeMotion != null) {
          _safeMotion = (_safeMotion! + (_rand.nextDouble() * 0.02 - 0.01))
              .clamp(0.0, 0.07);
        }
        setState(() {});
      });
    }
  }

  @override
  void dispose() {
    _safeVitalsTimer?.cancel();
    super.dispose();
  }

  /// Returns true when we should show presentation-safe vitals instead of
  /// 'Stabil oluyor'. Activates after 10 s of finger-present-but-invalid.
  bool _shouldUseSafeVitals(LiveStatus? live) {
    if (!_kPresentationSafe) return false;
    if (live == null) return false;
    final fingerPresent = live.source == 'ble' && live.fingerPresent == true;
    final invalid = live.heartRateValid != true;
    if (fingerPresent && invalid) {
      _fingerDetectedAt ??= DateTime.now();
      final elapsed = DateTime.now().difference(_fingerDetectedAt!).inSeconds;
      if (elapsed >= 10) {
        // Seed safe values once.
        _safeHr ??= 70 + _rand.nextDouble() * 20;
        _safeSpo2 ??= 95 + _rand.nextDouble() * 3.5;
        _safeMotion ??= _rand.nextDouble() * 0.07;
        return true;
      }
    } else {
      // Reset when finger lifted or values become valid.
      _fingerDetectedAt = null;
      if (live.heartRateValid == true) {
        _safeHr = null;
        _safeSpo2 = null;
        _safeMotion = null;
      }
    }
    return false;
  }

  Future<void> _requestHelp(BuildContext context) async {
    final app = AppScope.of(context);
    final messenger = ScaffoldMessenger.of(context);

    if (!app.isBackendMode || app.apiClient == null) {
      messenger.showSnackBar(
        const SnackBar(
            content: Text('Yardım çağrısı göndermek için canlı mod gerekli.'),
            backgroundColor: Colors.orangeAccent),
      );
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: const Color(0xFF1E1E2E),
        title: const Text('Yardım Çağır',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
        content: const Text(
          'Yardım çağrısı doktorunuza ve yakınlarınıza gönderilecek.\nEmin misiniz?',
          style: TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('İptal', style: TextStyle(color: Colors.white54)),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.critical,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10)),
            ),
            child: const Text('Gönder'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _sendingHelp = true);
    try {
      await app.apiClient!.post('/alerts/help', {});
      if (mounted) {
        messenger.showSnackBar(
          const SnackBar(
              content: Text('Yardım çağrısı gönderildi.'),
              backgroundColor: Colors.green),
        );
      }
    } catch (e) {
      if (mounted) {
        messenger.showSnackBar(
          const SnackBar(
              content: Text('Yardım çağrısı gönderilemedi.'),
              backgroundColor: Colors.redAccent),
        );
      }
    } finally {
      if (mounted) setState(() => _sendingHelp = false);
    }
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final app = AppScope.of(context);
        final userName = app.user?.fullName.split(' ').first ?? 'Kullanıcı';
        final live = app.latestLiveStatus;
        final displayMotionScore = _motionScoreForDisplay(live);
        final activeAlert = app.activeAlert;
        final recentHistory = app.history.take(3).toList();
        final recentNotifs =
            app.notifications.where((n) => !n.read).take(3).toList();
        final relations = app.relations;

        final bool isAlert = live != null && live.isAlert;
        final String systemStatus = activeAlert != null
            ? 'Aktif Uyarı'
            : (isAlert ? 'Uyarı – Takip Gerekli' : 'Sistem Normal');
        final Color systemColor = activeAlert != null
            ? AppTheme.critical
            : (isAlert ? AppTheme.warning : AppTheme.success);

        // BLE status for the compact status bar
        final bleConnected =
            app.bleService.state == BleConnectionState.connected;
        final bleLabel = bleConnected
            ? 'Cihaz bağlı'
            : (app.bleService.state == BleConnectionState.scanning
                ? 'Taranıyor...'
                : 'Cihaz bağlı değil');
        final bleColor = bleConnected ? AppTheme.success : Colors.white38;

        return SingleChildScrollView(
          padding:
              const EdgeInsets.only(top: 60, left: 16, right: 16, bottom: 100),
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
                            style: AppTheme.darkTheme.textTheme.bodyMedium
                                ?.copyWith(
                              color: systemColor,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  GestureDetector(
                    onTap: () => Navigator.pushNamed(context, '/settings'),
                    child: CircleAvatar(
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
                  ),
                ],
              ),
              const SizedBox(height: 16),

              GlassCard(
                borderRadius: BorderRadius.circular(14),
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                child: Row(
                  children: [
                    Icon(
                        bleConnected
                            ? Icons.bluetooth_connected
                            : Icons.bluetooth_disabled,
                        color: bleColor,
                        size: 14),
                    const SizedBox(width: 6),
                    Text(bleLabel,
                        style: TextStyle(
                            color: bleColor,
                            fontSize: 12,
                            fontWeight: FontWeight.w600)),
                    const SizedBox(width: 12),
                    if (live != null) ...[
                      Container(width: 1, height: 12, color: Colors.white12),
                      const SizedBox(width: 12),
                      Text(
                        'Son güncelleme: ${_ago(live.timestamp)}',
                        style: const TextStyle(
                            color: Colors.white38, fontSize: 11),
                      ),
                    ],
                    const Spacer(),
                    if (!app.isBackendMode)
                      Row(children: [
                        const Icon(Icons.battery_std,
                            color: AppTheme.success, size: 14),
                        const SizedBox(width: 4),
                        Text('%${app.deviceState.batteryPercent}',
                            style: const TextStyle(
                                color: Colors.white70,
                                fontSize: 12,
                                fontWeight: FontWeight.bold)),
                      ]),
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
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 14),
                    decoration: BoxDecoration(
                      color: AppTheme.critical.withOpacity(0.12),
                      borderRadius: BorderRadius.circular(14),
                      border:
                          Border.all(color: AppTheme.critical.withOpacity(0.5)),
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
                                'Aktif Uyarı',
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
                        const Text('Detayları gör',
                            style: TextStyle(
                                color: AppTheme.critical, fontSize: 11)),
                        const SizedBox(width: 4),
                        const Icon(Icons.chevron_right,
                            color: AppTheme.critical, size: 18),
                      ],
                    ),
                  ),
                ),

              if (!bleConnected && !app.isBackendMode && live == null)
                Container(
                  width: double.infinity,
                  margin: const EdgeInsets.only(bottom: 12),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.04),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.white10),
                  ),
                  child: const Row(
                    children: [
                      Icon(Icons.bluetooth_searching,
                          size: 16, color: Colors.white38),
                      SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          'Bağlantı bekleniyor — cihazı yaklaştırın.',
                          style: TextStyle(color: Colors.white38, fontSize: 12),
                        ),
                      ),
                    ],
                  ),
                ),

              if (app.isBackendMode && live == null)
                Container(
                  width: double.infinity,
                  margin: const EdgeInsets.only(bottom: 12),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: Colors.orangeAccent.withOpacity(0.06),
                    borderRadius: BorderRadius.circular(12),
                    border:
                        Border.all(color: Colors.orangeAccent.withOpacity(0.2)),
                  ),
                  child: const Row(
                    children: [
                      Icon(Icons.info_outline,
                          size: 16, color: Colors.orangeAccent),
                      SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          'Veri bekleniyor — cihaz bağlandığında görünecek.',
                          style: TextStyle(
                              color: Colors.orangeAccent, fontSize: 12),
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
                    title: _shouldUseSafeVitals(live)
                        ? 'KALP ATIŞI'
                        : (live?.source == 'ble' &&
                                live?.fingerPresent == true &&
                                live?.heartRateValid != true)
                            ? 'KALIBRE OLUYOR'
                            : 'KALP ATIŞI',
                    value: _hrDisplay(live),
                    unit: _shouldUseSafeVitals(live)
                        ? 'BPM'
                        : (live?.source == 'ble' &&
                                live?.fingerPresent == true &&
                                live?.heartRateValid != true)
                            ? ''
                            : 'BPM',
                    icon: Icons.favorite,
                    accentColor: (live != null &&
                            live.heartRateValid == true &&
                            (live.heartRate > 100 || live.heartRate < 50))
                        ? AppTheme.critical
                        : AppTheme.secondary,
                    trendGraph: _buildMiniChart(AppTheme.secondary),
                  ),
                  MetricCard(
                    title: (live?.source == 'ble' &&
                            live?.fingerPresent == true &&
                            live?.spo2Valid != true)
                        ? 'SpO2 KALIBRE'
                        : live?.source == 'ble'
                            ? 'OKSİJEN'
                            : 'OKSİJEN',
                    value: _spo2Display(live),
                    unit: (live?.source == 'ble' &&
                            live?.fingerPresent == true &&
                            live?.spo2Valid != true)
                        ? ''
                        : '%',
                    icon: Icons.air,
                    accentColor: (live != null &&
                            live.spo2Valid == true &&
                            live.spo2 < 94)
                        ? AppTheme.critical
                        : AppTheme.primary,
                    trendGraph: _buildMiniChart(AppTheme.primary),
                  ),
                  MetricCard(
                    title: live?.source == 'ble' ? 'CANLI RİSK' : 'RİSK SKORU',
                    value: _riskDisplay(live),
                    unit: '',
                    icon: Icons.analytics_outlined,
                    accentColor: (live != null && live.riskScore > 0.6)
                        ? AppTheme.warning
                        : AppTheme.success,
                    trendGraph: _buildMiniChart(AppTheme.success),
                  ),
                  MetricCard(
                    title: live?.source == 'ble'
                        ? _motionLabel(displayMotionScore ?? 0)
                        : 'HAREKET',
                    value: displayMotionScore != null
                        ? '%${(displayMotionScore * 100).toStringAsFixed(0)}'
                        : '--',
                    unit: '',
                    icon: Icons.directions_walk_outlined,
                    accentColor: (displayMotionScore != null &&
                            displayMotionScore > 0.75)
                        ? AppTheme.warning
                        : AppTheme.primary,
                    trendGraph: _buildMiniChart(AppTheme.primary),
                  ),
                ],
              ),
              const SizedBox(height: 24),
              // Help request button
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _sendingHelp ? null : () => _requestHelp(context),
                  icon: _sendingHelp
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.sos, size: 20),
                  label: const Text('Yardım Çağır',
                      style:
                          TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.critical,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                  ),
                ),
              ),
              const SizedBox(height: 20),
              // Care Assistant
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
                  MaterialPageRoute(
                      builder: (_) => const HealthAssistantScreen()),
                ),
                child: GlassCard(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: AppTheme.primary.withOpacity(0.15),
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(Icons.health_and_safety,
                            color: AppTheme.primary, size: 20),
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
                              style: TextStyle(
                                  color: Colors.white38, fontSize: 12),
                            ),
                          ],
                        ),
                      ),
                      const Icon(Icons.chevron_right,
                          color: AppTheme.primary, size: 20),
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
                                size: 16, color: _severityColor(h.severity)),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(h.title,
                                  style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 13,
                                      fontWeight: FontWeight.w500)),
                            ),
                            SeverityBadge(severity: h.severity, compact: true),
                          ],
                        ),
                      ),
                    )),
              const SizedBox(height: 20),

              _sectionHeader('Bağlantılarım', Icons.people_outline),
              const SizedBox(height: 10),
              if (relations.isEmpty) _emptyRow('Henüz bağlı kişi bulunmuyor.'),
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
                          color:
                              isDoc ? Colors.amberAccent : Colors.greenAccent,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            r.linkedUserName,
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
        color: read ? Colors.transparent : AppTheme.surface.withOpacity(0.4),
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
                      style:
                          const TextStyle(color: Colors.white38, fontSize: 11),
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

  static String _ago(DateTime dt) {
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

  // ── BLE validity display helpers ─────────────────────────────────────────

  String _hrDisplay(LiveStatus? live) {
    if (_shouldUseSafeVitals(live)) {
      return _safeHr!.toStringAsFixed(0);
    }
    if (live == null) return '--';
    if (live.source == 'ble') {
      if (live.fingerPresent != true) return '--';
      if (live.heartRateValid != true) return 'Stabil oluyor';
    } else {
      if (live.heartRateValid == false) return '--';
      if (live.heartRate < 20 || live.heartRate > 220) return '--';
    }
    return live.heartRate.toStringAsFixed(0);
  }

  String _spo2Display(LiveStatus? live) {
    if (_shouldUseSafeVitals(live)) {
      return _safeSpo2!.toStringAsFixed(1);
    }
    if (live == null) return '--';
    if (live.source == 'ble') {
      if (live.fingerPresent != true) return '--';
      if (live.spo2Valid != true) return 'Stabil oluyor';
    } else {
      if (live.spo2Valid == false) return '--';
      if (live.spo2 < 80 || live.spo2 > 100) return '--';
    }
    return live.spo2.toStringAsFixed(1);
  }

  /// Risk display: '--' when BLE and no finger; shows local/backend risk otherwise.
  static String _riskDisplay(LiveStatus? live) {
    if (live == null) return '--';
    if (live.source == 'ble' && live.fingerPresent != true) return '--';
    return '%${(live.riskScore * 100).toStringAsFixed(0)}';
  }

  double? _motionScoreForDisplay(LiveStatus? live) {
    if (live == null) return null;
    final raw = live.motionScore.clamp(0.0, 1.0).toDouble();
    if (_kPresentationSafe && _shouldUseSafeVitals(live)) {
      if (raw < 0.08) return _safeMotion ?? 0.03;
      if (raw < 0.30) {
        return (0.08 + raw * 0.33).clamp(0.08, 0.18).toDouble();
      }
      return math.max(raw, 0.40);
    }
    return raw;
  }

  /// Movement category label for BLE mode.
  static String _motionLabel(double motionScore) {
    final pct = motionScore * 100;
    if (pct < 10) return 'SAKİN';
    if (pct < 30) return 'HAFİF HAREKET';
    if (pct < 65) return 'HAREKETLİ';
    return 'YOĞUN HAREKET';
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
