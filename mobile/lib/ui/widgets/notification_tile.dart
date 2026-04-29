import 'package:flutter/material.dart';
import '../../core/models/enums.dart';
import '../../core/models/notification_item.dart';
import '../theme/app_theme.dart';

class NotificationTile extends StatelessWidget {
  final NotificationItem notification;
  final VoidCallback? onTap;

  const NotificationTile({super.key, required this.notification, this.onTap});

  Color get _channelColor {
    switch (notification.channel) {
      case NotificationChannel.inApp:
        return AppTheme.primary;
      case NotificationChannel.local:
        return AppTheme.warning;
    }
  }

  IconData get _channelIcon {
    switch (notification.channel) {
      case NotificationChannel.inApp:
        return Icons.notifications_outlined;
      case NotificationChannel.local:
        return Icons.notifications_active_outlined;
    }
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: notification.read
              ? Colors.transparent
              : AppTheme.surface.withOpacity(0.6),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: notification.read
                ? Colors.white10
                : _channelColor.withOpacity(0.3),
          ),
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _channelColor.withOpacity(0.15),
              ),
              child: Icon(_channelIcon, color: _channelColor, size: 18),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    notification.title,
                    style: TextStyle(
                      color: notification.read ? Colors.white54 : Colors.white,
                      fontWeight:
                          notification.read ? FontWeight.normal : FontWeight.bold,
                      fontSize: 13,
                    ),
                  ),
                  if (notification.body.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      notification.body,
                      style: const TextStyle(color: Colors.white38, fontSize: 11),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                  const SizedBox(height: 4),
                  Text(
                    _timeAgo(notification.createdAt),
                    style: const TextStyle(color: Colors.white30, fontSize: 10),
                  ),
                ],
              ),
            ),
            if (!notification.read)
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _channelColor,
                ),
              ),
          ],
        ),
      ),
    );
  }

  String _timeAgo(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inMinutes < 1) return 'Az önce';
    if (diff.inMinutes < 60) return '${diff.inMinutes} dk önce';
    if (diff.inHours < 24) return '${diff.inHours} sa önce';
    return '${diff.inDays} gün önce';
  }
}
