import 'package:flutter/material.dart';
import 'dart:math';

class AnimatedChartPlaceholder extends StatefulWidget {
  final Color color;
  const AnimatedChartPlaceholder({super.key, required this.color});

  @override
  State<AnimatedChartPlaceholder> createState() => _AnimatedChartPlaceholderState();
}

class _AnimatedChartPlaceholderState extends State<AnimatedChartPlaceholder>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  /// Widget durumunu başlatır.
  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();
  }

  /// Kaynakları serbest bırakır.
  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  /// Widget ağacını oluşturur.
  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return CustomPaint(
          size: Size.infinite,
          painter: ChartPainter(
            animationValue: _controller.value,
            color: widget.color,
          ),
        );
      },
    );
  }
}

class ChartPainter extends CustomPainter {
  final double animationValue;
  final Color color;

  ChartPainter({required this.animationValue, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke;

    final path = Path();
    path.moveTo(0, size.height / 2);

    for (double x = 0; x <= size.width; x++) {
      final y = size.height / 2 +
          sin((x / 50 + animationValue * 2 * pi)) * 30 +
          sin((x / 20 + animationValue * pi)) * 10;
      path.lineTo(x, y);
    }

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant ChartPainter oldDelegate) => true;
}
