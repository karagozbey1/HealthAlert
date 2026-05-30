import 'package:flutter/material.dart';
import '../../../core/models/history_item.dart';
import '../../../core/models/user_profile.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import '../../widgets/severity_badge.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class RelativeHistoryScreen extends StatefulWidget {
  const RelativeHistoryScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<RelativeHistoryScreen> createState() => _RelativeHistoryScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _RelativeHistoryScreenState extends State<RelativeHistoryScreen> {
  bool _loading = false;
  UserProfile? _selectedUser;
  List<HistoryItem> _history = [];

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    _init();
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Future<void> _init() async {
    if (mounted) setState(() => _loading = true);
    try {
      final app = AppScope.of(context);
      if (app.monitoredUsers.isEmpty) {
        await app.loadMonitoredUsers();
      }
      if (app.monitoredUsers.isNotEmpty && _selectedUser == null) {
        _selectedUser = app.monitoredUsers.first;
        await _loadHistory();
        return;
      }
    } catch (e) {
      debugPrint('[RelativeHistory] _init error: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Ekranda kullanılacak verileri ilgili kaynaktan yükler.
  Future<void> _loadHistory({bool isRefresh = false}) async {
    if (_selectedUser == null) return;
    if (!isRefresh || _history.isEmpty) {
      if (mounted) setState(() => _loading = true);
    }
    try {
      final app = AppScope.of(context);
      _history = await app.getHistoryForUser(_selectedUser!.id);
    } catch (e) {
      debugPrint('[RelativeHistory] _loadHistory error: $e');
    } finally {
      if (mounted)
        setState(() {
          _loading = false;
        });
    }
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final users = app.monitoredUsers;

    // Reactively auto-select first user if the AppController now has users
    // but our local state hasn't caught up yet (e.g. fast navigation).
    if (_selectedUser == null && users.isNotEmpty && !_loading) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _selectedUser == null) {
          setState(() => _selectedUser = users.first);
          _loadHistory();
        }
      });
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16, bottom: 100),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Geçmiş', style: AppTheme.darkTheme.textTheme.displaySmall),
          const SizedBox(height: 16),
          if (users.isNotEmpty) ...[
            _buildPatientCards(users),
            const SizedBox(height: 16),
          ],
          if (_loading)
            const Center(
                child: CircularProgressIndicator(color: Colors.greenAccent))
          else if (users.isEmpty)
            GlassCard(
              padding: const EdgeInsets.all(32),
              child: const Center(
                child: Column(
                  children: [
                    Icon(Icons.group_off_outlined,
                        size: 40, color: Colors.white24),
                    SizedBox(height: 12),
                    Text(
                      'Henüz bağlı hasta yok',
                      style: TextStyle(color: Colors.white38),
                    ),
                  ],
                ),
              ),
            )
          else if (_history.isEmpty)
            GlassCard(
              padding: const EdgeInsets.all(32),
              child: Center(
                child: Column(
                  children: [
                    const Icon(Icons.history_toggle_off_outlined,
                        size: 40, color: Colors.white24),
                    const SizedBox(height: 12),
                    const Text('Henüz geçmiş kaydı yok',
                        style: TextStyle(color: Colors.white38)),
                    if (_selectedUser != null) ...[
                      const SizedBox(height: 4),
                      Text(
                        _selectedUser!.fullName,
                        style: const TextStyle(
                            color: Colors.white24, fontSize: 12),
                      ),
                    ],
                    if (app.isBackendMode && _selectedUser != null) ...[
                      const SizedBox(height: 8),
                      const Text(
                        'Canlı modda henüz kayıtlı olay bulunmuyor.',
                        style: TextStyle(color: Colors.white24, fontSize: 11),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ],
                ),
              ),
            )
          else
            ..._history.map((item) => _historyTile(item)),
        ],
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildPatientCards(List<UserProfile> users) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: users.map((u) {
          final selected = u.id == _selectedUser?.id;
          return GestureDetector(
            onTap: () {
              setState(() {
                _selectedUser = u;
                _history = [];
              });
              _loadHistory();
            },
            child: Container(
              width: 240,
              margin: const EdgeInsets.only(right: 10),
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: selected
                    ? Colors.greenAccent.withOpacity(0.16)
                    : AppTheme.surface.withOpacity(0.38),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: selected
                      ? Colors.greenAccent.withOpacity(0.55)
                      : Colors.white12,
                ),
              ),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 18,
                    backgroundColor: Colors.greenAccent.withOpacity(0.14),
                    child: Text(
                      u.fullName.isNotEmpty ? u.fullName[0].toUpperCase() : '?',
                      style: const TextStyle(
                          color: Colors.greenAccent,
                          fontWeight: FontWeight.bold),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          u.fullName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w600,
                              fontSize: 13),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          selected ? 'Geçmiş açık' : 'Geçmişi gör',
                          style: TextStyle(
                              color: selected
                                  ? Colors.greenAccent
                                  : Colors.white38,
                              fontSize: 11),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Widget _historyTile(HistoryItem item) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        color: AppTheme.surface.withOpacity(0.4),
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
                      style:
                          const TextStyle(color: Colors.white54, fontSize: 11)),
                const SizedBox(height: 4),
                Text(_formatDate(item.timestamp),
                    style:
                        const TextStyle(color: Colors.white30, fontSize: 10)),
              ],
            ),
          ),
          SeverityBadge(severity: item.severity, compact: true),
        ],
      ),
    );
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  String _formatDate(DateTime dt) {
    return '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')}/${dt.year} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }
}
