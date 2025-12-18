// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Spanish Castilian (`es`).
class AppLocalizationsEs extends AppLocalizations {
  AppLocalizationsEs([String locale = 'es']) : super(locale);

  @override
  String get homeMenuItem => 'Inicio';

  @override
  String get messagesMenuItem => 'Mensajes';

  @override
  String get workbenchMenuItem => 'Taller';

  @override
  String get sharedMenuItem => 'Compartido';

  @override
  String get squareMenuItem => 'Plaza';

  @override
  String get settingsMenuItem => 'Configuración';

  @override
  String get settingsTitle => 'Configuración';

  @override
  String get languageSetting => 'Idioma';

  @override
  String get english => 'Inglés';

  @override
  String get simplifiedChinese => 'Chino simplificado';

  @override
  String get traditionalChinese => 'Chino tradicional';

  @override
  String get spanish => 'Español';

  @override
  String get fileSaved => 'Archivo guardado';

  @override
  String saveFailed(String error) {
    return 'Error al guardar: \$error';
  }

  @override
  String get userSettings => 'Configuración de usuario';

  @override
  String get autoLogin => 'Inicio de sesión automático';

  @override
  String get themeSettings => 'Configuración de tema';

  @override
  String get appSettings => 'Configuración de la aplicación';

  @override
  String get otherSettings => 'Otras configuraciones';

  @override
  String get shortcutSettings => 'Configuración de atajos';

  @override
  String get fontSetting => 'Configuración de fuente';

  @override
  String get splashAnimationSetting => 'Animación de pantalla de inicio';

  @override
  String get currentDataPathWithHint =>
      'Ruta de almacenamiento de datos actual (migrará después de editar)';

  @override
  String get migrationCancelled => 'Migración cancelada';

  @override
  String get migrationSuccess => 'Datos migrados a: ';

  @override
  String get targetFolderNotEmpty => 'La carpeta de destino no está vacía';

  @override
  String get selectEmptyFolderHint =>
      'Seleccione una carpeta vacía como nueva ruta de almacenamiento';

  @override
  String get confirm => 'Confirmar';

  @override
  String get migrationFailed => 'Error de migración: ';

  @override
  String get migratingData => 'Migrando datos';

  @override
  String get migrationComplete => '¡Migración completada!';

  @override
  String get cancel => 'Cancelar';

  @override
  String get migratingFiles => 'Migrando archivos:';

  @override
  String get presetThemes => 'Temas predefinidos';

  @override
  String get customTheme => 'Tema personalizado';

  @override
  String get primaryColorLabel => 'Color principal';

  @override
  String get leftSidebarColorLabel => 'Color de barra lateral izquierda';

  @override
  String get rightPanelColorLabel => 'Color de panel derecho';

  @override
  String get chooseColor => 'Elegir color';

  @override
  String get apply => 'Aplicar';
}
