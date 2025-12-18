class ThemeEntity {
  final bool isDarkMode;
  final String languageCode;

  ThemeEntity({
    required this.isDarkMode,
    required this.languageCode,
  });

  static ThemeEntity defaultTheme() {
    return ThemeEntity(
      isDarkMode: false,
      languageCode: 'en',
    );
  }
}