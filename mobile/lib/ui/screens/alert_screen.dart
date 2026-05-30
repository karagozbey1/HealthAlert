import 'package:flutter/material.dart';
import '../../core/models/enums.dart';
import '../../core/state/app_scope.dart';
import '../../ui/theme/app_theme.dart';
import '../../ui/widgets/glass_card.dart';
import '../../ui/widgets/gradient_button.dart';
import 'post_event_monitor_screen.dart';
enum AlertType { fall, hrHigh, hrLow, spo2Low, anomaly }
class AlertScreen extends StatefulWidget {
  final AlertType type;

  const AlertScreen({super.key, required this.type});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<AlertScreen> createState() => _AlertScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _AlertScreenState extends State<AlertScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 1),
    )..repeat(reverse: true);
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final active = app.activeAlert;

    if (active == null ||
        active.status == AlertLifecycleStatus.postEventMonitoring) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const PostEventMonitorScreen()),
        );
      });
    }

    Gradient gradient;
    IconData icon;
    String title;

    switch (widget.type) {
      case AlertType.fall:
        gradient = AppTheme.criticalGradient;
        icon = Icons.personal_injury;
        title = "DÜŞME TESPİT EDİLDİ";
        break;
      case AlertType.hrHigh:
        gradient = const LinearGradient(
            colors: [Color(0xFFFF512F), Color(0xFFDD2476)]);
        icon = Icons.favorite;
        title = "YÜKSEK NABIZ";
        break;
      case AlertType.hrLow:
        gradient = const LinearGradient(colors: [
          Color(0xFF3A1C71),
          Color(0xFFD76D77),
          Color(0xFFFFAF7B)
        ]); // Purple-Orange
        icon = Icons.favorite_border;
        title = "DÜŞÜK NABIZ";
        break;
      case AlertType.spo2Low:
        gradient = const LinearGradient(
            colors: [Color(0xFF2193b0), Color(0xFF6dd5ed)]); // Blue
        icon = Icons.air;
        title = "DÜŞÜK OKSİJEN";
        break;
      case AlertType.anomaly:
        gradient =
            const LinearGradient(colors: [AppTheme.warning, Color(0xFFE65100)]);
        icon = Icons.monitor_heart;
        title = "NABIZ ANOMALİSİ";
        break;
    }

    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: gradient,
        ),
        child: SafeArea(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Spacer(),
              ScaleTransition(
                scale: Tween(begin: 1.0, end: 1.2).animate(CurvedAnimation(
                    parent: _controller, curve: Curves.easeInOut)),
                child: Container(
                  padding: const EdgeInsets.all(30),
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.white.withOpacity(0.2),
                    border: Border.all(color: Colors.white, width: 4),
                  ),
                  child: Icon(icon, size: 60, color: Colors.white),
                ),
              ),
              const SizedBox(height: 32),
              Text(
                title,
                textAlign: TextAlign.center,
                style: AppTheme.darkTheme.textTheme.displayMedium?.copyWith(
                  fontWeight: FontWeight.w900,
                  shadows: [
                    const Shadow(
                        color: Colors.black26,
                        blurRadius: 10,
                        offset: Offset(0, 4)),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              GlassCard(
                margin: const EdgeInsets.symmetric(horizontal: 40),
                padding: const EdgeInsets.all(16),
                color: Colors.black.withOpacity(0.3),
                child: Column(
                  children: [
                    Text(
                      "Yardım bildirimi gönderiliyor:",
                      style: AppTheme.darkTheme.textTheme.bodyMedium,
                    ),
                    Text(
                      "${active?.countdownRemainingSec ?? 0} sn",
                      style: AppTheme.darkTheme.textTheme.displayLarge
                          ?.copyWith(fontSize: 48),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              GlassCard(
                margin: const EdgeInsets.symmetric(horizontal: 24),
                padding: const EdgeInsets.all(16),
                color: Colors.black.withOpacity(0.2),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.info_outline,
                            color: Colors.white70, size: 16),
                        const SizedBox(width: 8),
                        Text(
                          'Neden bu uyarı?',
                          style:
                              AppTheme.darkTheme.textTheme.titleSmall?.copyWith(
                            color: Colors.white70,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      _explanationForType(widget.type),
                      style: const TextStyle(
                          color: Colors.white60, fontSize: 13, height: 1.5),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        const Icon(Icons.health_and_safety_outlined,
                            color: Colors.white70, size: 16),
                        const SizedBox(width: 8),
                        Text(
                          'Ne yapmalısınız?',
                          style:
                              AppTheme.darkTheme.textTheme.titleSmall?.copyWith(
                            color: Colors.white70,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      _recommendationForType(widget.type),
                      style: const TextStyle(
                          color: Colors.white60, fontSize: 13, height: 1.5),
                    ),
                  ],
                ),
              ),
              const Spacer(),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  children: [
                    SizedBox(
                      width: double.infinity,
                      child: GradientButton(
                        text: "İYİYİM, İPTAL ET",
                        icon: Icons.check,
                        gradient: const LinearGradient(
                            colors: [AppTheme.success, Color(0xFF00B368)]),
                        onPressed: () async {
                          await app.confirmImOkay();
                          if (!context.mounted) return;
                          Navigator.pushReplacement(
                            context,
                            MaterialPageRoute(
                                builder: (_) => const PostEventMonitorScreen()),
                          );
                        },
                      ),
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.emergency, color: Colors.white),
                        label: const Text("ACİL YARDIM ÇAĞIR",
                            style: TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.bold)),
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(color: Colors.white, width: 2),
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(30)),
                        ),
                        onPressed: () async {
                          await app.requestEmergency();
                          if (!context.mounted) return;
                          Navigator.pushReplacement(
                              context,
                              MaterialPageRoute(
                                  builder: (_) =>
                                      const PostEventMonitorScreen()));
                        },
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 40),
            ],
          ),
        ),
      ),
    );
  }
  String _explanationForType(AlertType type) {
    switch (type) {
      case AlertType.fall:
        return 'Sensör verilerine göre ani bir ivme değişimi ve ardından hareketsizlik tespit edildi. '
            'Bu durum olası bir düşme olarak değerlendirilmektedir.';
      case AlertType.hrHigh:
        return 'Nabız değeriniz belirlenen üst eşiği aştı. '
            'Hareket halinde değilseniz bu durum dikkat gerektirebilir.';
      case AlertType.hrLow:
        return 'Nabız değeriniz belirlenen alt eşiğin altına düştü. '
            'Bradikardi belirtisi olabilir.';
      case AlertType.spo2Low:
        return 'Kan oksijen doygunluğunuz güvenli aralığın altına indi. '
            'Bu durum solunum fonksiyonlarıyla ilgili olabilir.';
      case AlertType.anomaly:
        return 'Nabız ritminizde olağan dışı bir değişiklik tespit edildi. '
            'AI analizi bu durumu anomali olarak işaretledi.';
    }
  }
  String _recommendationForType(AlertType type) {
    switch (type) {
      case AlertType.fall:
        return 'Düşmediyseniz "İyiyim" butonuna basın. '
            'Düştüyseniz ve yardıma ihtiyacınız varsa "Acil Yardım" butonuna basın.';
      case AlertType.hrHigh:
        return 'Oturun ve derin nefes alın. Su için. '
            'Nabzınız düşmezse doktorunuza danışın.';
      case AlertType.hrLow:
        return 'Baş dönmesi veya halsizlik hissediyorsanız yere uzanın. '
            'Belinizi destekli bir pozisyonda kalın.';
      case AlertType.spo2Low:
        return 'Derin ve yavaş nefes alıp verin. '
            'Pencereyi açın veya açık havaya çıkın. Değer düzelmezse acil yardım isteyin.';
      case AlertType.anomaly:
        return 'Sakin kalın ve hareket etmeyin. '
            'Birkaç dakika bekleyin; değerler normale dönerse endişelenmenize gerek yok.';
    }
  }
}
