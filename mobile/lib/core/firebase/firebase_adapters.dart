import '../models/alert_event.dart';
import '../models/app_settings.dart';
import '../models/history_item.dart';
import '../models/user_profile.dart';

class FirestoreAlertAdapter {
  Map<String, dynamic> toFirestore(AlertEvent event) {
    return {
      'id': event.id,
      'title': event.title,
      'description': event.description,
      'severity': event.severity.name,
      'status': event.status.name,
      'createdAt': event.createdAt.toIso8601String(),
      'countdownTotalSec': event.countdownTotalSec,
      'countdownRemainingSec': event.countdownRemainingSec,
      'recommendations': event.recommendations,
      'relatedAnomalyId': event.relatedAnomalyId,
    };
  }
}

class FirestoreUserAdapter {
  Map<String, dynamic> toFirestore(UserProfile profile) => profile.toJson();
}

class FirestoreSettingsAdapter {
  Map<String, dynamic> toFirestore(AppSettings settings) => settings.toJson();
}

class FirestoreHistoryAdapter {
  Map<String, dynamic> toFirestore(HistoryItem item) => item.toJson();
}
