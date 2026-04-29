import 'package:flutter/material.dart';
import 'package:percent_indicator/circular_percent_indicator.dart';
import '../../core/models/enums.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';
import '../../ui/widgets/gradient_button.dart';

class PostEventMonitorScreen extends StatefulWidget {
  const PostEventMonitorScreen({super.key});

  @override
  State<PostEventMonitorScreen> createState() => _PostEventMonitorScreenState();
}

class _PostEventMonitorScreenState extends State<PostEventMonitorScreen> {
  String _lifecycleLabel(AlertLifecycleStatus s) {
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
        return 'OLAY SONRASI İZLEME';
      case AlertLifecycleStatus.closed:
        return 'KAPATILDI';
    }
  }

  List<Map<String, dynamic>> _timelineForStatus(AlertLifecycleStatus status) {
    return [
      {
        'time': '00:00',
        'status': 'Anomali tespit edildi ve alarm yükseltildi',
        'active': true,
      },
      {
        'time': '00:10',
        'status': status == AlertLifecycleStatus.emergencyRequested
            ? 'Kullanıcı tarafından acil yardım çağrıldı'
            : 'Kullanıcının iyi olduğu onayı işlendi',
        'active': true,
      },
      {
        'time': '00:30',
        'status': 'Olay sonrası izleme aktif',
        'active': true,
      },
      {
        'time': '02:00',
        'status': 'İzleme kapanışı bekleniyor',
        'active': false,
      },
    ];
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final active = app.activeAlert;
    if (active == null) {
      return Scaffold(
        backgroundColor: AppTheme.background,
        appBar: AppBar(
          title: const Text('Acil Durum Takibi'),
          backgroundColor: Colors.transparent,
        ),
        body: const Center(
          child: Text('Aktif olay sonrası izleme kaydı bulunamadı.'),
        ),
      );
    }

    final timeline = _timelineForStatus(active.status);
    final elapsed = active.countdownTotalSec - active.countdownRemainingSec;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        title: const Text("Acil Durum Takibi"),
        backgroundColor: Colors.transparent,
        automaticallyImplyLeading: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.close),
            onPressed: () => Navigator.pop(context),
          ),
        ],
      ),
      body: SingleChildScrollView(
         padding: const EdgeInsets.all(16),
         child: Column(
           children: [
             Center(
               child: CircularPercentIndicator(
                 radius: 100.0,
                 lineWidth: 12.0,
                 percent: active.countdownTotalSec > 0
                     ? (elapsed / active.countdownTotalSec).clamp(0.0, 1.0)
                     : 0.0,
                 center: Column(
                   mainAxisAlignment: MainAxisAlignment.center,
                   children: [
                     Text(
                       '${elapsed}s',
                       style: AppTheme.darkTheme.textTheme.displayMedium,
                     ),
                     Text(
                       _lifecycleLabel(active.status),
                       style: AppTheme.darkTheme.textTheme.labelSmall,
                     ),
                   ],
                 ),
                 progressColor: AppTheme.critical,
                 backgroundColor: AppTheme.surface,
                 circularStrokeCap: CircularStrokeCap.round,
                 animation: true,
               ),
             ),
             const SizedBox(height: 32),
             
             Text(
               "OLAY AKIŞI",
               style: AppTheme.darkTheme.textTheme.labelSmall?.copyWith(letterSpacing: 2),
             ),
             const SizedBox(height: 16),
             
             GlassCard(
               padding: const EdgeInsets.all(24),
               child: Column(
                 crossAxisAlignment: CrossAxisAlignment.start,
                 children: timeline.map((item) => _buildTimelineItem(item)).toList(),
               ),
             ),
             const SizedBox(height: 32),
             
             GradientButton(
               text: "DURUM NORMAL - KAPAT",
               gradient: const LinearGradient(colors: [AppTheme.textSecondary, Colors.grey]),
               onPressed: () async {
                 await app.closePostEvent();
                 if (!context.mounted) return;
                 Navigator.pop(context);
               },
             ),
           ],
         ),
      ),
    );
  }

  Widget _buildTimelineItem(Map<String, dynamic> item) {
    final bool active = item['active'];
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            children: [
              Container(
                 width: 12,
                 height: 12,
                 decoration: BoxDecoration(
                   color: active ? AppTheme.primary : Colors.grey,
                   shape: BoxShape.circle,
                   boxShadow: active ? [BoxShadow(color: AppTheme.primary.withOpacity(0.5), blurRadius: 10)] : [],
                 ),
              ),
              Container(
                width: 2,
                height: 30, // Connect line
                color: Colors.white10,
              ),
            ],
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item['time'],
                  style: TextStyle(color: active ? AppTheme.primary : Colors.grey, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 4),
                Text(
                  item['status'],
                  style: TextStyle(color: active ? Colors.white : Colors.white54),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
