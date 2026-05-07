// Asistan uç noktalarına erişip mobil modelleri dolduran servis katmanıdır.

import '../models/assistant_state.dart';
import 'api_client.dart';

class CareAssistantService {
  final ApiClient _api;

  CareAssistantService(this._api);

  // İlgili kullanıcı için güncel asistan durumunu getirir.
  Future<AssistantState?> getAssistantState(String userId) async {
    try {
      final data = await _api.get('/assistant/state/$userId');
      if (data is Map) {
        return AssistantState.fromJson(Map<String, dynamic>.from(data));
      }
    } catch (_) {}
    return null;
  }

  // Kullanıcıya ait tamamlanmamış asistan eylemlerini listeler.
  Future<List<AssistantAction>> getAssistantActions(String userId) async {
    try {
      final data = await _api.get('/assistant/actions/$userId');
      if (data is List) {
        return (data as List)
            .map((e) =>
                AssistantAction.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList();
      }
    } catch (_) {}
    return [];
  }

  // Kritik durumda verilen kullanıcı yanıtını sunucuya iletir.
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
    } catch (_) {}
    return null;
  }

  // Gösterge paneli için bakım özetini tek çağrıda döndürür.
  Future<Map<String, dynamic>?> getCareSummary(String userId) async {
    try {
      final data = await _api.get('/assistant/care-summary/$userId');
      if (data is Map) {
        return Map<String, dynamic>.from(data);
      }
    } catch (_) {}
    return null;
  }
}
