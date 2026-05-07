import 'package:flutter/material.dart';
import '../../../core/models/history_item.dart';
import '../../../core/models/user_profile.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import '../../widgets/severity_badge.dart';

class RelativeHistoryScreen extends StatefulWidget {
  const RelativeHistoryScreen({super.key});

  @override
  State<RelativeHistoryScreen> createState() => _RelativeHistoryScreenState();
}

class _RelativeHistoryScreenState extends State<RelativeHistoryScreen> {
  bool _loading = false;
  bool _refreshing = false;
  UserProfile? _selectedUser;
  List<HistoryItem> _history = [];

  /// Widget durumunu başlatır.
  @override
  void initState() {
    super.initState();
    _init();
  }

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

  Future<void> _loadHistory({bool isRefresh = false}) async {
    if (_selectedUser == null) return;
    if (!isRefresh || _history.isEmpty) {
      if (mounted) setState(() => _loading = true);
    } else {
      if (mounted) setState(() => _refreshing = true);
    }
    try {
      final app = AppScope.of(context);
      _history = await app.getHistoryForUser(_selectedUser!.id);
    } catch (e) {
      debugPrint('[RelativeHistory] _loadHistory error: $e');
    } finally {
      if (mounted) setState(() { _loading = false; _refreshing = false; });
    }
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final users = app.monitoredUsers;

    return SingleChildScrollView(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16, bottom: 100),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Geçmiş', style: AppTheme.darkTheme.textTheme.displaySmall),
          const SizedBox(height: 16),

          if (users.length > 1) ...[
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: users.map((u) {
                  final selected = u.id == _selectedUser?.id;
                  return GestureDetector(
                    onTap: () {
                      setState(() => _selectedUser = u);
                      _loadHistory();
                    },
                    child: Container(
                      margin: const EdgeInsets.only(right: 8),
                      padding:
                          const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      decoration: BoxDecoration(
                        color: selected
                            ? Colors.greenAccent.withOpacity(0.2)
                            : AppTheme.surface.withOpacity(0.3),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: selected
                              ? Colors.greenAccent.withOpacity(0.6)
                              : Colors.white12,
                        ),
                      ),
                      child: Text(
                        u.fullName.split(' ').first,
                        style: TextStyle(
                          color: selected ? Colors.greenAccent : Colors.white54,
                          fontWeight: selected ? FontWeight.bold : FontWeight.normal,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
            const SizedBox(height: 16),
          ],

          if (_loading)
            const Center(child: CircularProgressIndicator(color: Colors.greenAccent))
          else if (_history.isEmpty)
            GlassCard(
              padding: const EdgeInsets.all(32),
              child: Center(
                child: Column(
                  children: [
                    const Icon(Icons.history_toggle_off_outlined,
                        size: 40, color: Colors.white24),
                    const SizedBox(height: 12),
                    Text(
                      _selectedUser != null
                          ? '${_selectedUser!.fullName} için geçmiş yok'
                          : 'Hasta seçilmedi',
                      style: const TextStyle(color: Colors.white38),
                    ),
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
                        color: Colors.white, fontWeight: FontWeight.w600, fontSize: 13)),
                if (item.subtitle.isNotEmpty)
                  Text(item.subtitle,
                      style: const TextStyle(color: Colors.white54, fontSize: 11)),
                const SizedBox(height: 4),
                Text(_formatDate(item.timestamp),
                    style: const TextStyle(color: Colors.white30, fontSize: 10)),
              ],
            ),
          ),
          SeverityBadge(severity: item.severity, compact: true),
        ],
      ),
    );
  }

  String _formatDate(DateTime dt) {
    return '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')}/${dt.year} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }
}
