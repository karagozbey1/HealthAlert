// Asistan uç noktalarına erişip mobil modelleri dolduran servis katmanıdır.

import '../models/assistant_state.dart';
import 'api_client.dart';
import 'package:flutter/foundation.dart';

/// Bakım asistanı endpointlerinden mobil panel verilerini getirir.
class CareAssistantService {
  final ApiClient _api;

  CareAssistantService(this._api);

  /// Kullanıcıya ait güncel bakım asistanı durumunu backend'den getirir.
  Future<AssistantState?> getAssistantState(String userId) async {
    try {
      final data = await _api.get('/assistant/state/$userId');
      if (data is Map) {
        return AssistantState.fromJson(Map<String, dynamic>.from(data));
      }
    } catch (error) {
      debugPrint('[CareAssistantService] State load failed: $error');
    }
    return null;
  }

  /// Kullanıcıya ait tamamlanmamış asistan eylemlerini listeler.
  Future<List<AssistantAction>> getAssistantActions(String userId) async {
    try {
      final data = await _api.get('/assistant/actions/$userId');
      if (data is List) {
        return data
            .map((e) =>
                AssistantAction.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList();
      }
    } catch (error) {
      debugPrint('[CareAssistantService] Actions load failed: $error');
    }
    return [];
  }

  /// Kritik durumda verilen kullanıcı yanıtını backend asistanına iletir.
  Future<Map<String, dynamic>?> sendAssistantAck({
    required String userId,
    required String response,
    String? note,
    String? actionId,
  }) async {
    try {
      final body = <String, dynamic>{
        'user_id': userId,
        'response': response,
        if (note != null) 'note': note,
        if (actionId != null) 'action_id': actionId,
      };
      final data = await _api.post('/assistant/ack', body);
      return Map<String, dynamic>.from(data);
    } catch (error) {
      debugPrint('[CareAssistantService] Ack send failed: $error');
    }
    return null;
  }

  /// Gösterge panelinde kullanılacak bakım özetini backend'den getirir.
  Future<Map<String, dynamic>?> getCareSummary(String userId) async {
    try {
      final data = await _api.get('/assistant/care-summary/$userId');
      if (data is Map) {
        return Map<String, dynamic>.from(data);
      }
    } catch (error) {
      debugPrint('[CareAssistantService] Care summary load failed: $error');
    }
    return null;
  }
}
