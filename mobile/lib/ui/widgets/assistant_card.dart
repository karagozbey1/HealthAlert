// Asistan modunu ve gerekli kullanıcı eylemlerini kart olarak gösterir.

import 'package:flutter/material.dart';

import '../../core/models/assistant_state.dart';
import '../../core/services/care_assistant_service.dart';
import '../theme/app_theme.dart';

class AssistantCard extends StatelessWidget {
  final AssistantState? state;
  final List<AssistantAction> actions;
  final CareAssistantService service;
  final VoidCallback? onAckSent;

  const AssistantCard({
    super.key,
    required this.state,
    required this.actions,
    required this.service,
    this.onAckSent,
  });

  // Duruma göre kartı gizler ya da uygun içerikle oluşturur.
  @override
  Widget build(BuildContext context) {
    if (state == null) return const SizedBox.shrink();

    final mode = state!.currentMode;

    if (mode == 'normal') return const SizedBox.shrink();

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _bgColor(mode).withOpacity(0.12),
        border: Border.all(color: _bgColor(mode), width: 1.5),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(_modeIcon(mode), color: _bgColor(mode), size: 22),
              const SizedBox(width: 8),
              Text(
                _modeLabel(mode),
                style: TextStyle(
                  color: _bgColor(mode),
                  fontWeight: FontWeight.bold,
                  fontSize: 15,
                ),
              ),
              const Spacer(),
              _MonitoringBadge(intensity: state!.monitoringIntensity),
            ],
          ),
          const SizedBox(height: 10),
          ..._buildMessages(mode),
          if (mode == 'critical' && state!.awaitingUserAck)
            _AreYouOkButtons(
              state: state!,
              actions: actions,
              service: service,
              onAckSent: onAckSent,
            ),
        ],
      ),
    );
  }

  // Mevcut moda uygun kısa bilgi mesajlarını üretir.
  List<Widget> _buildMessages(String mode) {
    if (mode == 'watch') {
      return [
        const Text(
          'Değerlerinde küçük bir değişim algılandı. Seni yakından takip ediyorum.',
          style: TextStyle(fontSize: 13),
        ),
      ];
    }
    if (mode == 'warning') {
      final guidanceActions = actions
          .where((a) => a.actionType == 'show_guidance')
          .toList();
      if (guidanceActions.isEmpty) {
        return [const Text('Değerlerin yükselme eğiliminde. Lütfen dinlen.')];
      }
      final meta = guidanceActions.first.ackOptions;
      final List<dynamic> guidanceList =
          meta?['guidance_list'] as List<dynamic>? ?? [];
      return [
        ...guidanceList.take(3).map(
              (msg) => Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('• ', style: TextStyle(fontSize: 13)),
                    Expanded(
                      child: Text(msg.toString(),
                          style: const TextStyle(fontSize: 13)),
                    ),
                  ],
                ),
              ),
            ),
      ];
    }
    if (mode == 'critical') {
      return [
        const Text(
          'Kritik durum algılandı! Lütfen hareketsiz kal ve derin nefes al.',
          style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
      ];
    }
    return [];
  }

  // Modun görsel vurgu rengini seçer.
  Color _bgColor(String mode) {
    switch (mode) {
      case 'watch':
        return AppTheme.primary;
      case 'warning':
        return AppTheme.warning;
      case 'critical':
        return AppTheme.critical;
      default:
        return AppTheme.success;
    }
  }

  // Modu temsil eden simgeyi seçer.
  IconData _modeIcon(String mode) {
    switch (mode) {
      case 'watch':
        return Icons.visibility;
      case 'warning':
        return Icons.warning_amber_rounded;
      case 'critical':
        return Icons.emergency;
      default:
        return Icons.check_circle_outline;
    }
  }

  // Mod adına karşılık gelen kısa etiketi döndürür.
  String _modeLabel(String mode) {
    switch (mode) {
      case 'watch':
        return 'İzleme Modu';
      case 'warning':
        return 'Uyarı Modu';
      case 'critical':
        return '🚨 KRİTİK';
      default:
        return 'Normal';
    }
  }
}

class _MonitoringBadge extends StatelessWidget {
  final String intensity;
  const _MonitoringBadge({required this.intensity});

  // İzleme yoğunluğunu küçük bir rozet olarak gösterir.
  @override
  Widget build(BuildContext context) {
    if (intensity == 'normal') return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: intensity == 'urgent'
            ? AppTheme.critical.withOpacity(0.18)
            : AppTheme.warning.withOpacity(0.18),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        intensity == 'urgent' ? 'Acil İzleme' : 'Artırılmış İzleme',
        style: TextStyle(
          fontSize: 11,
          color: intensity == 'urgent' ? AppTheme.critical : AppTheme.warning,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _AreYouOkButtons extends StatefulWidget {
  final AssistantState state;
  final List<AssistantAction> actions;
  final CareAssistantService service;
  final VoidCallback? onAckSent;

  const _AreYouOkButtons({
    required this.state,
    required this.actions,
    required this.service,
    this.onAckSent,
  });

  @override
  State<_AreYouOkButtons> createState() => _AreYouOkButtonsState();
}

class _AreYouOkButtonsState extends State<_AreYouOkButtons> {
  bool _sending = false;

  // Seçilen yanıtı gönderip işlem bitince üst bileşene haber verir.
  Future<void> _sendAck(String response) async {
    if (_sending) return;
    setState(() => _sending = true);

    final askAction = widget.actions
        .where((a) => a.actionType == 'ask_are_you_ok')
        .firstOrNull;

    await widget.service.sendAssistantAck(
      userId: widget.state.userId,
      response: response,
      actionId: askAction?.id,
    );

    if (mounted) {
      setState(() => _sending = false);
      widget.onAckSent?.call();
    }
  }

  // Kritik modda gösterilen onay butonlarını ve yükleme durumunu çizer.
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const Text(
          'İyi misiniz?',
          style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        if (_sending)
          const Center(child: CircularProgressIndicator())
        else
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _AckButton(
                label: 'İyiyim',
                icon: Icons.check_circle,
                color: AppTheme.success,
                onTap: () => _sendAck('ok'),
              ),
              _AckButton(
                label: 'Yardım Lazım',
                icon: Icons.sos,
                color: AppTheme.critical,
                onTap: () => _sendAck('not_ok'),
              ),
              _AckButton(
                label: 'Yanlış Alarm',
                icon: Icons.cancel,
                color: AppTheme.primary,
                onTap: () => _sendAck('false_alarm'),
              ),
            ],
          ),
      ],
    );
  }
}

class _AckButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;

  const _AckButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.onTap,
  });

  // Tek bir kullanıcı yanıt düğmesini ikon ve etiketle birlikte oluşturur.
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: color.withOpacity(0.15),
              shape: BoxShape.circle,
              border: Border.all(color: color),
            ),
            child: Icon(icon, color: color, size: 24),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              color: color,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}
