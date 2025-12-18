import 'package:flutter/material.dart';
import 'package:zzcc/data/models/theme_model.dart';

class ThemeManager {
  static ThemeData lightTheme(CustomTheme customTheme) {
    return ThemeData.light().copyWith(
      primaryColor: customTheme.primaryColor,
      colorScheme: ColorScheme.fromSeed(
        seedColor: customTheme.primaryColor,
        brightness: Brightness.light
      ),
    );
  }

  static ThemeData darkTheme(CustomTheme customTheme) {
    return ThemeData.dark().copyWith(
      primaryColor: customTheme.primaryColor,
      colorScheme: ColorScheme.fromSeed(
        seedColor: customTheme.primaryColor,
        brightness: Brightness.dark
      ),
    );
  }
}