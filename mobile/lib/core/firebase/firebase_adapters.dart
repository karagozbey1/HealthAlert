import '../models/alert_event.dart';
import '../models/app_settings.dart';
import '../models/history_item.dart';
import '../models/user_profile.dart';

/// Firebase alanlarını mobil uygulama tiplerine dönüştüren yardımcı yapıdır.
class FirestoreAlertAdapter {
  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
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

/// Firebase alanlarını mobil uygulama tiplerine dönüştüren yardımcı yapıdır.
class FirestoreUserAdapter {
  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  Map<String, dynamic> toFirestore(UserProfile profile) => profile.toJson();
}

/// Firebase alanlarını mobil uygulama tiplerine dönüştüren yardımcı yapıdır.
class FirestoreSettingsAdapter {
  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  Map<String, dynamic> toFirestore(AppSettings settings) => settings.toJson();
}

/// Firebase alanlarını mobil uygulama tiplerine dönüştüren yardımcı yapıdır.
class FirestoreHistoryAdapter {
  /// HealthAlert akışında kullanılan yardımcı işlemi güvenli şekilde yürütür.
  Map<String, dynamic> toFirestore(HistoryItem item) => item.toJson();
}
