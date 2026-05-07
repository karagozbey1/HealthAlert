import 'api_client.dart';

class ChatMessage {
  final String role;
  final String content;
  final String? tag;
  final String source;
  final List<UIAction> uiActions;
  final DateTime timestamp;

  /// Sohbet mesajini rol, kaynak ve zaman bilgisiyle birlikte olusturur.
  ChatMessage({
    required this.role,
    required this.content,
    this.tag,
    this.source = 'local',
    this.uiActions = const [],
    DateTime? timestamp,
  }) : timestamp = timestamp ?? DateTime.now();

  /// Mesajin asistana ait olup olmadigini bildirir.
  bool get isAssistant => role == 'assistant';

  /// Mesajin kullanicidan gelip gelmedigini bildirir.
  bool get isUser => role == 'user';
}

class UIAction {
  final String label;
  final String route;

  /// Arayuzde acilabilecek hedef ve etiket bilgisini tasir.
  const UIAction({required this.label, required this.route});

  /// Sunucu yanitindan arayuz eylemi nesnesi uretir.
  factory UIAction.fromJson(Map<String, dynamic> json) {
    return UIAction(
      label: json['label'] as String? ?? '',
      route: json['route'] as String? ?? '',
    );
  }
}

class ChatResponse {
  final String sessionId;
  final String message;
  final String source;
  final String disclaimer;
  final List<UIAction> uiActions;
  final String contextSummary;

  /// Sohbet yanitinin istemcide kullanilacak alanlarini bir arada tutar.
  const ChatResponse({
    required this.sessionId,
    required this.message,
    required this.source,
    required this.disclaimer,
    this.uiActions = const [],
    this.contextSummary = '',
  });

  /// API yanitindan sohbet sonucunu ayriştirir.
  factory ChatResponse.fromJson(Map<String, dynamic> json) {
    return ChatResponse(
      sessionId: json['session_id'] as String? ?? '',
      message: json['message'] as String? ?? '',
      source: json['source'] as String? ?? 'unknown',
      disclaimer: json['disclaimer'] as String? ?? '',
      uiActions: (json['ui_actions'] as List<dynamic>?)
              ?.map((e) => UIAction.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      contextSummary: json['context_summary'] as String? ?? '',
    );
  }
}

class ChatStatus {
  final bool llmConfigured;
  final String llmModel;
  final String llmStatus;
  final bool fallbackAvailable;

  /// Asistan servisinin baglanti ve yedekleme durumunu tasir.
  const ChatStatus({
    required this.llmConfigured,
    required this.llmModel,
    required this.llmStatus,
    this.fallbackAvailable = true,
  });

  /// API yanitindan servis durumunu ayriştirir.
  factory ChatStatus.fromJson(Map<String, dynamic> json) {
    return ChatStatus(
      llmConfigured: json['llm_configured'] as bool? ?? false,
      llmModel: json['llm_model'] as String? ?? '',
      llmStatus: json['llm_status'] as String? ?? 'unknown',
      fallbackAvailable: json['fallback_available'] as bool? ?? true,
    );
  }
}

class ChatService {
  /// Sohbet isteklerini API varsa sunucuya, yoksa yerel yedek akişa yonlendirir.
  ChatService({this.apiClient});

  final ApiClient? apiClient;
  String? _sessionId;

  /// Etkin sohbet oturumunun kimligini dondurur.
  String? get sessionId => _sessionId;

  /// Mesaji sunucuya gonderir ve gerekiyorsa yerel yedek yanit uretir.
  Future<ChatResponse> sendMessage({
    required String message,
    String? targetUserId,
    String screenContext = '',
  }) async {
    if (apiClient == null || !apiClient!.hasToken) {
      return _localFallback(message);
    }

    try {
      final body = <String, dynamic>{
        'message': message,
        'screen_context': screenContext,
      };
      if (_sessionId != null) body['session_id'] = _sessionId;
      if (targetUserId != null) body['target_user_id'] = targetUserId;

      final data = await apiClient!.post('/assistant/chat', body);
      final resp = ChatResponse.fromJson(data);
      _sessionId = resp.sessionId;
      return resp;
    } catch (e) {
      return _localFallback(message);
    }
  }

  /// Kullaniciya gosterilecek hazir soru onerilerini getirir.
  Future<List<String>> getSuggestions() async {
    if (apiClient == null || !apiClient!.hasToken) {
      return _defaultSuggestions();
    }
    try {
      final data = await apiClient!.get('/assistant/suggestions');
      final list = (data as Map<String, dynamic>)['suggestions'] as List<dynamic>?;
      return list?.map((e) => e.toString()).toList() ?? _defaultSuggestions();
    } catch (_) {
      return _defaultSuggestions();
    }
  }

  /// Asistan servisinin baglanti durumunu sorgular.
  Future<ChatStatus> getStatus() async {
    if (apiClient == null || !apiClient!.hasToken) {
      return const ChatStatus(
        llmConfigured: false,
        llmModel: '',
        llmStatus: 'not_configured',
      );
    }
    try {
      final data = await apiClient!.get('/assistant/chat-status');
      return ChatStatus.fromJson(data as Map<String, dynamic>);
    } catch (_) {
      return const ChatStatus(
        llmConfigured: false,
        llmModel: '',
        llmStatus: 'error',
      );
    }
  }

  /// Gecerli sohbet oturumunu sifirlar.
  void resetSession() => _sessionId = null;

  /// Sunucuya ulasilamadiginda kullaniciya gosterilecek yerel yaniti uretir.
  ChatResponse _localFallback(String message) {
    return ChatResponse(
      sessionId: _sessionId ?? '',
      message: 'Su an asistan sunucusuna ulasilamiyor. '
        'Lutfen internet baglantinizi kontrol edin veya daha sonra tekrar deneyin.',
      source: 'local_fallback',
      disclaimer:
          'Bu degerlendirme sensor ve sistem verilerine dayali otomatik bir yorumdur. '
          'Tibbi teshis yerine gecmez.',
    );
  }

  /// Sunucuya baglanilamadiginda varsayilan soru onerilerini saglar.
  List<String> _defaultSuggestions() {
    return [
      'Bugunku durumumu ozetle',
      'Neden uyari aldim?',
      'Su an ne yapmaliyim?',
      'Trendleri acikla',
    ];
  }
}
