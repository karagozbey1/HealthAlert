import 'package:flutter/material.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class ContactsScreen extends StatefulWidget {
  const ContactsScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<ContactsScreen> createState() => _ContactsScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _ContactsScreenState extends State<ContactsScreen> {
  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final contacts = app.contacts;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        title: const Text("Yakın Kişiler"),
        backgroundColor: Colors.transparent,
        elevation: 0,
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
                content: Text(
              app.isBackendMode
                  ? 'Kişi ekleme özelliği yakında aktif olacak.'
                  : 'Demo modu: kişi ekleme akışı örnek olarak gösteriliyor.',
            )),
          );
        },
        backgroundColor: AppTheme.primary,
        child: const Icon(Icons.add, color: Colors.black),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: contacts
            .map(
              (c) =>
                  _buildContactCard(c.name, c.relation, c.phone, c.isPrimary),
            )
            .toList(),
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildContactCard(
      String name, String relation, String phone, bool isPrimary) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: GlassCard(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            CircleAvatar(
              backgroundColor: AppTheme.primary.withOpacity(0.2),
              child: Text(
                name.substring(0, 1),
                style: const TextStyle(
                    color: AppTheme.primary, fontWeight: FontWeight.bold),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    style: AppTheme.darkTheme.textTheme.titleMedium,
                  ),
                  Text(
                    relation,
                    style: AppTheme.darkTheme.textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            if (isPrimary)
              Container(
                margin: const EdgeInsets.only(right: 8),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppTheme.primary.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Text(
                  "Öncelikli",
                  style: TextStyle(
                      color: AppTheme.primary,
                      fontSize: 10,
                      fontWeight: FontWeight.bold),
                ),
              ),
            IconButton(
              icon: const Icon(Icons.edit, color: Colors.grey, size: 20),
              onPressed: () {},
            ),
          ],
        ),
      ),
    );
  }
}
