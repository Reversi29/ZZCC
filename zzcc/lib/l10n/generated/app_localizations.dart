import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_es.dart';
import 'app_localizations_zh.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'generated/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
      : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations? of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('es'),
    Locale('zh'),
    Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hans'),
    Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')
  ];

  /// Home menu item
  ///
  /// In en, this message translates to:
  /// **'Home'**
  String get homeMenuItem;

  /// Messages menu item
  ///
  /// In en, this message translates to:
  /// **'Messages'**
  String get messagesMenuItem;

  /// Workbench menu item
  ///
  /// In en, this message translates to:
  /// **'Workbench'**
  String get workbenchMenuItem;

  /// Shared menu item
  ///
  /// In en, this message translates to:
  /// **'Shared'**
  String get sharedMenuItem;

  /// Square menu item
  ///
  /// In en, this message translates to:
  /// **'Square'**
  String get squareMenuItem;

  /// Settings menu item
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settingsMenuItem;

  /// Title for settings page
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settingsTitle;

  /// Label for language setting
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get languageSetting;

  /// English language name
  ///
  /// In en, this message translates to:
  /// **'English'**
  String get english;

  /// Simplified Chinese language name
  ///
  /// In en, this message translates to:
  /// **'Simplified Chinese'**
  String get simplifiedChinese;

  /// Traditional Chinese language name
  ///
  /// In en, this message translates to:
  /// **'Traditional Chinese'**
  String get traditionalChinese;

  /// Spanish language name
  ///
  /// In en, this message translates to:
  /// **'Spanish'**
  String get spanish;

  /// Message when file is saved
  ///
  /// In en, this message translates to:
  /// **'File saved'**
  String get fileSaved;

  /// Message when file save fails
  ///
  /// In en, this message translates to:
  /// **'Save failed: {error}'**
  String saveFailed(String error);

  /// No description provided for @userSettings.
  ///
  /// In en, this message translates to:
  /// **'User Settings'**
  String get userSettings;

  /// No description provided for @autoLogin.
  ///
  /// In en, this message translates to:
  /// **'Auto Login'**
  String get autoLogin;

  /// No description provided for @themeSettings.
  ///
  /// In en, this message translates to:
  /// **'Theme Settings'**
  String get themeSettings;

  /// No description provided for @appSettings.
  ///
  /// In en, this message translates to:
  /// **'App Settings'**
  String get appSettings;

  /// No description provided for @otherSettings.
  ///
  /// In en, this message translates to:
  /// **'Other Settings'**
  String get otherSettings;

  /// No description provided for @shortcutSettings.
  ///
  /// In en, this message translates to:
  /// **'Shortcut Settings'**
  String get shortcutSettings;

  /// Label for font setting
  ///
  /// In en, this message translates to:
  /// **'Font Settings'**
  String get fontSetting;

  /// Setting option to enable/disable splash screen animation (switch title)
  ///
  /// In en, this message translates to:
  /// **'Splash Screen Animation'**
  String get splashAnimationSetting;

  /// No description provided for @currentDataPathWithHint.
  ///
  /// In en, this message translates to:
  /// **'Current APP data storage path (will migrate after edit)'**
  String get currentDataPathWithHint;

  /// No description provided for @migrationCancelled.
  ///
  /// In en, this message translates to:
  /// **'Migration cancelled'**
  String get migrationCancelled;

  /// No description provided for @migrationSuccess.
  ///
  /// In en, this message translates to:
  /// **'Data migrated to: '**
  String get migrationSuccess;

  /// No description provided for @targetFolderNotEmpty.
  ///
  /// In en, this message translates to:
  /// **'Target folder is not empty'**
  String get targetFolderNotEmpty;

  /// No description provided for @selectEmptyFolderHint.
  ///
  /// In en, this message translates to:
  /// **'Please select an empty folder as new storage path'**
  String get selectEmptyFolderHint;

  /// No description provided for @confirm.
  ///
  /// In en, this message translates to:
  /// **'Confirm'**
  String get confirm;

  /// No description provided for @migrationFailed.
  ///
  /// In en, this message translates to:
  /// **'Migration failed: '**
  String get migrationFailed;

  /// No description provided for @migratingData.
  ///
  /// In en, this message translates to:
  /// **'Migrating data'**
  String get migratingData;

  /// No description provided for @migrationComplete.
  ///
  /// In en, this message translates to:
  /// **'Migration complete!'**
  String get migrationComplete;

  /// No description provided for @cancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// No description provided for @migratingFiles.
  ///
  /// In en, this message translates to:
  /// **'Migrating files:'**
  String get migratingFiles;

  /// Title for preset themes section
  ///
  /// In en, this message translates to:
  /// **'Preset Themes'**
  String get presetThemes;

  /// Title for custom theme section
  ///
  /// In en, this message translates to:
  /// **'Custom Theme'**
  String get customTheme;

  /// Label for primary color selector
  ///
  /// In en, this message translates to:
  /// **'Primary Color'**
  String get primaryColorLabel;

  /// Label for left sidebar color selector
  ///
  /// In en, this message translates to:
  /// **'Left Sidebar Color'**
  String get leftSidebarColorLabel;

  /// Label for right panel color selector
  ///
  /// In en, this message translates to:
  /// **'Right Panel Color'**
  String get rightPanelColorLabel;

  /// Title for color picker dialog
  ///
  /// In en, this message translates to:
  /// **'Choose Color'**
  String get chooseColor;

  /// Apply button text
  ///
  /// In en, this message translates to:
  /// **'Apply'**
  String get apply;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'es', 'zh'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when language+script codes are specified.
  switch (locale.languageCode) {
    case 'zh':
      {
        switch (locale.scriptCode) {
          case 'Hans':
            return AppLocalizationsZhHans();
          case 'Hant':
            return AppLocalizationsZhHant();
        }
        break;
      }
  }

  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'es':
      return AppLocalizationsEs();
    case 'zh':
      return AppLocalizationsZh();
  }

  throw FlutterError(
      'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
