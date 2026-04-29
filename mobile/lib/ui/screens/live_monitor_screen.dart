import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';
import '../../ui/widgets/live_value_card.dart';
import '../../ui/widgets/empty_state_widget.dart';
import 'health_assistant_screen.dart';

class LiveMonitorScreen extends StatefulWidget {
  const LiveMonitorScreen({super.key});

  @override
  State<LiveMonitorScreen> createState() => _LiveMonitorScreenState();
}

class _LiveMonitorScreenState extends State<LiveMonitorScreen> with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;

  /// Widget durumunu başlatır.
  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
       vsync: this,
       duration: const Duration(seconds: 1),
    )..repeat(reverse: true);
  }

  /// Kaynakları serbest bırakır.
  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  /// Widget ağacını oluşturur.
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
                    "Canlı İzleme",
                    style: AppTheme.darkTheme.textTheme.displaySmall,
                   ),
                   FadeTransition(
                     opacity: _pulseController,
                     child: Container(
                       padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                       decoration: BoxDecoration(
                         color: AppTheme.critical.withOpacity(0.2),
                         border: Border.all(color: AppTheme.critical),
                         borderRadius: BorderRadius.circular(20),
                       ),
                       child: Row(
                         children: [
                           const Icon(Icons.fiber_manual_record, color: AppTheme.critical, size: 10),
                           const SizedBox(width: 8),
                           Text(
                             "CANLI",
                             style: AppTheme.darkTheme.textTheme.labelSmall?.copyWith(
                               color: AppTheme.critical,
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

               Builder(builder: (context) {
                 final app = AppScope.of(context);
                 final live = app.latestLiveStatus;
                 final isBackend = app.isBackendMode;

                 if (live == null && isBackend) {
                   return const EmptyStateWidget(
                     icon: Icons.monitor_heart_outlined,
                     title: 'Henüz canlı veri yok',
                     subtitle: 'Sunucudan veri bekleniyor. Cihaz bağlantısı '
                         'kurulduktan sonra burada gerçek zamanlı veriler görünecek.',
                   );
                 }

                 return Column(
                   children: [
                     if (live != null && live.scenarioLabel.isNotEmpty)
                       Container(
                         width: double.infinity,
                         margin: const EdgeInsets.only(bottom: 12),
                         padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                         decoration: BoxDecoration(
                           color: AppTheme.surface.withOpacity(0.4),
                           borderRadius: BorderRadius.circular(10),
                           border: Border.all(
                             color: live.isAlert
                                 ? AppTheme.warning.withOpacity(0.6)
                                 : Colors.white10,
                           ),
                         ),
                         child: Row(
                           children: [
                             Icon(
                               live.isAlert ? Icons.warning_amber_rounded : Icons.check_circle_outline,
                               size: 14,
                               color: live.isAlert ? AppTheme.warning : AppTheme.success,
                             ),
                             const SizedBox(width: 8),
                             Text(
                               live.scenarioLabel,
                               style: TextStyle(
                                 color: live.isAlert ? AppTheme.warning : Colors.white54,
                                 fontSize: 12,
                               ),
                             ),
                             const Spacer(),
                             Text(
                               _timeStr(live.timestamp),
                               style: const TextStyle(color: Colors.white30, fontSize: 10),
                             ),
                           ],
                         ),
                       ),
                     Row(
                       children: [
                         Expanded(
                           child: SizedBox(
                             height: 130,
                             child: live != null
                                 ? LiveValueCard.heartRate(live)
                                 : _buildMonitorCard("KALP ATIŞI", "-- BPM", AppTheme.secondary, _buildSineWaveChart(AppTheme.secondary)),
                           ),
                         ),
                         const SizedBox(width: 12),
                         Expanded(
                           child: SizedBox(
                             height: 130,
                             child: live != null
                                 ? LiveValueCard.spo2(live)
                                 : _buildMonitorCard("SpO₂", "-- %", AppTheme.primary, _buildSineWaveChart(AppTheme.primary)),
                           ),
                         ),
                       ],
                     ),
                     const SizedBox(height: 12),
                     SizedBox(
                       width: double.infinity,
                       height: 130,
                       child: live != null
                           ? LiveValueCard.riskScore(live)
                           : _buildMonitorCard("RİSK SKORU", "--", AppTheme.success, _buildSineWaveChart(AppTheme.success)),
                     ),
                   ],
                 );
               }),
               const SizedBox(height: 16),

               Builder(builder: (context) {
                 final app = AppScope.of(context);
                 if (app.isBackendMode) {
                   return _buildMonitorCard(
                     "KALP ATIŞI (EKG)",
                     "",
                     AppTheme.secondary,
                     const Center(
                       child: Text(
                         'EKG dalga verisi henüz mevcut değil.\nCihazdan veri akışı bekleniyor.',
                         textAlign: TextAlign.center,
                         style: TextStyle(color: Colors.white30, fontSize: 12),
                       ),
                     ),
                   );
                 }
                 return _buildMonitorCard(
                   "KALP ATIŞI (EKG)",
                   "",
                   AppTheme.secondary,
                   _buildSineWaveChart(AppTheme.secondary),
                 );
               }),
               const SizedBox(height: 16),

               Builder(builder: (context) {
                 final app = AppScope.of(context);
                 if (app.isBackendMode) {
                   return _buildMonitorCard(
                     "OKSİJEN SATÜRASYONU",
                     "",
                     AppTheme.primary,
                     const Center(
                       child: Text(
                         'SpO2 dalga verisi henüz mevcut değil.\nCihazdan veri akışı bekleniyor.',
                         textAlign: TextAlign.center,
                         style: TextStyle(color: Colors.white30, fontSize: 12),
                       ),
                     ),
                   );
                 }
                 return _buildMonitorCard(
                   "OKSİJEN SATÜRASYONU",
                   "",
                   AppTheme.primary,
                   _buildSineWaveChart(AppTheme.primary, frequency: 2, amplitude: 0.5),
                 );
               }),
               const SizedBox(height: 16),

               Builder(builder: (context) {
                 final app = AppScope.of(context);
                 final isBackend = app.isBackendMode;
                 final sourceLabel = isBackend ? 'CANLI SUNUCU VERİSİ' : 'DEMO / SİMÜLASYON';
                 final sourceColor = isBackend ? Colors.greenAccent : Colors.orangeAccent;
                 return Container(
                   width: double.infinity,
                   padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                   decoration: BoxDecoration(
                     color: sourceColor.withOpacity(0.07),
                     borderRadius: BorderRadius.circular(10),
                     border: Border.all(color: sourceColor.withOpacity(0.25)),
                   ),
                   child: Row(
                     children: [
                       Icon(isBackend ? Icons.wifi : Icons.wifi_off,
                           size: 13, color: sourceColor),
                       const SizedBox(width: 8),
                       Text(
                         sourceLabel,
                         style: TextStyle(
                             color: sourceColor,
                             fontSize: 11,
                             fontWeight: FontWeight.bold),
                       ),
                       if (!isBackend) ...
                         [
                           const Spacer(),
                           const Text(
                             'Gerçek veriler için sunucuya bağlanın',
                             style: TextStyle(color: Colors.white30, fontSize: 10),
                           ),
                         ],
                     ],
                   ),
                 );
               }),
               const SizedBox(height: 16),

               Builder(builder: (context) {
                 final live = AppScope.of(context).latestLiveStatus;
                 if (live == null) return const SizedBox.shrink();
                 final isAlertScenario = live.isAlert;
                 if (!isAlertScenario) return const SizedBox.shrink();
                 return Container(
                   width: double.infinity,
                   margin: const EdgeInsets.only(bottom: 4),
                   padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                   decoration: BoxDecoration(
                     color: AppTheme.warning.withOpacity(0.1),
                     borderRadius: BorderRadius.circular(12),
                     border: Border.all(color: AppTheme.warning.withOpacity(0.4)),
                   ),
                   child: Row(
                     children: [
                       const Icon(Icons.warning_amber_rounded,
                           color: AppTheme.warning, size: 18),
                       const SizedBox(width: 10),
                       Expanded(
                         child: Text(
                           '${live.scenarioLabel} algılandı — Oturun ve sakin olun.',
                           style: const TextStyle(
                               color: AppTheme.warning,
                               fontSize: 12,
                               fontWeight: FontWeight.w600),
                         ),
                       ),
                     ],
                   ),
                 );
               }),

               const SizedBox(height: 8),
               SizedBox(
                 width: double.infinity,
                 child: OutlinedButton.icon(
                   icon: const Icon(Icons.smart_toy_outlined, size: 18),
                   label: const Text('Bu durumu asistana sor'),
                   style: OutlinedButton.styleFrom(
                     foregroundColor: AppTheme.primary,
                     side: BorderSide(color: AppTheme.primary.withOpacity(0.4)),
                     shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                     padding: const EdgeInsets.symmetric(vertical: 12),
                   ),
                   onPressed: () {
                     Navigator.push(
                       context,
                       MaterialPageRoute(builder: (_) => const HealthAssistantScreen()),
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

  String _timeStr(DateTime dt) {
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    final s = dt.second.toString().padLeft(2, '0');
    return '$h:$m:$s';
  }

  Widget _buildMonitorCard(String title, String value, Color color, Widget chart) {
    return GlassCard(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                title,
                style: AppTheme.darkTheme.textTheme.titleMedium?.copyWith(
                  color: Colors.white70,
                  fontSize: 14,
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
          SizedBox(
            height: 120,
            child: chart,
          ),
        ],
      ),
    );
  }

  Widget _buildSineWaveChart(Color color, {double frequency = 1, double amplitude = 1}) {
    final List<FlSpot> spots = [];
    for (double i = 0; i < 20; i += 0.2) {
      spots.add(FlSpot(i, amplitude * 3 + (amplitude * 2) * (i.toInt().isEven ? 0.3 : -0.3))); // Mock "noisy" sine
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
          ),
        ),
        titlesData: FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        minX: 0,
        maxX: 20,
        minY: 0,
        maxY: 10,
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            color: color,
            barWidth: 3,
            isStrokeCapRound: true,
            dotData: FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              color: color.withOpacity(0.1),
            ),
          ),
        ],
      ),
    );
  }

   Widget _buildMultiLineChart(Color color) {
    return LineChart(
      LineChartData(
        gridData: FlGridData(show: false),
        titlesData: FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        lineBarsData: [
          LineChartBarData(
            spots: [
              const FlSpot(0, 1), const FlSpot(2, 4), const FlSpot(4, 2), const FlSpot(6, 5), const FlSpot(8, 3),
            ],
            isCurved: true,
            color: color,
            barWidth: 2,
            dotData: FlDotData(show: false),
          ),
          LineChartBarData(
            spots: [
              const FlSpot(0, 2), const FlSpot(2, 2.5), const FlSpot(4, 3), const FlSpot(6, 2), const FlSpot(8, 4),
            ],
            isCurved: true,
            color: Colors.purple,
            barWidth: 2,
            dotData: FlDotData(show: false),
          ),
        ],
      ),
    );
  }
}
