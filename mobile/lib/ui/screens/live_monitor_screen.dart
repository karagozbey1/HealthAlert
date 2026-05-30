import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../core/models/live_status.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/empty_state_widget.dart';
import '../../ui/widgets/glass_card.dart';
import '../../ui/widgets/live_value_card.dart';
import 'health_assistant_screen.dart';

class LiveMonitorScreen extends StatefulWidget {
  const LiveMonitorScreen({super.key});

  @override
  State<LiveMonitorScreen> createState() => _LiveMonitorScreenState();
}

class _LiveMonitorScreenState extends State<LiveMonitorScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 1),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Canlı İzleme',
                    style: AppTheme.darkTheme.textTheme.displaySmall,
                  ),
                  FadeTransition(
                    opacity: _pulseController,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: AppTheme.critical.withOpacity(0.16),
                        border: Border.all(
                          color: AppTheme.critical.withOpacity(0.7),
                        ),
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: const Row(
                        children: [
                          Icon(
                            Icons.fiber_manual_record,
                            color: AppTheme.critical,
                            size: 10,
                          ),
                          SizedBox(width: 8),
                          Text(
                            'CANLI',
                            style: TextStyle(
                              color: AppTheme.critical,
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Builder(
                builder: (context) {
                  final app = AppScope.of(context);
                  final live = app.latestLiveStatus;
                  final isBackend = app.isBackendMode;

                  if (live == null && isBackend) {
                    return const EmptyStateWidget(
                      icon: Icons.monitor_heart_outlined,
                      title: 'Henüz canlı veri yok',
                      subtitle:
                          'Cihaz bağlantısı kurulduğunda ölçümler burada görünecek.',
                    );
                  }

                  return Column(
                    children: [
                      if (live != null) _statusBanner(live),
                      Row(
                        children: [
                          Expanded(
                            child: SizedBox(
                              height: 130,
                              child: live != null
                                  ? LiveValueCard.heartRate(live)
                                  : _valuePlaceholderCard(
                                      'KALP ATIŞI',
                                      '-- BPM',
                                      AppTheme.secondary,
                                    ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: SizedBox(
                              height: 130,
                              child: live != null
                                  ? LiveValueCard.spo2(live)
                                  : _valuePlaceholderCard(
                                      'OKSİJEN',
                                      '-- %',
                                      AppTheme.primary,
                                    ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: SizedBox(
                              height: 130,
                              child: live != null
                                  ? LiveValueCard.riskScore(live)
                                  : _valuePlaceholderCard(
                                      'RİSK SKORU',
                                      '--',
                                      AppTheme.success,
                                    ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: SizedBox(
                              height: 130,
                              child: live != null
                                  ? _movementCard(live)
                                  : _valuePlaceholderCard(
                                      'HAREKET',
                                      '--',
                                      AppTheme.primary,
                                    ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  );
                },
              ),
              const SizedBox(height: 16),
              _buildMonitorCard(
                'KALP ATIŞI',
                '',
                AppTheme.secondary,
                _buildSineWaveChart(AppTheme.secondary),
              ),
              const SizedBox(height: 16),
              _buildMonitorCard(
                'OKSİJEN SATÜRASYONU',
                '',
                AppTheme.primary,
                _buildSineWaveChart(
                  AppTheme.primary,
                  frequency: 2,
                  amplitude: 0.5,
                ),
              ),
              const SizedBox(height: 16),
              Builder(
                builder: (context) {
                  final live = AppScope.of(context).latestLiveStatus;
                  if (live == null || !live.isAlert) {
                    return const SizedBox.shrink();
                  }
                  return Container(
                    width: double.infinity,
                    margin: const EdgeInsets.only(bottom: 4),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 10,
                    ),
                    decoration: BoxDecoration(
                      color: AppTheme.warning.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: AppTheme.warning.withOpacity(0.4),
                      ),
                    ),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.warning_amber_rounded,
                          color: AppTheme.warning,
                          size: 18,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            '${live.scenarioLabel} algılandı. Oturun ve sakin olun.',
                            style: const TextStyle(
                              color: AppTheme.warning,
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.smart_toy_outlined, size: 18),
                  label: const Text('Bu durumu asistana sor'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppTheme.primary,
                    side: BorderSide(color: AppTheme.primary.withOpacity(0.4)),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                  ),
                  onPressed: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => const HealthAssistantScreen(),
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _statusBanner(LiveStatus live) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.surface.withOpacity(0.4),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color:
              live.isAlert ? AppTheme.warning.withOpacity(0.6) : Colors.white10,
        ),
      ),
      child: Row(
        children: [
          Icon(
            live.isAlert
                ? Icons.warning_amber_rounded
                : Icons.check_circle_outline,
            size: 14,
            color: live.isAlert ? AppTheme.warning : AppTheme.success,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              live.scenarioLabel,
              style: TextStyle(
                color: live.isAlert ? AppTheme.warning : Colors.white54,
                fontSize: 12,
              ),
            ),
          ),
          Text(
            _timeStr(live.timestamp),
            style: const TextStyle(color: Colors.white30, fontSize: 10),
          ),
        ],
      ),
    );
  }

  Widget _movementCard(LiveStatus live) {
    final score = (live.motionScore.clamp(0.0, 1.0) * 100).toStringAsFixed(0);
    final color = live.motionScore > 0.65 ? AppTheme.warning : AppTheme.primary;
    return GlassCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.directions_walk_outlined, color: color, size: 18),
              const SizedBox(width: 8),
              Text(
                'HAREKET',
                style: TextStyle(
                  color: color.withOpacity(0.8),
                  fontSize: 10,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const Spacer(),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                score,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 32,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const Padding(
                padding: EdgeInsets.only(left: 4, bottom: 4),
                child: Text(
                  '%',
                  style: TextStyle(color: Colors.white54, fontSize: 12),
                ),
              ),
            ],
          ),
          Text(
            _motionLabel(live.motionScore),
            style: const TextStyle(color: Colors.white38, fontSize: 11),
          ),
        ],
      ),
    );
  }

  String _timeStr(DateTime dt) {
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    final s = dt.second.toString().padLeft(2, '0');
    return '$h:$m:$s';
  }

  String _motionLabel(double motionScore) {
    final pct = motionScore * 100;
    if (pct < 10) return 'Sakin';
    if (pct < 30) return 'Hafif hareket';
    if (pct < 65) return 'Hareketli';
    return 'Yoğun hareket';
  }

  Widget _valuePlaceholderCard(String title, String value, Color color) {
    return GlassCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              color: color.withOpacity(0.8),
              fontSize: 10,
              fontWeight: FontWeight.bold,
            ),
          ),
          const Spacer(),
          Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 28,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMonitorCard(
    String title,
    String value,
    Color color,
    Widget chart,
  ) {
    return GlassCard(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: Text(
                  title,
                  style: AppTheme.darkTheme.textTheme.titleMedium?.copyWith(
                    color: Colors.white70,
                    fontSize: 14,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Text(
                value,
                style: AppTheme.darkTheme.textTheme.titleLarge?.copyWith(
                  color: color,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          SizedBox(height: 120, child: chart),
        ],
      ),
    );
  }

  Widget _buildSineWaveChart(
    Color color, {
    double frequency = 1,
    double amplitude = 1,
  }) {
    final spots = <FlSpot>[];
    for (double i = 0; i < 20; i += 0.2) {
      spots.add(
        FlSpot(
          i,
          amplitude * 3 +
              (amplitude * 2) * (i.toInt().isEven ? 0.3 : -0.3) * frequency,
        ),
      );
    }

    return LineChart(
      LineChartData(
        gridData: FlGridData(
          show: true,
          drawVerticalLine: true,
          getDrawingHorizontalLine: (value) => FlLine(
            color: Colors.white.withOpacity(0.05),
            strokeWidth: 1,
            dashArray: [5, 5],
          ),
          getDrawingVerticalLine: (value) => FlLine(
            color: Colors.white.withOpacity(0.05),
            strokeWidth: 1,
            dashArray: [5, 5],
          ),
        ),
        titlesData: const FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        minX: 0,
        maxX: 20,
        minY: 0,
        maxY: 6,
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            color: color,
            barWidth: 3,
            isStrokeCapRound: true,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              color: color.withOpacity(0.1),
            ),
          ),
        ],
      ),
    );
  }
}
