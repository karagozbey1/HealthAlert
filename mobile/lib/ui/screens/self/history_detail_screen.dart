import 'package:flutter/material.dart';
import '../../../core/models/enums.dart';
import '../../../core/models/history_item.dart';
import '../../../core/services/chat_service.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import '../../widgets/severity_badge.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class HistoryDetailScreen extends StatefulWidget {
  const HistoryDetailScreen({super.key, required this.item});

  final HistoryItem item;

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<HistoryDetailScreen> createState() => _HistoryDetailScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _HistoryDetailScreenState extends State<HistoryDetailScreen> {
  String? _recommendation;
  bool _loadingRec = false;

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _fetchRecommendation());
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Future<void> _fetchRecommendation() async {
    final app = AppScope.of(context);
    if (!app.isBackendMode) return;

    setState(() => _loadingRec = true);
    final chatService = ChatService(apiClient: app.apiClient);
    try {
      final resp = await chatService.sendMessage(
        message: 'Bu olayla ilgili kısa öneri ver: '
            '${widget.item.title} — ${widget.item.subtitle.isNotEmpty ? widget.item.subtitle : "Ek detay yok"} '
            '(Şiddet: ${widget.item.severity.name}, Tür: ${widget.item.type.name})',
        screenContext: 'history_detail',
      );
      if (mounted) {
        setState(() {
          _recommendation = resp.message;
          _loadingRec = false;
        });
      }
    } catch (error) {
      debugPrint('[HistoryDetail] Recommendation load failed: $error');
      if (mounted) setState(() => _loadingRec = false);
    }
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text('Olay Detayı',
            style: TextStyle(color: Colors.white, fontSize: 16)),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              GlassCard(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: _severityColor(widget.item.severity)
                                .withOpacity(0.15),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(_typeIcon(widget.item.type),
                              color: _severityColor(widget.item.severity),
                              size: 28),
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(widget.item.title,
                                  style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 18,
                                      fontWeight: FontWeight.bold)),
                              const SizedBox(height: 6),
                              SeverityBadge(severity: widget.item.severity),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              GlassCard(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _buildDetailRow(
                      icon: Icons.category_outlined,
                      label: 'Olay Türü',
                      value: _typeLabel(widget.item.type),
                    ),
                    const Divider(color: Colors.white12, height: 24),
                    _buildDetailRow(
                      icon: Icons.access_time_outlined,
                      label: 'Zaman',
                      value: _formatDateTime(widget.item.timestamp),
                    ),
                    const Divider(color: Colors.white12, height: 24),
                    _buildDetailRow(
                      icon: Icons.info_outline,
                      label: 'Detaylar',
                      value: widget.item.subtitle.isNotEmpty
                          ? widget.item.subtitle
                          : 'Ek detay bulunmuyor.',
                      valueStyle: const TextStyle(
                          color: Colors.white70, fontSize: 13, height: 1.5),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              if (_loadingRec)
                const GlassCard(
                  padding: EdgeInsets.all(16),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: AppTheme.primary),
                      ),
                      SizedBox(width: 12),
                      Text('Öneri yükleniyor...',
                          style:
                              TextStyle(color: Colors.white54, fontSize: 13)),
                    ],
                  ),
                )
              else if (_recommendation != null)
                GlassCard(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(Icons.smart_toy,
                              color: AppTheme.primary, size: 18),
                          const SizedBox(width: 8),
                          const Text(
                            'Asistan Önerisi',
                            style: TextStyle(
                              color: AppTheme.primary,
                              fontWeight: FontWeight.bold,
                              fontSize: 13,
                            ),
                          ),
                        ],
                      ),
                      const Divider(color: Colors.white12, height: 20),
                      Text(
                        _recommendation!,
                        style: const TextStyle(
                            color: Colors.white70, fontSize: 13, height: 1.5),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Bu otomatik bir değerlendirmedir, tıbbi teşhis yerine geçmez.',
                        style: TextStyle(
                            color: Colors.white30,
                            fontSize: 10,
                            fontStyle: FontStyle.italic),
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(Icons.arrow_back),
                  label: const Text('Geçmişe Dön'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.surface,
                    foregroundColor: AppTheme.primary,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildDetailRow({
    required IconData icon,
    required String label,
    required String value,
    TextStyle? valueStyle,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 18, color: AppTheme.primary),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label,
                  style: const TextStyle(
                      color: Colors.white38, fontSize: 11, letterSpacing: 0.5)),
              const SizedBox(height: 4),
              Text(value,
                  style: valueStyle ??
                      const TextStyle(color: Colors.white, fontSize: 14)),
            ],
          ),
        ),
      ],
    );
  }

  /// Duruma göre ekranda kullanılacak rengi belirler.
  Color _severityColor(AlertSeverity s) {
    switch (s) {
      case AlertSeverity.critical:
        return AppTheme.critical;
      case AlertSeverity.warning:
        return AppTheme.warning;
      case AlertSeverity.watch:
        return AppTheme.primary;
      case AlertSeverity.normal:
        return AppTheme.success;
    }
  }

  /// Duruma göre ekranda kullanılacak ikonu belirler.
  IconData _typeIcon(HistoryItemType t) {
    switch (t) {
      case HistoryItemType.alert:
        return Icons.warning_amber_rounded;
      case HistoryItemType.anomaly:
        return Icons.monitor_heart;
      case HistoryItemType.status:
        return Icons.check_circle_outline;
      case HistoryItemType.notification:
        return Icons.notifications_outlined;
    }
  }

  /// Ekranda gösterilecek kullanıcı dostu durum etiketini seçer.
  String _typeLabel(HistoryItemType t) {
    switch (t) {
      case HistoryItemType.alert:
        return 'Alarm Olayı';
      case HistoryItemType.anomaly:
        return 'Anomali Tespit Edildi';
      case HistoryItemType.status:
        return 'Durum Değişikliği';
      case HistoryItemType.notification:
        return 'Bildirim';
    }
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  String _formatDateTime(DateTime dt) {
    final local = dt.toLocal();
    final pad = (int n) => n.toString().padLeft(2, '0');
    return '${local.year}-${pad(local.month)}-${pad(local.day)}  '
        '${pad(local.hour)}:${pad(local.minute)}:${pad(local.second)}';
  }
}
