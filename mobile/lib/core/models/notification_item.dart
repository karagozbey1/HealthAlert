import 'enums.dart';

class NotificationItem {
  const NotificationItem({
    required this.id,
    required this.title,
    required this.body,
    required this.channel,
    required this.createdAt,
    required this.read,
    this.senderId,
    this.recipientId,
    this.notificationType,
    this.referenceId,
    this.referenceType,
  });

  final String id;
  final String title;
  final String body;
  final NotificationChannel channel;
  final DateTime createdAt;
  final bool read;
  final String? senderId;
  final String? recipientId;
  final String? notificationType;
  final String? referenceId;
  final String? referenceType;

  NotificationItem copyWith({bool? read}) {
    return NotificationItem(
      id: id,
      title: title,
      body: body,
      channel: channel,
      createdAt: createdAt,
      read: read ?? this.read,
      senderId: senderId,
      recipientId: recipientId,
      notificationType: notificationType,
      referenceId: referenceId,
      referenceType: referenceType,
    );
  }

  static NotificationItem fromJson(Map<String, dynamic> json) =>
      NotificationItem(
        id: json['id'] as String,
        title: json['title'] as String? ?? '',
        body: json['body'] as String? ?? '',
        channel: NotificationChannel.inApp,
        createdAt: json['created_at'] != null
            ? DateTime.parse(json['created_at'] as String)
            : DateTime.now(),
        read: json['is_read'] as bool? ?? false,
        senderId: json['sender_id'] as String?,
        recipientId: json['recipient_id'] as String?,
        notificationType: json['notification_type'] as String?,
        referenceId: json['reference_id'] as String?,
        referenceType: json['reference_type'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'body': body,
        'created_at': createdAt.toIso8601String(),
        'is_read': read,
        'sender_id': senderId,
        'recipient_id': recipientId,
        'notification_type': notificationType,
        'reference_id': referenceId,
        'reference_type': referenceType,
      };
}
