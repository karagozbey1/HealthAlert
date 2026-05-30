import 'package:flutter/material.dart';
import '../../core/models/enums.dart';
import '../../core/state/app_scope.dart';
import '../theme/app_theme.dart';
import '../widgets/glass_card.dart';
import '../widgets/gradient_button.dart';
import 'home_container.dart';
import 'register_screen.dart';
import 'relative/relative_home_container.dart';
import 'doctor/doctor_home_container.dart';
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _LoginScreenState extends State<LoginScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnimation;
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _loading = false;
  String? _error;
  bool _checkedSession = false;
  bool _obscurePass = true;

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _fadeAnimation =
        CurvedAnimation(parent: _controller, curve: Curves.easeOut);
    _controller.forward();
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  @override
  void dispose() {
    _controller.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }
  Widget _roleHomeFor(UserRole role) {
    switch (role) {
      case UserRole.relative:
        return const RelativeHomeContainer();
      case UserRole.doctor:
        return const DoctorHomeContainer();
      default:
        return const HomeContainer();
    }
  }
  Future<void> _handleLogin() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    final app = AppScope.of(context);
    final ok =
        await app.login(_emailController.text.trim(), _passwordController.text);
    if (!mounted) return;
    setState(() => _loading = false);

    if (ok) {
      Navigator.of(context).pushReplacement(
        PageRouteBuilder(
          pageBuilder: (_, __, ___) => _roleHomeFor(app.role),
          transitionsBuilder: (_, anim, __, child) =>
              FadeTransition(opacity: anim, child: child),
        ),
      );
      return;
    }

    setState(() => _error = 'E-posta veya şifre hatalı.');
  }

  /// Inherited bağımlılıklar değiştiğinde ekran ayarlarını günceller.
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_checkedSession) return;
    _checkedSession = true;
    final app = AppScope.of(context);
    if (app.authenticated) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => _roleHomeFor(app.role)),
        );
      });
    }
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(color: AppTheme.background),
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: AppTheme.surface.withOpacity(0.5),
                      border:
                          Border.all(color: AppTheme.primary.withOpacity(0.5)),
                      boxShadow: [
                        BoxShadow(
                          color: AppTheme.primary.withOpacity(0.2),
                          blurRadius: 30,
                          spreadRadius: 10,
                        )
                      ],
                    ),
                    child: const Icon(
                      Icons.health_and_safety_outlined,
                      size: 64,
                      color: AppTheme.primary,
                    ),
                  ),
                  const SizedBox(height: 32),
                  Text('HealthAlert',
                      style: AppTheme.darkTheme.textTheme.displayLarge),
                  const SizedBox(height: 8),
                  Text(
                    'Akıllı sağlık izleme sistemi',
                    style: AppTheme.darkTheme.textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 48),
                  GlassCard(
                    padding: const EdgeInsets.all(28),
                    child: Column(
                      children: [
                        TextFormField(
                          controller: _emailController,
                          keyboardType: TextInputType.emailAddress,
                          style: const TextStyle(color: Colors.white),
                          decoration: InputDecoration(
                            labelText: 'E-posta',
                            prefixIcon: const Icon(Icons.email_outlined,
                                color: Colors.white54),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide.none,
                            ),
                            filled: true,
                            fillColor: Colors.white.withOpacity(0.05),
                            labelStyle: const TextStyle(color: Colors.white70),
                          ),
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _passwordController,
                          obscureText: _obscurePass,
                          style: const TextStyle(color: Colors.white),
                          onFieldSubmitted: (_) => _handleLogin(),
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
                        ),
                        const SizedBox(height: 24),
                        SizedBox(
                          width: double.infinity,
                          child: GradientButton(
                            text: _loading ? 'GİRİŞ YAPILIYOR...' : 'GİRİŞ YAP',
                            isLoading: _loading,
                            onPressed: _handleLogin,
                          ),
                        ),
                        if (_error != null) ...[
                          const SizedBox(height: 12),
                          Text(_error!,
                              style: const TextStyle(
                                  color: Colors.redAccent, fontSize: 13)),
                        ],
                        const SizedBox(height: 16),
                        const Divider(color: Colors.white12),
                        const SizedBox(height: 8),
                        SizedBox(
                          width: double.infinity,
                          child: OutlinedButton.icon(
                            icon: const Icon(Icons.person_add_outlined,
                                color: AppTheme.primary),
                            label: const Text(
                              'HESAP OLUŞTUR',
                              style: TextStyle(
                                  color: AppTheme.primary,
                                  fontWeight: FontWeight.bold,
                                  letterSpacing: 1.2),
                            ),
                            style: OutlinedButton.styleFrom(
                              padding: const EdgeInsets.symmetric(vertical: 14),
                              side: BorderSide(
                                  color: AppTheme.primary.withOpacity(0.5)),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(12),
                              ),
                            ),
                            onPressed: () => Navigator.push(
                              context,
                              MaterialPageRoute(
                                  builder: (_) => const RegisterScreen()),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),
                  if (!AppScope.of(context).isBackendMode)
                    GlassCard(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Demo Hesaplar',
                              style: AppTheme.darkTheme.textTheme.labelSmall
                                  ?.copyWith(
                                      color: AppTheme.primary,
                                      letterSpacing: 1)),
                          const SizedBox(height: 8),
                          _demoCredRow(
                              Icons.person, 'self@demo.com', 'Hasta/Kendim'),
                          _demoCredRow(Icons.family_restroom,
                              'relative@demo.com', 'Yakın'),
                          _demoCredRow(Icons.medical_services,
                              'doctor@demo.com', 'Doktor'),
                          const SizedBox(height: 4),
                          Text('Şifre: demo1234',
                              style: TextStyle(
                                  color: Colors.white38, fontSize: 11)),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
  Widget _demoCredRow(IconData icon, String email, String role) {
    return InkWell(
      onTap: () {
        _emailController.text = email;
        _passwordController.text = 'demo1234';
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          children: [
            Icon(icon, size: 14, color: Colors.white38),
            const SizedBox(width: 8),
            Text(email,
                style: const TextStyle(color: Colors.white54, fontSize: 12)),
            const Spacer(),
            Text(role,
                style: const TextStyle(
                    color: Colors.white38,
                    fontSize: 11,
                    fontStyle: FontStyle.italic)),
          ],
        ),
      ),
    );
  }
}
