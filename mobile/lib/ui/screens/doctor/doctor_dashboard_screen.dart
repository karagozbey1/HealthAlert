import 'dart:async';

import 'package:flutter/material.dart';
import '../../../core/models/live_status.dart';
import '../../../core/models/user_profile.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import 'patient_detail_screen.dart';
import '../self/redeem_code_screen.dart';
class DoctorDashboardScreen extends StatefulWidget {
  const DoctorDashboardScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<DoctorDashboardScreen> createState() => _DoctorDashboardScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _DoctorDashboardScreenState extends State<DoctorDashboardScreen> {
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
      _startAutoRefresh(); // reschedule with recalculated interval
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
              '[DoctorDashboard] Live load failed for ${user.id}: $error');
        }
      }
    } catch (e) {
      debugPrint('[DoctorDashboard] _loadData error: $e');
    } finally {
      _loadInProgress = false;
      if (mounted)
        setState(() {
          _loading = false;
          _refreshing = false;
        });
    }
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final patients = app.monitoredUsers;
    final name = app.user?.fullName.split(' ').first ?? 'Doktor';
    final statuses = patients
        .map((p) => app.monitoredLiveStatuses[p.id] ?? _liveData[p.id])
        .whereType<LiveStatus>()
        .toList();
    final alertCount = statuses.where((s) => s.isAlert).length;
    final avgRisk = statuses.isEmpty
        ? 0.0
        : statuses.map((s) => s.riskScore).reduce((a, b) => a + b) /
            statuses.length;

    return SingleChildScrollView(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16, bottom: 100),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Dr. $name', style: AppTheme.darkTheme.textTheme.displayMedium),
          const SizedBox(height: 4),
          Row(
            children: [
              Text(
                '${patients.length} hasta izleniyor',
                style: AppTheme.darkTheme.textTheme.bodyMedium
                    ?.copyWith(color: Colors.white54),
              ),
              const SizedBox(width: 10),
              if (_refreshing)
                const SizedBox(
                  width: 10,
                  height: 10,
                  child: CircularProgressIndicator(
                      strokeWidth: 1.5, color: Colors.amberAccent),
                )
              else
                const Icon(Icons.autorenew, size: 12, color: Colors.white24),
            ],
          ),
          const SizedBox(height: 14),
          GlassCard(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(
              children: [
                Expanded(
                    child: _summaryMetric(
                        'Alarm', '$alertCount', AppTheme.warning)),
                Expanded(
                  child: _summaryMetric(
                    'Ortalama Risk',
                    '%${(avgRisk * 100).toStringAsFixed(0)}',
                    AppTheme.primary,
                  ),
                ),
                Expanded(
                  child: _summaryMetric(
                    'Mod',
                    app.isBackendMode ? 'Canlı' : 'Demo',
                    app.isBackendMode ? AppTheme.success : Colors.amberAccent,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          if (_loading)
            const Center(
                child: Padding(
              padding: EdgeInsets.all(48),
              child: CircularProgressIndicator(color: Colors.amberAccent),
            ))
          else if (patients.isEmpty)
            _buildEmptyState()
          else ...[
            ...patients.map((p) => _patientCard(p)),
          ],
          const SizedBox(height: 16),
          if (_refreshing)
            const LinearProgressIndicator(
                color: Colors.amberAccent, backgroundColor: Colors.transparent)
          else
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.autorenew, color: Colors.white24, size: 13),
                  const SizedBox(width: 6),
                  const Text('Otomatik güncelleniyor · 3 sn',
                      style: TextStyle(color: Colors.white24, fontSize: 11)),
                ],
              ),
            ),
        ],
      ),
    );
  }
  Widget _summaryMetric(String label, String value, Color color) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: const TextStyle(color: Colors.white38, fontSize: 10)),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(
              color: color, fontWeight: FontWeight.bold, fontSize: 15),
        ),
      ],
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
              backgroundColor: Colors.amberAccent,
              foregroundColor: Colors.black87,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ],
      ),
    );
  }
  Widget _patientCard(UserProfile patient) {
    final app = AppScope.of(context);
    final live = app.monitoredLiveStatuses[patient.id] ?? _liveData[patient.id];
    final hasAlert = live?.isAlert ?? false;

    return GestureDetector(
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute(
            builder: (_) => PatientDetailScreen(patient: patient)),
      ),
      child: Container(
        margin: const EdgeInsets.only(bottom: 14),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          color: AppTheme.surface.withOpacity(0.5),
          border: Border.all(
            color:
                hasAlert ? Colors.redAccent.withOpacity(0.5) : Colors.white10,
          ),
        ),
        child: Column(
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundColor: Colors.amberAccent.withOpacity(0.15),
                  child: Text(
                    patient.fullName.isNotEmpty
                        ? patient.fullName[0].toUpperCase()
                        : '?',
                    style: const TextStyle(
                        color: Colors.amberAccent,
                        fontWeight: FontWeight.bold,
                        fontSize: 18),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(patient.fullName,
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold,
                              fontSize: 15)),
                      Text(patient.email,
                          style: const TextStyle(
                              color: Colors.white38, fontSize: 12)),
                    ],
                  ),
                ),
                if (hasAlert)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.redAccent.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(10),
                      border:
                          Border.all(color: Colors.redAccent.withOpacity(0.4)),
                    ),
                    child: const Text('ALARM',
                        style: TextStyle(
                            color: Colors.redAccent,
                            fontSize: 10,
                            fontWeight: FontWeight.bold)),
                  ),
                const SizedBox(width: 6),
                const Icon(Icons.chevron_right, color: Colors.white30),
              ],
            ),
            if (live != null) ...[
              const SizedBox(height: 10),
              const Divider(color: Colors.white10),
              const SizedBox(height: 6),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _metric('HR', live.heartRate.toStringAsFixed(0), 'bpm',
                      AppTheme.secondary),
                  _metric('SpO₂', live.spo2.toStringAsFixed(1), '%',
                      AppTheme.primary),
                  _metric(
                    'Risk',
                    '${(live.riskScore * 100).toStringAsFixed(0)}%',
                    '',
                    live.riskScore > 0.6 ? AppTheme.warning : AppTheme.success,
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Builder(builder: (_) {
                final diff = DateTime.now().difference(live.timestamp);
                final isStale = diff.inSeconds > 60;
                final label = diff.inSeconds < 60
                    ? 'Son güncelleme: ${diff.inSeconds}s önce'
                    : diff.inMinutes < 60
                        ? 'Son güncelleme: ${diff.inMinutes} dk önce'
                        : 'Veri gecikti (${diff.inHours}sa)';
                return Row(children: [
                  Icon(
                      isStale ? Icons.warning_amber_rounded : Icons.access_time,
                      size: 11,
                      color: isStale ? AppTheme.warning : Colors.white24),
                  const SizedBox(width: 4),
                  Text(label,
                      style: TextStyle(
                          color: isStale ? AppTheme.warning : Colors.white30,
                          fontSize: 10)),
                ]);
              }),
            ],
          ],
        ),
      ),
    );
  }
  Widget _metric(String label, String value, String unit, Color color) {
    return Column(
      children: [
        Text(label,
            style: const TextStyle(color: Colors.white38, fontSize: 10)),
        const SizedBox(height: 2),
        RichText(
          text: TextSpan(
            children: [
              TextSpan(
                  text: value,
                  style: TextStyle(
                      color: color, fontWeight: FontWeight.bold, fontSize: 17)),
              if (unit.isNotEmpty)
                TextSpan(
                    text: ' $unit',
                    style:
                        const TextStyle(color: Colors.white38, fontSize: 10)),
            ],
          ),
        ),
      ],
    );
  }
}
class _RedeemCodeLauncher extends StatelessWidget {
  const _RedeemCodeLauncher();

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) => const RedeemCodeScreen();
}
