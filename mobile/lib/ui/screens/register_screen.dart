import 'package:flutter/material.dart';
import '../../core/models/enums.dart';
import '../../core/state/app_scope.dart';
import '../theme/app_theme.dart';
import '../widgets/glass_card.dart';
import '../widgets/gradient_button.dart';
import 'home_container.dart';
import 'relative/relative_home_container.dart';
import 'doctor/doctor_home_container.dart';

/// HealthAlert ekranının kullanıcı arayüzünü ve etkileşimlerini oluşturur.
class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _RegisterScreenState extends State<RegisterScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _fadeAnim;

  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _nameCtrl = TextEditingController();
  final _phoneCtrl = TextEditingController();

  UserRole _selectedRole = UserRole.self;
  bool _loading = false;
  String? _error;
  bool _obscurePass = true;

  static const _roleInfo = {
    UserRole.self: (
      label: 'Hasta / Kendim',
      desc: 'Kendi sağlık metriklerini takip et',
      icon: Icons.person,
      color: AppTheme.primary,
    ),
    UserRole.relative: (
      label: 'Yakın / Bakım Veren',
      desc: 'Bağlı aile bireylerini takip et',
      icon: Icons.family_restroom,
      color: AppTheme.success,
    ),
    UserRole.doctor: (
      label: 'Doktor',
      desc: 'Hastalarını klinik olarak takip et',
      icon: Icons.medical_services,
      color: AppTheme.warning,
    ),
  };

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 800));
    _fadeAnim = CurvedAnimation(parent: _ctrl, curve: Curves.easeOut);
    _ctrl.forward();
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  @override
  void dispose() {
    _ctrl.dispose();
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    _nameCtrl.dispose();
    _phoneCtrl.dispose();
    super.dispose();
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Future<void> _handleRegister() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
    });

    final app = AppScope.of(context);
    final ok = await app.register(
      email: _emailCtrl.text.trim(),
      password: _passwordCtrl.text,
      fullName: _nameCtrl.text.trim(),
      role: _selectedRole,
      phone: _phoneCtrl.text.trim().isEmpty ? null : _phoneCtrl.text.trim(),
    );

    if (!mounted) return;
    setState(() => _loading = false);

    if (ok) {
      Widget destination;
      switch (_selectedRole) {
        case UserRole.relative:
          destination = const RelativeHomeContainer();
          break;
        case UserRole.doctor:
          destination = const DoctorHomeContainer();
          break;
        default:
          destination = const HomeContainer();
      }
      Navigator.of(context).pushReplacement(
        PageRouteBuilder(
          pageBuilder: (_, __, ___) => destination,
          transitionsBuilder: (_, anim, __, child) =>
              FadeTransition(opacity: anim, child: child),
        ),
      );
    } else {
      setState(
          () => _error = 'Kayıt başarısız oldu. Farklı bir e-posta deneyin.');
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
          icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white70),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text('Hesap Oluştur',
            style: TextStyle(color: Colors.white70)),
      ),
      body: FadeTransition(
        opacity: _fadeAnim,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Rolünüz',
                    style: AppTheme.darkTheme.textTheme.labelSmall
                        ?.copyWith(letterSpacing: 1.5)),
                const SizedBox(height: 12),
                Row(
                  children: UserRole.values.map((role) {
                    final info = _roleInfo[role]!;
                    final selected = _selectedRole == role;
                    return Expanded(
                      child: GestureDetector(
                        onTap: () => setState(() => _selectedRole = role),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 200),
                          margin: const EdgeInsets.symmetric(horizontal: 4),
                          padding: const EdgeInsets.symmetric(
                              vertical: 16, horizontal: 8),
                          decoration: BoxDecoration(
                            color: selected
                                ? info.color.withOpacity(0.2)
                                : AppTheme.surface,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: selected ? info.color : Colors.white12,
                              width: selected ? 2 : 1,
                            ),
                          ),
                          child: Column(
                            children: [
                              Icon(info.icon,
                                  color: selected ? info.color : Colors.white54,
                                  size: 28),
                              const SizedBox(height: 8),
                              Text(
                                info.label,
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  color: selected ? info.color : Colors.white70,
                                  fontSize: 11,
                                  fontWeight: selected
                                      ? FontWeight.bold
                                      : FontWeight.normal,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 8),
                Text(
                  _roleInfo[_selectedRole]!.desc,
                  style: TextStyle(
                      color: _roleInfo[_selectedRole]!.color, fontSize: 12),
                ),
                const SizedBox(height: 24),
                GlassCard(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    children: [
                      _field(
                        controller: _nameCtrl,
                        label: 'Ad Soyad',
                        icon: Icons.person_outline,
                        validator: (v) => v == null || v.trim().isEmpty
                            ? 'Zorunlu alan'
                            : null,
                      ),
                      const SizedBox(height: 16),
                      _field(
                        controller: _emailCtrl,
                        label: 'E-posta',
                        icon: Icons.email_outlined,
                        keyboard: TextInputType.emailAddress,
                        validator: (v) {
                          if (v == null || v.trim().isEmpty)
                            return 'Zorunlu alan';
                          if (!v.contains('@'))
                            return 'Geçerli bir e-posta girin';
                          return null;
                        },
                      ),
                      const SizedBox(height: 16),
                      _field(
                        controller: _phoneCtrl,
                        label: 'Telefon (opsiyonel)',
                        icon: Icons.phone_outlined,
                        keyboard: TextInputType.phone,
                      ),
                      const SizedBox(height: 16),
                      TextFormField(
                        controller: _passwordCtrl,
                        obscureText: _obscurePass,
                        style: const TextStyle(color: Colors.white),
                        decoration: InputDecoration(
                          labelText: 'Şifre',
                          prefixIcon: const Icon(Icons.lock_outline,
                              color: Colors.white54),
                          suffixIcon: IconButton(
                            icon: Icon(
                              _obscurePass
                                  ? Icons.visibility_off
                                  : Icons.visibility,
                              color: Colors.white54,
                            ),
                            onPressed: () =>
                                setState(() => _obscurePass = !_obscurePass),
                          ),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide.none,
                          ),
                          filled: true,
                          fillColor: Colors.white.withOpacity(0.05),
                          labelStyle: const TextStyle(color: Colors.white70),
                        ),
                        validator: (v) => v == null || v.length < 6
                            ? 'En az 6 karakter'
                            : null,
                      ),
                    ],
                  ),
                ),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(_error!,
                        style: const TextStyle(color: Colors.redAccent)),
                  ),
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  child: GradientButton(
                    text: _loading ? 'HESAP OLUŞTURULUYOR...' : 'HESAP OLUŞTUR',
                    isLoading: _loading,
                    onPressed: _loading ? () {} : _handleRegister,
                    gradient: LinearGradient(
                      colors: [
                        _roleInfo[_selectedRole]!.color,
                        _roleInfo[_selectedRole]!.color.withOpacity(0.7),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 40),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// Ekranın ilgili kullanıcı etkileşimini veya arayüz parçasını hazırlar.
  Widget _field({
    required TextEditingController controller,
    required String label,
    required IconData icon,
    TextInputType keyboard = TextInputType.text,
    String? Function(String?)? validator,
  }) {
    return TextFormField(
      controller: controller,
      keyboardType: keyboard,
      style: const TextStyle(color: Colors.white),
      decoration: InputDecoration(
        labelText: label,
        prefixIcon: Icon(icon, color: Colors.white54),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
        filled: true,
        fillColor: Colors.white.withOpacity(0.05),
        labelStyle: const TextStyle(color: Colors.white70),
      ),
      validator: validator,
    );
  }
}
