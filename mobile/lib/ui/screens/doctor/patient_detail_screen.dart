import 'dart:async';
import 'package:flutter/material.dart';
import '../../../core/models/alert_event.dart';
import '../../../core/models/history_item.dart';
import '../../../core/models/live_status.dart';
import '../../../core/models/user_profile.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import '../../widgets/live_value_card.dart';
import '../../widgets/severity_badge.dart';
import 'clinical_notes_screen.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class PatientDetailScreen extends StatefulWidget {
  final UserProfile patient;
  const PatientDetailScreen({super.key, required this.patient});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<PatientDetailScreen> createState() => _PatientDetailScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _PatientDetailScreenState extends State<PatientDetailScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  LiveStatus? _live;
  List<HistoryItem> _history = [];
  List<AlertEvent> _alerts = [];
  bool _loading = true;
  Timer? _liveTimer;
  StreamSubscription<LiveStatus?>? _firestoreSub;

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _load();
    WidgetsBinding.instance.addPostFrameCallback((_) => _setupLiveUpdates());
  }

  /// Canlı sağlık verisiyle ilgili okuma veya güncelleme işlemini yürütür.
  void _setupLiveUpdates() {
    if (!mounted) return;
    final app = AppScope.of(context);
    if (app.isFirestoreSyncAvailable) {
      final stream = app.getFirestoreLiveStatusStream(widget.patient.id);
      if (stream != null) {
        _firestoreSub = stream.listen(_onFirestoreLive,
            onError: (_) => _ensureTimerRunning());
        return;
      }
    }
    _ensureTimerRunning();
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  void _ensureTimerRunning() {
    _liveTimer ??=
        Timer.periodic(const Duration(seconds: 5), (_) => _fetchLive());
  }

  /// Canlı sağlık verisiyle ilgili okuma veya güncelleme işlemini yürütür.
  void _onFirestoreLive(LiveStatus? status) {
    if (!mounted || status == null) return;
    setState(() => _live = status);
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  @override
  void dispose() {
    _tabController.dispose();
    _liveTimer?.cancel();
    _firestoreSub?.cancel();
    super.dispose();
  }

  /// Ekranda kullanılacak verileri ilgili kaynaktan yükler.
  Future<void> _load() async {
    final app = AppScope.of(context);
    try {
      final live = await app.getLiveStatusForUser(widget.patient.id);
      final history = await app.getHistoryForUser(widget.patient.id);
      final alerts = await app.getAlertsForUser(widget.patient.id);
      if (mounted) {
        setState(() {
          _live = live;
          _history = history;
          _alerts = alerts;
        });
      }
    } catch (e) {
      debugPrint('[PatientDetail] _load error: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Canlı sağlık verisiyle ilgili okuma veya güncelleme işlemini yürütür.
  Future<void> _fetchLive() async {
    if (!mounted) return;
    try {
      final live =
          await AppScope.of(context).getLiveStatusForUser(widget.patient.id);
      if (mounted) setState(() => _live = live);
    } catch (error) {
      debugPrint(
          '[PatientDetail] Live fetch failed for ${widget.patient.id}: $error');
    }
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Text(widget.patient.fullName),
        actions: [
          TextButton.icon(
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(
                  builder: (_) => ClinicalNotesScreen(patient: widget.patient)),
            ),
            icon: const Icon(Icons.note_add_outlined,
                color: Colors.amberAccent, size: 18),
            label: const Text('Notlar',
                style: TextStyle(color: Colors.amberAccent)),
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          labelColor: Colors.amberAccent,
          unselectedLabelColor: Colors.white38,
          indicatorColor: Colors.amberAccent,
          tabs: const [
            Tab(text: 'Canlı'),
            Tab(text: 'Geçmiş'),
            Tab(text: 'Alarmlar'),
          ],
        ),
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: Colors.amberAccent))
          : TabBarView(
              controller: _tabController,
              children: [
                _buildLiveTab(),
                _buildHistoryTab(),
                _buildAlertsTab(),
              ],
            ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildLiveTab() {
    final live = _live;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          if (live != null) ...[
            if (live.scenarioLabel.isNotEmpty)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.only(bottom: 12),
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
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
                      live.isAlert
                          ? Icons.warning_amber_rounded
                          : Icons.check_circle_outline,
                      size: 14,
                      color: live.isAlert ? AppTheme.warning : AppTheme.success,
                    ),
                    const SizedBox(width: 8),
                    Text(live.scenarioLabel,
                        style: TextStyle(
                            color: live.isAlert
                                ? AppTheme.warning
                                : Colors.white54,
                            fontSize: 12)),
                  ],
                ),
              ),
            Row(
              children: [
                Expanded(
                    child: SizedBox(
                        height: 130, child: LiveValueCard.heartRate(live))),
                const SizedBox(width: 12),
                Expanded(
                    child:
                        SizedBox(height: 130, child: LiveValueCard.spo2(live))),
              ],
            ),
            const SizedBox(height: 12),
            SizedBox(
                width: double.infinity,
                height: 130,
                child: LiveValueCard.riskScore(live)),
          ] else
            GlassCard(
              padding: const EdgeInsets.all(32),
              child: const Center(
                child: Text('Canlı veri mevcut değil',
                    style: TextStyle(color: Colors.white38)),
              ),
            ),
        ],
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildHistoryTab() {
    if (_history.isEmpty) {
      return const Center(
          child: Text('Geçmiş verisi mevcut değil',
              style: TextStyle(color: Colors.white38)));
    }
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: _history.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (context, i) {
        final item = _history[i];
        return Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: AppTheme.surface.withOpacity(0.4),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.white10),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.title,
                        style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w600,
                            fontSize: 13)),
                    if (item.subtitle.isNotEmpty)
                      Text(item.subtitle,
                          style: const TextStyle(
                              color: Colors.white54, fontSize: 11)),
                    Text(_fmt(item.timestamp),
                        style: const TextStyle(
                            color: Colors.white30, fontSize: 10)),
                  ],
                ),
              ),
              SeverityBadge(severity: item.severity, compact: true),
            ],
          ),
        );
      },
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildAlertsTab() {
    if (_alerts.isEmpty) {
      return const Center(
          child: Text('Kayıtlı alarm yok',
              style: TextStyle(color: Colors.white38)));
    }
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: _alerts.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (context, i) {
        final alert = _alerts[i];
        return Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: AppTheme.surface.withOpacity(0.4),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.white10),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(alert.title,
                        style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w600,
                            fontSize: 13)),
                    if (alert.description.isNotEmpty)
                      Text(alert.description,
                          style: const TextStyle(
                              color: Colors.white54, fontSize: 11)),
                    Text(_fmt(alert.createdAt),
                        style: const TextStyle(
                            color: Colors.white30, fontSize: 10)),
                    const SizedBox(height: 4),
                    Text(
                      'Durum: ${alert.status.name}',
                      style:
                          const TextStyle(color: Colors.white38, fontSize: 11),
                    ),
                  ],
                ),
              ),
              SeverityBadge(severity: alert.severity, compact: true),
            ],
          ),
        );
      },
    );
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  String _fmt(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')}/${dt.year} '
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}
