import 'package:flutter/material.dart';
import '../../core/models/enums.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';
import '../../ui/widgets/gradient_button.dart';
import '../screens/login_screen.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _ProfileScreenState extends State<ProfileScreen> {
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _phoneController = TextEditingController();
  bool _loaded = false;

  /// Inherited bağımlılıklar değiştiğinde ekran ayarlarını günceller.
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_loaded) return;
    final p = AppScope.of(context).user;
    if (p != null) {
      _nameController.text = p.fullName;
      _emailController.text = p.email;
      _phoneController.text = p.phone;
    }
    _loaded = true;
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final profile = app.user;
    if (profile == null) {
      return const Scaffold(body: Center(child: Text('Aktif oturum yok')));
    }

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        title: const Text("Hesabım"),
        backgroundColor: Colors.transparent,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Center(
              child: Stack(
                alignment: Alignment.bottomRight,
                children: [
                  Container(
                    width: 120,
                    height: 120,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(color: AppTheme.primary, width: 2),
                      color: AppTheme.surface,
                    ),
                    child: Center(
                      child: Text(
                        profile.fullName.isNotEmpty
                            ? profile.fullName[0].toUpperCase()
                            : 'K',
                        style: const TextStyle(
                          color: AppTheme.primary,
                          fontSize: 48,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: const BoxDecoration(
                      color: AppTheme.primary,
                      shape: BoxShape.circle,
                    ),
                    child:
                        const Icon(Icons.edit, color: Colors.black, size: 20),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            Text(
              profile.fullName,
              style: AppTheme.darkTheme.textTheme.displayMedium,
            ),
            Text(
              _roleLabel(profile.role),
              style: AppTheme.darkTheme.textTheme.bodyMedium
                  ?.copyWith(color: AppTheme.textSecondary),
            ),
            const SizedBox(height: 32),
            GlassCard(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  _buildEditableItem(Icons.person, 'Ad Soyad', _nameController),
                  const Divider(color: Colors.white10),
                  _buildEditableItem(Icons.email, 'E-posta', _emailController),
                  const Divider(color: Colors.white10),
                  _buildEditableItem(Icons.phone, 'Telefon', _phoneController),
                  const Divider(color: Colors.white10),
                  _buildProfileItem(Icons.watch, 'Cihaz ID', profile.deviceId),
                ],
              ),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: GradientButton(
                text: 'KAYDET',
                icon: Icons.save,
                onPressed: () async {
                  await app.updateProfile(
                    profile.copyWith(
                      fullName: _nameController.text.trim(),
                      email: _emailController.text.trim(),
                      phone: _phoneController.text.trim(),
                    ),
                  );
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                        content: Text('Profil başarıyla kaydedildi.')),
                  );
                },
              ),
            ),
            const SizedBox(height: 24),
            Text(
              "GÜVENLİK",
              style: AppTheme.darkTheme.textTheme.labelSmall
                  ?.copyWith(letterSpacing: 2),
            ),
            const SizedBox(height: 16),
            GlassCard(
              onTap: () {}, // Mock change password
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text("Şifre Değiştir",
                      style: TextStyle(color: Colors.white, fontSize: 16)),
                  Icon(Icons.arrow_forward_ios, size: 16, color: Colors.grey),
                ],
              ),
            ),
            const SizedBox(height: 32),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: AppTheme.critical),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(30)),
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
                onPressed: () {
                  app.logout();
                  Navigator.of(context).pushAndRemoveUntil(
                    MaterialPageRoute(builder: (_) => const LoginScreen()),
                    (route) => false,
                  );
                },
                child: const Text("ÇIKIŞ YAP",
                    style: TextStyle(
                        color: AppTheme.critical, fontWeight: FontWeight.bold)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildEditableItem(
      IconData icon, String title, TextEditingController controller) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: AppTheme.primary.withOpacity(0.7), size: 20),
          const SizedBox(width: 16),
          Expanded(
            child: TextField(
              controller: controller,
              decoration: InputDecoration(
                labelText: title,
                labelStyle: AppTheme.darkTheme.textTheme.labelSmall,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// Ekranda gösterilecek ilgili arayüz bölümünü oluşturur.
  Widget _buildProfileItem(IconData icon, String title, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Icon(icon, color: AppTheme.primary.withOpacity(0.7), size: 20),
          const SizedBox(width: 16),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: AppTheme.darkTheme.textTheme.labelSmall),
              Text(value, style: AppTheme.darkTheme.textTheme.bodyLarge),
            ],
          ),
        ],
      ),
    );
  }

  /// Ekranda gösterilecek kullanıcı dostu durum etiketini seçer.
  String _roleLabel(UserRole? role) {
    switch (role) {
      case UserRole.doctor:
        return 'Doktor';
      case UserRole.relative:
        return 'Hasta Yakını';
      default:
        return 'Hasta / Kullanıcı';
    }
  }
}
