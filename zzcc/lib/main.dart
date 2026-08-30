import 'package:flutter/material.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/routes/app_router.dart';
import 'package:zzcc/core/theme/theme_manager.dart';
import 'package:zzcc/core/services/logger_service.dart';
import 'package:logging/logging.dart' show Logger, Level;
import 'package:zzcc/core/services/config_service.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/data/repositories/chat_repository.dart';
// Conditional import: no-op on web, FFI cleanup on native.
import 'package:zzcc/core/platform/platform_setup_stub.dart'
    if (dart.library.io) 'package:zzcc/core/platform/platform_setup_io.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/presentation/providers/user_provider.dart';
import 'package:zzcc/presentation/providers/locale_provider.dart';
import 'package:path/path.dart' as path;
import 'package:zzcc/l10n/generated/app_localizations.dart';
import 'package:zzcc/presentation/providers/theme_provider.dart';
import 'package:zzcc/presentation/providers/font_provider.dart';
import 'package:zzcc/presentation/providers/app_loaded_provider.dart';
import 'package:zzcc/presentation/pages/splash/splash_page.dart';

class MyApp extends ConsumerWidget {
  const MyApp({super.key});

  static ThemeData _applyGlobalFont(ThemeData theme, {required String fontFamily}) {
    return theme.copyWith(
      textTheme: theme.textTheme.apply(fontFamily: fontFamily),
      primaryTextTheme: theme.primaryTextTheme.apply(fontFamily: fontFamily),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = ref.watch(themeProvider);
    final localeProvider = ref.watch(appLocaleProvider);
    final fontFamily = ref.watch(fontFamilyProvider) ?? 'NotoSansSC';

    ref.listen<LocaleProvider>(appLocaleProvider, (previous, next) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(appLocaleProvider.notifier).init();
      });
    });

    return MaterialApp.router(
      title: '粽子橙橙',
      theme: _applyGlobalFont(ThemeManager.lightTheme(theme), fontFamily: fontFamily),
      darkTheme: _applyGlobalFont(ThemeManager.darkTheme(theme), fontFamily: fontFamily),
      themeMode: ThemeMode.system,
      routerConfig: appRouter,
      debugShowCheckedModeBanner: false,
      locale: localeProvider.locale,
      supportedLocales: localeProvider.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
    );
  }
}

class SplashController extends ConsumerWidget {
  const SplashController({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ref.watch(appLoadedProvider) ? const MyApp() : const SplashPage();
  }
}

void main() async {
  // Setup platform-specific exit handler (no-op on web)
  setupExitHandler();

  WidgetsFlutterBinding.ensureInitialized();

  await setupServiceLocator();
  debugPrint('TRACE: setupServiceLocator done');

  final logger = getIt<LoggerService>();
  await logger.init();
  debugPrint('TRACE: logger.init done');

  // Bridge dart `logging` package to LoggerService so that ChatRepository /
  // ChatRemoteSource logs are visible in the console and log file.
  Logger.root.level = Level.ALL;
  Logger.root.onRecord.listen((record) {
    final msg = '[${record.loggerName}] ${record.message}';
    switch (record.level) {
      case Level.SEVERE:
        logger.error(msg);
        break;
      case Level.WARNING:
        logger.warning(msg);
        break;
      case Level.INFO:
        logger.info(msg);
        break;
      default:
        logger.debug(msg);
    }
  });

  final configService = getIt<ConfigService>();
  final storageService = getIt<StorageService>();
  final userNotifier = UserNotifier();

  await storageService.init(configService.appDataPath);
  debugPrint('TRACE: storageService.init(2) done, keepLoggedIn=${configService.keepLoggedIn}');

  if (configService.keepLoggedIn) {
    final currentUserId = storageService.getCurrentUser();
    if (currentUserId != null) {
      logger.info('检测到自动登录标识，尝试自动登录: $currentUserId');

      final storedCiphertext = storageService.getUserRegistry(currentUserId);
      if (storedCiphertext != null) {
        try {
          final userInfo = await storageService.getUserInfo(storedCiphertext);
          if (userInfo != null) {
            final userDataPath = path.join(configService.appDataPath, storedCiphertext);
            userNotifier.loginUser(
              name: userInfo['name'] ?? '用户名称',
              uid: currentUserId,
              userDataPath: userDataPath,
            );
            logger.info('自动登录成功');
            // 后台同步离线账号（如果需要）
            final chatRepo = getIt<ChatRepository>();
            final password = userInfo['password'] as String? ?? '';
            logger.info('auto-login: userInfo has password=${password.isNotEmpty ? "YES" : "NO (empty)"}');
            if (password.isNotEmpty) {
              chatRepo.syncOfflineAccountIfNeeded(password: password);
            } else {
              logger.info('auto-login: cannot sync — password not stored. User needs to log in manually once.');
            }
          } else {
            logger.info('用户信息不存在，清除当前用户记录');
            storageService.clearCurrentUser();
          }
        } catch (e) {
          logger.error('自动登录失败: $e');
          storageService.clearCurrentUser();
        }
      } else {
        logger.info('用户密文不存在，清除当前用户记录');
        storageService.clearCurrentUser();
      }
    }
  } else {
    logger.info('未开启自动登录，清除当前用户记录');
    storageService.clearCurrentUser();
  }

  final localeProvider = LocaleProvider();

  debugPrint('TRACE: about to runApp');
  runApp(ProviderScope(
    overrides: [
      userProvider.overrideWith((ref) => userNotifier),
      appLocaleProvider.overrideWith((ref) => localeProvider),
    ],
    child: const SplashController(),
  ));

  WidgetsBinding.instance.addPostFrameCallback((_) async {
    await localeProvider.init();
    logger.info('语言设置初始化完成');
  });
}
