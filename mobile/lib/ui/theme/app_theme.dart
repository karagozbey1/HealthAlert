import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  static const Color background = Color(0xFF0B1020); // Deep Navy
  static const Color surface = Color(0xFF162036); // Lighter Navy for cards
  static const Color primary = Color(0xFF00E5FF); // Cyan Neon
  static const Color secondary = Color(0xFFFF2E63); // Magenta Neon
  static const Color success = Color(0xFF00FF94); // Neon Green
  static const Color warning = Color(0xFFFFB100); // Amber
  static const Color critical = Color(0xFFFF0044); // Red Alert
  
  static const Color textMain = Colors.white;
  static const Color textSecondary = Color(0xFF8F9BB3);

  static const LinearGradient primaryGradient = LinearGradient(
    colors: [Color(0xFF00E5FF), Color(0xFF00A2E8)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const LinearGradient criticalGradient = LinearGradient(
    colors: [Color(0xFFFF2E63), Color(0xFFB00020)],
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
  );

  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: background,
      primaryColor: primary,
      colorScheme: ColorScheme.dark(
        primary: primary,
        secondary: secondary,
        surface: surface,
        background: background,
        error: critical,
      ),
      textTheme: TextTheme(
        displayLarge: GoogleFonts.outfit(
          color: textMain,
          fontSize: 32,
          fontWeight: FontWeight.bold,
          letterSpacing: -1.0,
        ),
        displayMedium: GoogleFonts.outfit(
          color: textMain,
          fontSize: 24,
          fontWeight: FontWeight.bold,
        ),
        titleLarge: GoogleFonts.outfit(
          color: textMain,
          fontSize: 20,
          fontWeight: FontWeight.w600,
        ),
        bodyLarge: GoogleFonts.inter(
          color: textMain,
          fontSize: 16,
        ),
        bodyMedium: GoogleFonts.inter(
          color: textSecondary,
          fontSize: 14,
        ),
        labelSmall: GoogleFonts.inter(
          color: textSecondary.withOpacity(0.7),
          fontSize: 11,
          letterSpacing: 0.5,
        ),
      ),
      iconTheme: const IconThemeData(
        color: textMain,
        size: 24,
      ),
      bottomNavigationBarTheme: BottomNavigationBarThemeData(
        backgroundColor: surface.withOpacity(0.8),
        selectedItemColor: primary,
        unselectedItemColor: textSecondary,
        type: BottomNavigationBarType.fixed,
        showSelectedLabels: true,
        showUnselectedLabels: true,
      ),
    );
  }
}
