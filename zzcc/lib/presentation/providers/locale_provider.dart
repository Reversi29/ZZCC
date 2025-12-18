import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/l10n/generated/app_localizations.dart';

final appLocaleProvider = ChangeNotifierProvider<LocaleProvider>((ref) {
  return LocaleProvider();
});

class LocaleProvider extends ChangeNotifier {
  late Locale _locale;
  late List<Locale> _supportedLocales;

  Locale get locale => _locale;
  List<Locale> get supportedLocales => _supportedLocales;
  
  LocaleProvider() {
    _locale = const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hans');
    _supportedLocales = _getFilteredSupportedLocales();
  }
  
  void setLocale(Locale newLocale) {
    _locale = newLocale;
    _saveLocale(newLocale);
    notifyListeners();
  }

  Locale? _findMatchingLocale(Locale locale) {
    for (final supportedLocale in supportedLocales) {
      if (supportedLocale.languageCode == locale.languageCode &&
          supportedLocale.scriptCode == locale.scriptCode) {
        return supportedLocale;
      }
    }
    for (final supportedLocale in supportedLocales) {
      if (supportedLocale.languageCode == locale.languageCode) {
        return supportedLocale;
      }
    }
    return null;
  }
  
  Future<void> init() async {
    final storageService = getIt<StorageService>();
    final savedLocale = await storageService.getSavedLocale();
    if (savedLocale != null) {
      final matchedLocale = _findMatchingLocale(savedLocale);
      if (matchedLocale != null) {
        _locale = matchedLocale;
        notifyListeners(); // 通知UI更新
      }
    }
  }
  
  Future<void> _saveLocale(Locale locale) async {
    final storageService = getIt<StorageService>();
    await storageService.saveLocale(locale);
  }
  
  List<Locale> _getFilteredSupportedLocales() {
    final rawLocales = AppLocalizations.supportedLocales;
    final filteredLocales = <Locale>[];
    final languageCodes = <String, bool>{};

    for (final locale in rawLocales) {
      if (locale.scriptCode != null) {
        languageCodes[locale.languageCode] = true;
      }
    }

    for (final locale in rawLocales) {
      if (locale.scriptCode == null && languageCodes.containsKey(locale.languageCode)) {
        continue;
      }
      filteredLocales.add(locale);
    }
    
    if (!filteredLocales.any((l) => 
        l.languageCode == 'zh' && 
        l.scriptCode == 'Hans')) {
      filteredLocales.add(const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hans'));
    }
    
    return filteredLocales;
  }
}