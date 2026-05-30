import 'package:flutter/material.dart';
import '../../core/services/chat_service.dart';
import '../../core/state/app_scope.dart';
import '../theme/app_theme.dart';
import '../widgets/empty_state_widget.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class HealthAssistantScreen extends StatefulWidget {
  const HealthAssistantScreen({super.key, this.initialQuestion});

  final String? initialQuestion;

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<HealthAssistantScreen> createState() => _HealthAssistantScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _HealthAssistantScreenState extends State<HealthAssistantScreen> {
  late ChatService _chatService;
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _inputFocus = FocusNode();

  final List<ChatMessage> _messages = [];
  List<String> _suggestions = [];
  bool _loading = false;
  bool _initializing = true;

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _initialize());
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  @override
  void dispose() {
    _inputController.dispose();
    _scrollController.dispose();
    _inputFocus.dispose();
    super.dispose();
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Future<void> _initialize() async {
    final app = AppScope.of(context);
    _chatService = ChatService(
      apiClient: app.isBackendMode ? app.apiClient : null,
    );

    _suggestions = await _chatService.getSuggestions();

    _messages.add(ChatMessage(
      role: 'assistant',
      content: 'Merhaba! Ben Saglik Asistanınız. '
          'Size saglik verileriniz hakkinda bilgi verebilir ve onerilerde bulunabilirim.\n\n'
          'Sormak istediginiz bir sey var mi?',
      source: 'system',
    ));
    if (app.latestLiveStatus == null) {
      _messages.add(ChatMessage(
        role: 'assistant',
        content:
            'Henuz yorumlanacak yeterli veri yok. Veri geldikce daha iyi yardimci olacagim.',
        source: 'system',
      ));
    }

    setState(() => _initializing = false);

    if (widget.initialQuestion != null) {
      _sendMessage(widget.initialQuestion!);
    }
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Future<void> _sendMessage(String text) async {
    if (text.trim().isEmpty) return;

    final userMsg = ChatMessage(role: 'user', content: text.trim());
    setState(() {
      _messages.add(userMsg);
      _loading = true;
    });
    _inputController.clear();
    _scrollToBottom();

    final app = AppScope.of(context);
    String? targetUserId;
    if (app.role.name.toUpperCase() != 'SELF' &&
        app.selectedMonitoredUserId != null) {
      targetUserId = app.selectedMonitoredUserId;
    }

    final response = await _chatService.sendMessage(
      message: text.trim(),
      targetUserId: targetUserId,
      screenContext: 'health_assistant',
    );

    final assistantMsg = ChatMessage(
      role: 'assistant',
      content: response.message,
      source: response.source,
      uiActions: response.uiActions,
    );

    setState(() {
      _messages.add(assistantMsg);
      _loading = false;
    });
    _scrollToBottom();
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent + 100,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  void _handleNewChat() {
    _chatService.resetSession();
    setState(() {
      _messages.clear();
      _messages.add(ChatMessage(
        role: 'assistant',
        content: 'Yeni sohbet baslatildi. Size nasil yardimci olabilirim?',
        source: 'system',
      ));
    });
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    if (_initializing) {
      return Scaffold(
        backgroundColor: AppTheme.background,
        appBar: _buildAppBar(),
        body: const LoadingStateWidget(message: 'Asistan hazirlaniyor...'),
      );
    }

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: _buildAppBar(),
      body: Column(
        children: [
          _buildDisclaimerBanner(),
          Expanded(
            child: _messages.isEmpty
                ? const EmptyStateWidget(
                    icon: Icons.chat_bubble_outline,
                    title: 'Henuz mesaj yok',
                    subtitle:
                        'Asistana bir soru sorun veya asagidaki onerilerden birini secin.',
                  )
                : ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.all(16),
                    itemCount: _messages.length + (_loading ? 1 : 0),
                    itemBuilder: (context, index) {
                      if (index == _messages.length && _loading) {
                        return _buildLoadingBubble();
                      }
                      return _buildMessageBubble(_messages[index]);
                    },
                  ),
          ),
          if (_suggestions.isNotEmpty) _buildSuggestionChips(),
          _buildInputArea(),
        ],
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  PreferredSizeWidget _buildAppBar() {
    return AppBar(
      backgroundColor: Colors.transparent,
      elevation: 0,
      title: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: AppTheme.primary.withValues(alpha: 0.15),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.health_and_safety,
                color: AppTheme.primary, size: 18),
          ),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Saglik Asistani', style: TextStyle(fontSize: 16)),
            ],
          ),
        ],
      ),
      actions: [
        IconButton(
          icon: const Icon(Icons.add_comment_outlined, size: 20),
          tooltip: 'Yeni Sohbet',
          onPressed: _handleNewChat,
        ),
      ],
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildDisclaimerBanner() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      color: AppTheme.primary.withValues(alpha: 0.08),
      child: const Row(
        children: [
          Icon(Icons.info_outline, size: 13, color: AppTheme.primary),
          SizedBox(width: 8),
          Expanded(
            child: Text(
              'Bu asistan tibbi teshis koymaz, ilac onermez. '
              'Otomatik degerlendirmedir.',
              style: TextStyle(color: Colors.white38, fontSize: 10),
            ),
          ),
        ],
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildLoadingBubble() {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.6,
        ),
        decoration: BoxDecoration(
          color: AppTheme.surface.withValues(alpha: 0.6),
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(16),
            topRight: Radius.circular(16),
            bottomLeft: Radius.circular(4),
            bottomRight: Radius.circular(16),
          ),
          border: Border.all(color: Colors.white10),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: AppTheme.primary.withValues(alpha: 0.6),
              ),
            ),
            const SizedBox(width: 10),
            const Text(
              'Dusunuyor...',
              style: TextStyle(
                  color: Colors.white38,
                  fontSize: 12,
                  fontStyle: FontStyle.italic),
            ),
          ],
        ),
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildMessageBubble(ChatMessage msg) {
    final isAssistant = msg.isAssistant;
    final isError = msg.source == 'local_fallback';

    return Align(
      alignment: isAssistant ? Alignment.centerLeft : Alignment.centerRight,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.82,
        ),
        decoration: BoxDecoration(
          color: isError
              ? Colors.red.withValues(alpha: 0.1)
              : isAssistant
                  ? AppTheme.surface.withValues(alpha: 0.6)
                  : AppTheme.primary.withValues(alpha: 0.2),
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(isAssistant ? 4 : 16),
            bottomRight: Radius.circular(isAssistant ? 16 : 4),
          ),
          border: Border.all(
            color: isError
                ? Colors.red.withValues(alpha: 0.3)
                : isAssistant
                    ? Colors.white10
                    : AppTheme.primary.withValues(alpha: 0.3),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (isAssistant)
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    margin: const EdgeInsets.only(right: 8, top: 2),
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(
                      color: isError
                          ? Colors.red.withValues(alpha: 0.15)
                          : AppTheme.primary.withValues(alpha: 0.15),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      isError ? Icons.error_outline : Icons.health_and_safety,
                      size: 12,
                      color: isError ? Colors.redAccent : AppTheme.primary,
                    ),
                  ),
                  Expanded(
                    child: Text(
                      msg.content,
                      style: const TextStyle(
                          color: Colors.white70, fontSize: 13, height: 1.5),
                    ),
                  ),
                ],
              )
            else
              Text(
                msg.content,
                style: const TextStyle(
                    color: Colors.white, fontSize: 13, height: 1.5),
              ),
            if (msg.uiActions.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  children:
                      msg.uiActions.map((a) => _buildActionChip(a)).toList(),
                ),
              ),
          ],
        ),
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildActionChip(UIAction action) {
    return GestureDetector(
      onTap: () {
        final route = action.route;
        if (route.isNotEmpty) {
          Navigator.of(context).pushNamed(route);
        }
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: AppTheme.primary.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppTheme.primary.withValues(alpha: 0.25)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.open_in_new, size: 11, color: AppTheme.primary),
            const SizedBox(width: 4),
            Text(
              action.label,
              style: const TextStyle(color: AppTheme.primary, fontSize: 11),
            ),
          ],
        ),
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildSuggestionChips() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.surface.withValues(alpha: 0.3),
        border: const Border(top: BorderSide(color: Colors.white12)),
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: _suggestions
              .map((s) => Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: GestureDetector(
                      onTap: () => _sendMessage(s),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 8),
                        decoration: BoxDecoration(
                          color: AppTheme.primary.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(
                              color: AppTheme.primary.withValues(alpha: 0.3)),
                        ),
                        child: Text(
                          s,
                          style: const TextStyle(
                            color: AppTheme.primary,
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                    ),
                  ))
              .toList(),
        ),
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildInputArea() {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 8, 12),
      decoration: BoxDecoration(
        color: AppTheme.surface.withValues(alpha: 0.5),
        border: const Border(top: BorderSide(color: Colors.white12)),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _inputController,
                focusNode: _inputFocus,
                style: const TextStyle(color: Colors.white, fontSize: 14),
                maxLines: 3,
                minLines: 1,
                textInputAction: TextInputAction.send,
                onSubmitted: (v) => _sendMessage(v),
                decoration: InputDecoration(
                  hintText: 'Mesajinizi yazin...',
                  hintStyle:
                      TextStyle(color: Colors.white.withValues(alpha: 0.3)),
                  filled: true,
                  fillColor: AppTheme.background.withValues(alpha: 0.5),
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),
            GestureDetector(
              onTap:
                  _loading ? null : () => _sendMessage(_inputController.text),
              child: Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: _loading
                      ? Colors.grey.withValues(alpha: 0.3)
                      : AppTheme.primary,
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  _loading ? Icons.hourglass_empty : Icons.send,
                  color: Colors.white,
                  size: 20,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
