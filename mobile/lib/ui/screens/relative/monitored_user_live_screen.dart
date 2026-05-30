import 'dart:async';
import 'package:flutter/material.dart';
import '../../../core/models/live_status.dart';
import '../../../core/models/user_profile.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import '../../widgets/live_value_card.dart';
import '../../widgets/severity_badge.dart';
class MonitoredUserLiveScreen extends StatefulWidget {
  final UserProfile user;
  const MonitoredUserLiveScreen({super.key, required this.user});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<MonitoredUserLiveScreen> createState() =>
      _MonitoredUserLiveScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _MonitoredUserLiveScreenState extends State<MonitoredUserLiveScreen> {
  LiveStatus? _live;
  bool _loading = true;
  Timer? _timer;
  StreamSubscription<LiveStatus?>? _firestoreSub;

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    _fetchLive();
    // Setup realtime updates after the first frame so context is ready.
    WidgetsBinding.instance.addPostFrameCallback((_) => _setupLiveUpdates());
  }
  void _setupLiveUpdates() {
    if (!mounted) return;
    final app = AppScope.of(context);
    if (app.isFirestoreSyncAvailable) {
      // Firestore realtime listener – preferred over polling.
      final stream = app.getFirestoreLiveStatusStream(widget.user.id);
      if (stream != null) {
        _firestoreSub = stream.listen(_onFirestoreLive, onError: (e) {
          debugPrint('[MonitoredUserLive] Firestore stream error: $e');
          // Fall back to timer if stream fails.
          _ensureTimerRunning();
        });
        return;
      }
    }
    // No Firestore: fall back to periodic polling.
    _ensureTimerRunning();
  }
  void _ensureTimerRunning() {
    _timer ??= Timer.periodic(const Duration(seconds: 5), (_) => _fetchLive());
  }
  void _onFirestoreLive(LiveStatus? status) {
    if (!mounted || status == null) return;
    setState(() {
      _live = status;
      _loading = false;
    });
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  @override
  void dispose() {
    _timer?.cancel();
    _firestoreSub?.cancel();
    super.dispose();
  }
  Future<void> _fetchLive() async {
    if (!mounted) return;
    try {
      final status =
          await AppScope.of(context).getLiveStatusForUser(widget.user.id);
      if (mounted) {
        setState(() {
          _live = status;
          _loading = false;
        });
      }
    } catch (e) {
      debugPrint('[MonitoredUserLive] _fetchLive error: $e');
      if (mounted) setState(() => _loading = false);
    }
  }

  bool get _isStale =>
      _live != null &&
      DateTime.now().difference(_live!.timestamp).inSeconds > 60;

  bool get _isDelayed =>
      _live != null &&
      DateTime.now().difference(_live!.timestamp).inSeconds > 30;

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final live = _live;
    final isAlert = live?.isAlert ?? false;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Text(widget.user.fullName),
        actions: [
          if (isAlert)
            Container(
              margin: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(
                color: AppTheme.critical.withOpacity(0.2),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppTheme.critical.withOpacity(0.4)),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.warning_amber_rounded,
                      size: 14, color: AppTheme.critical),
                  SizedBox(width: 4),
                  Text('ALARM',
                      style: TextStyle(
                          color: AppTheme.critical,
                          fontSize: 11,
                          fontWeight: FontWeight.bold)),
                ],
              ),
            ),
        ],
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: Colors.greenAccent))
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  GlassCard(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        CircleAvatar(
                          radius: 26,
                          backgroundColor: Colors.greenAccent.withOpacity(0.15),
                          child: Text(
                            widget.user.fullName.isNotEmpty
                                ? widget.user.fullName[0].toUpperCase()
                                : '?',
                            style: const TextStyle(
                                color: Colors.greenAccent,
                                fontWeight: FontWeight.bold,
                                fontSize: 22),
                          ),
                        ),
                        const SizedBox(width: 16),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(widget.user.fullName,
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.bold,
                                    fontSize: 16)),
                            if (widget.user.phone != null)
                              Text(widget.user.phone!,
                                  style: const TextStyle(
                                      color: Colors.white38, fontSize: 13)),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (live != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Row(
                        children: [
                          Container(
                            width: 8,
                            height: 8,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: _isStale
                                  ? AppTheme.warning
                                  : isAlert
                                      ? AppTheme.critical
                                      : AppTheme.success,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            _isStale
                                ? 'Veri gecikti — ${_timeAgo(live.timestamp)}'
                                : _isDelayed
                                    ? 'Sinyal yavaş — ${_timeAgo(live.timestamp)}'
                                    : 'Son güncelleme: ${_timeAgo(live.timestamp)}',
                            style: TextStyle(
                              color:
                                  _isStale ? AppTheme.warning : Colors.white38,
                              fontSize: 12,
                            ),
                          ),
                          const Spacer(),
                          Text(
                            live.scenarioLabel,
                            style: TextStyle(
                              color:
                                  isAlert ? AppTheme.warning : Colors.white30,
                              fontSize: 11,
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (live != null) ...[
                    Row(
                      children: [
                        Expanded(
                            child: SizedBox(
                                height: 130,
                                child: LiveValueCard.heartRate(live))),
                        const SizedBox(width: 12),
                        Expanded(
                            child: SizedBox(
                                height: 130, child: LiveValueCard.spo2(live))),
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
            ),
    );
  }
  String _timeAgo(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inSeconds < 60) return '${diff.inSeconds} sn önce';
    if (diff.inMinutes < 60) return '${diff.inMinutes} dk önce';
    return '${diff.inHours} sa önce';
  }
}
