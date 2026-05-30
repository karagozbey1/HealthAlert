import 'package:flutter/material.dart';

import '../../../core/state/app_scope.dart';
import '../../../ui/theme/app_theme.dart';
import '../../../ui/widgets/glass_card.dart';
class CloudSyncScreen extends StatelessWidget {
  const CloudSyncScreen({super.key});

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final isConnected = app.isFirestoreSyncAvailable || app.isBackendMode;
    final lastSync = app.firestoreSync?.lastSyncTime;
    final pendingCount = app.firestoreSync?.pendingCount ?? 0;

    final statusLabel = app.isFirestoreSyncAvailable
        ? 'Firebase/Firestore senkronizasyonu aktif'
        : isConnected
            ? 'Bulut bağlantısı hazır'
            : 'Bulut bağlantısı beklemede';
    final statusSub = isConnected
        ? 'Canlı izleme verileri yetkili hesaplarla eşitlenir.'
        : 'Canlı bağlantı açıldığında eşitleme otomatik başlar.';
    final statusColor = isConnected ? AppTheme.success : Colors.white38;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Bulut Senkronizasyonu'),
        leading: const BackButton(),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            GlassCard(
              padding: const EdgeInsets.all(18),
              child: Row(
                children: [
                  Container(
                    width: 46,
                    height: 46,
                    decoration: BoxDecoration(
                      color: statusColor.withOpacity(0.12),
                      borderRadius: BorderRadius.circular(13),
                      border: Border.all(color: statusColor.withOpacity(0.28)),
                    ),
                    child: Icon(
                      isConnected
                          ? Icons.cloud_done_outlined
                          : Icons.cloud_queue_outlined,
                      color: statusColor,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          statusLabel,
                          style: TextStyle(
                            color: statusColor,
                            fontWeight: FontWeight.bold,
                            fontSize: 15,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          statusSub,
                          style: const TextStyle(
                            color: Colors.white54,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            Text(
              'Senkronizasyon durumu'.toUpperCase(),
              style: AppTheme.darkTheme.textTheme.labelSmall,
            ),
            const SizedBox(height: 8),
            GlassCard(
              padding: const EdgeInsets.all(14),
              child: Column(
                children: [
                  _SyncRow(
                    'Durum',
                    isConnected ? 'Aktif' : 'Beklemede',
                    statusColor,
                  ),
                  const Divider(color: Colors.white10, height: 16),
                  _SyncRow(
                    'Son güncelleme',
                    lastSync != null ? _ago(lastSync) : 'Henüz yok',
                    Colors.white70,
                  ),
                  if (pendingCount > 0) ...[
                    const Divider(color: Colors.white10, height: 16),
                    _SyncRow(
                      'Bekleyen kayıt',
                      '$pendingCount',
                      pendingCount > 10 ? Colors.orangeAccent : Colors.white54,
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 16),
            GlassCard(
              padding: const EdgeInsets.all(14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Icon(Icons.info_outline, color: AppTheme.primary, size: 18),
                  SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Veriler otomatik güncellenir. Acil durumda yardım çağrısı doktor ve yakınlara iletilir.',
                      style: TextStyle(color: Colors.white54, fontSize: 12),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
  static String _ago(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inSeconds < 60) return '${diff.inSeconds}s önce';
    if (diff.inMinutes < 60) return '${diff.inMinutes} dk önce';
    if (diff.inHours < 24) return '${diff.inHours} sa önce';
    return '${diff.inDays} gün önce';
  }
}
class _SyncRow extends StatelessWidget {
  const _SyncRow(this.label, this.value, this.color);

  final String label;
  final String value;
  final Color color;

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: const TextStyle(color: Colors.white38, fontSize: 12),
          ),
        ),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 12,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }
}
