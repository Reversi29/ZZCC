// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get homeMenuItem => 'Home';

  @override
  String get messagesMenuItem => 'Messages';

  @override
  String get workbenchMenuItem => 'Workbench';

  @override
  String get sharedMenuItem => 'Shared';

  @override
  String get squareMenuItem => 'Square';

  @override
  String get settingsMenuItem => 'Settings';

  @override
  String get settingsTitle => 'Settings';

  @override
  String get languageSetting => 'Language';

  @override
  String get english => 'English';

  @override
  String get simplifiedChinese => 'Simplified Chinese';

  @override
  String get traditionalChinese => 'Traditional Chinese';

  @override
  String get spanish => 'Spanish';

  @override
  String get fileSaved => 'File saved';

  @override
  String saveFailed(String error) {
    return 'Save failed: $error';
  }

  @override
  String get userSettings => 'User Settings';

  @override
  String get autoLogin => 'Auto Login';

  @override
  String get themeSettings => 'Theme Settings';

  @override
  String get appSettings => 'App Settings';

  @override
  String get otherSettings => 'Other Settings';

  @override
  String get shortcutSettings => 'Shortcut Settings';

  @override
  String get fontSetting => 'Font Settings';

  @override
  String get splashAnimationSetting => 'Splash Screen Animation';

  @override
  String get currentDataPathWithHint =>
      'Current APP data storage path (will migrate after edit)';

  @override
  String get migrationCancelled => 'Migration cancelled';

  @override
  String get migrationSuccess => 'Data migrated to: ';

  @override
  String get targetFolderNotEmpty => 'Target folder is not empty';

  @override
  String get selectEmptyFolderHint =>
      'Please select an empty folder as new storage path';

  @override
  String get confirm => 'Confirm';

  @override
  String get migrationFailed => 'Migration failed: ';

  @override
  String get migratingData => 'Migrating data';

  @override
  String get migrationComplete => 'Migration complete!';

  @override
  String get cancel => 'Cancel';

  @override
  String get migratingFiles => 'Migrating files:';

  @override
  String get presetThemes => 'Preset Themes';

  @override
  String get customTheme => 'Custom Theme';

  @override
  String get primaryColorLabel => 'Primary Color';

  @override
  String get leftSidebarColorLabel => 'Left Sidebar Color';

  @override
  String get rightPanelColorLabel => 'Right Panel Color';

  @override
  String get chooseColor => 'Choose Color';

  @override
  String get apply => 'Apply';
}
