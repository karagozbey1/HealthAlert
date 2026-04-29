import 'package:flutter/material.dart';
import '../../core/state/app_scope.dart';
import '../theme/app_theme.dart';
import '../widgets/notification_tile.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  bool _refreshing = false;

  Future<void> _refresh() async {
    setState(() => _refreshing = true);
    await AppScope.of(context).refreshNotifications();
    if (mounted) setState(() => _refreshing = false);
  }

  Future<void> _markAllRead() async {
    await AppScope.of(context).markNotificationsRead();
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final notifications = app.notifications;
    final unread = app.unreadNotifications;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Row(
          children: [
            const Text('Bildirimler'),
            if (unread > 0) ...[
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: AppTheme.critical.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppTheme.critical.withOpacity(0.4)),
                ),
                child: Text(
                  '$unread okunmamış',
                  style: const TextStyle(
                      color: AppTheme.critical, fontSize: 11, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ],
        ),
        actions: [
          if (unread > 0)
            TextButton.icon(
              onPressed: _markAllRead,
              icon: const Icon(Icons.done_all, size: 16, color: AppTheme.primary),
              label: const Text('Tümünü okundu yap',
                  style: TextStyle(color: AppTheme.primary, fontSize: 12)),
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        color: AppTheme.primary,
        child: notifications.isEmpty
            ? ListView(
                children: [
                  SizedBox(
                    height: MediaQuery.of(context).size.height * 0.6,
                    child: Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.notifications_none_outlined,
                              size: 64, color: Colors.white24),
                          const SizedBox(height: 16),
                          const Text('Henüz bildirim yok',
                              style: TextStyle(color: Colors.white38, fontSize: 16)),
                          const SizedBox(height: 8),
                          Text(
                            app.isBackendMode
                                ? 'Canlı modda henüz bildirim oluşmadı.\n'
                                  'Alarm veya anomali tespit edildiğinde burada görünecek.'
                                : 'Yenilemek için aşağı çekin.',
                            style: const TextStyle(color: Colors.white24, fontSize: 12),
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              )
            : ListView.separated(
                padding: const EdgeInsets.all(16),
                itemCount: notifications.length,
                separatorBuilder: (_, __) => const SizedBox(height: 8),
                itemBuilder: (context, index) {
                  return NotificationTile(notification: notifications[index]);
                },
              ),
      ),
    );
  }
}
