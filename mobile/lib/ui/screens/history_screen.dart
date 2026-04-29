import 'package:flutter/material.dart';
import '../../core/models/enums.dart';
import '../../core/models/history_item.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';
import '../../ui/widgets/empty_state_widget.dart';
import 'self/history_detail_screen.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  String _filter = 'All';

  bool _matchesFilter(HistoryItemType type) {
    switch (_filter) {
      case 'Alarm':
        return type == HistoryItemType.alert;
      case 'Anomali':
        return type == HistoryItemType.anomaly;
      case 'Durum':
        return type == HistoryItemType.status;
      default:
        return true;
    }
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final items = app.history.where((e) => _matchesFilter(e.type)).toList();

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Column(
          children: [
            const SizedBox(height: 16),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Olay Geçmişi',
                    style: AppTheme.darkTheme.textTheme.displaySmall,
                  ),
                  IconButton(
                    icon: const Icon(Icons.filter_list),
                    onPressed: () {},
                  ),
                ],
              ),
            ),
             const SizedBox(height: 16),
             
             SingleChildScrollView(
               scrollDirection: Axis.horizontal,
               padding: const EdgeInsets.only(left: 16, bottom: 16),
               child: Row(
                 children: [
                   _buildFilterChip('All', 'Tumu'),
                     _buildFilterChip('Alarm', 'Alarm'),
                     _buildFilterChip('Anomali', 'Anomali'),
                     _buildFilterChip('Durum', 'Durum'),
                 ],
               ),
             ),
             
             Expanded(
               child: items.isEmpty
                   ? Center(
                       child: EmptyStateWidget(
                         icon: Icons.history_toggle_off_outlined,
                         title: 'Geçmiş kaydı bulunmuyor',
                         subtitle: app.isBackendMode
                             ? 'Henüz canlı modda kayıtlı bir olay yok. '
                               'Cihaz bağlantısı kurulup veri akışı başladığında '
                               'olaylar burada görünecek.'
                             : 'Demo modda henüz bir olay oluşmadı.',
                       ),
                     )
                   : ListView(
                       padding: const EdgeInsets.all(16),
                       children: items
                           .map((e) => _buildEventItem(context: context, item: e))
                           .toList(),
                     ),
             ),
          ],
        ),
      ),
    );
  }

  Widget _buildFilterChip(String key, String label) {
    final isSelected = _filter == key;
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? AppTheme.primary : AppTheme.surface.withOpacity(0.5),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? AppTheme.primary : Colors.white.withOpacity(0.1),
          ),
        ),
        child: InkWell(
          onTap: () => setState(() => _filter = key),
          borderRadius: BorderRadius.circular(20),
        child: Text(
          label,
          style: AppTheme.darkTheme.textTheme.bodyMedium?.copyWith(
            color: isSelected ? AppTheme.background : Colors.white,
            fontWeight: FontWeight.bold,
          ),
        ),
        ),
      ),
    );
  }

  Widget _buildEventItem({
    required BuildContext context,
    required HistoryItem item,
  }) {
    final severityColor = _severityColor(item.severity);
    final icon = _severityIcon(item.severity);
    final type = item.title;
    final time = item.timestamp.toLocal().toString().substring(0, 16);
    final severity = item.severity.name.toUpperCase();

    return Padding(
       padding: const EdgeInsets.only(bottom: 12),
       child: GlassCard(
         onTap: () => Navigator.push(
           context,
           MaterialPageRoute(builder: (_) => HistoryDetailScreen(item: item)),
         ),
         padding: const EdgeInsets.all(16),
         child: Row(
           children: [
             Container(
               padding: const EdgeInsets.all(12),
               decoration: BoxDecoration(
                 color: severityColor.withOpacity(0.2),
                 shape: BoxShape.circle,
               ),
               child: Icon(icon, color: severityColor, size: 24),
             ),
             const SizedBox(width: 16),
             Expanded(
               child: Column(
                 crossAxisAlignment: CrossAxisAlignment.start,
                 children: [
                   Row(
                     mainAxisAlignment: MainAxisAlignment.spaceBetween,
                     children: [
                       Expanded(
                         child: Text(
                           type,
                           style: AppTheme.darkTheme.textTheme.titleMedium
                               ?.copyWith(fontWeight: FontWeight.bold),
                           overflow: TextOverflow.ellipsis,
                         ),
                       ),
                       const SizedBox(width: 8),
                       Container(
                         padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                         decoration: BoxDecoration(
                           color: severityColor.withOpacity(0.1),
                           borderRadius: BorderRadius.circular(10),
                           border: Border.all(color: severityColor.withOpacity(0.5)),
                         ),
                         child: Text(
                           severity,
                           style: AppTheme.darkTheme.textTheme.labelSmall?.copyWith(
                             color: severityColor,
                             fontWeight: FontWeight.bold,
                             fontSize: 10,
                           ),
                         ),
                       ),
                     ],
                   ),
                   const SizedBox(height: 4),
                   Text(
                     time,
                     style: AppTheme.darkTheme.textTheme.bodyMedium?.copyWith(
                       color: AppTheme.textSecondary,
                     ),
                   ),
                 ],
               ),
             ),
             const SizedBox(width: 8),
             const Icon(Icons.chevron_right, color: Colors.white24, size: 18),
           ],
         ),
       ),
    );
  }

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

  IconData _severityIcon(AlertSeverity s) {
    switch (s) {
      case AlertSeverity.critical:
        return Icons.warning_amber_rounded;
      case AlertSeverity.warning:
        return Icons.monitor_heart;
      case AlertSeverity.watch:
        return Icons.visibility;
      case AlertSeverity.normal:
        return Icons.check_circle;
    }
  }
}
