import 'package:flutter/material.dart';
// import 'package:flutter/services.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/routes/app_router.dart';
import 'package:zzcc/core/theme/theme_manager.dart';
import 'package:zzcc/presentation/providers/theme_provider.dart';
import 'package:zzcc/core/services/logger_service.dart';
import 'package:zzcc/core/services/config_service.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/core/services/torrent_service.dart';
import 'package:zzcc/presentation/providers/user_provider.dart';
import 'package:zzcc/presentation/providers/locale_provider.dart';
import 'dart:ffi';
import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:zzcc/l10n/generated/app_localizations.dart';
import 'package:zzcc/presentation/providers/font_provider.dart';
import 'package:zzcc/presentation/providers/app_loaded_provider.dart';
import 'package:zzcc/presentation/pages/splash/splash_page.dart';
// import 'package:webview_flutter_platform_interface/webview_flutter_platform_interface.dart';
// // 修正导入语句
// import 'package:webview_flutter_android/webview_flutter_android.dart';
// import 'package:webview_flutter_wkwebview/webview_flutter_wkwebview.dart';
// // Windows平台需要特殊处理
// // import 'package:webview_flutter/webview_flutter.dart' as webview;

final _kernel32 = DynamicLibrary.open('kernel32.dll');

final setConsoleCtrlHandler = _kernel32.lookupFunction<
    Int32 Function(Pointer<NativeFunction<Int32 Function(Int32)>>, Int32),
    int Function(Pointer<NativeFunction<Int32 Function(Int32)>>, int)
>('SetConsoleCtrlHandler');

void _cleanup() {
  try {
    final torrentService = getIt<TorrentService>();
    torrentService.dispose();
    getIt<LoggerService>().info('Application resources cleaned up');
  } catch (e) {
    // 忽略错误
  }
}

void _setupExitHandler() {
  final handler = Pointer.fromFunction<Int32 Function(Int32)>(
    _exitHandler,
    0 // 异常返回值
  );
  setConsoleCtrlHandler(handler, 1);
}

int _exitHandler(int ctrlType) {
  _cleanup();
  exit(0);
}

class MyApp extends ConsumerWidget {
  const MyApp({super.key});

  static ThemeData _applyGlobalFont(ThemeData theme, {required String fontFamily}) {
    return theme.copyWith(
      textTheme: theme.textTheme.apply(
        fontFamily: fontFamily,
      ),
      primaryTextTheme: theme.primaryTextTheme.apply(
        fontFamily: fontFamily,
      ),
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
    return ref.watch(appLoadedProvider)
        ? const MyApp()
        : const SplashPage();
  }
}

void main() async {
  if (Platform.isWindows) {
    _setupExitHandler();
  }

  WidgetsFlutterBinding.ensureInitialized();
  
  
  // // 平台特定的WebView初始化（仅支持Android和iOS）
  // if (WebViewPlatform.instance == null) {
  //   if (Platform.isAndroid) {
  //     AndroidWebViewPlatform.registerWith();
  //   } else if (Platform.isIOS) {
  //     WebKitWebViewPlatform.registerWith();
  //   }
  // }
  
  await setupServiceLocator();

  final logger = getIt<LoggerService>();
  await logger.init();
  
  final configService = getIt<ConfigService>();
  final storageService = getIt<StorageService>();
  final userNotifier = UserNotifier();
  
  await storageService.init(configService.appDataPath);

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
          } else {
            logger.info('用户信息不存在，清除当前用户记录');
            storageService.clearCurrentUser();
          }
        } catch (e) {
          logger.error('自动登录失败: ${e.toString()}');
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

  // 创建LocaleProvider实例
  final localeProvider = LocaleProvider();
  
  // 运行应用
  runApp(ProviderScope(
    overrides: [
      userProvider.overrideWith((ref) => userNotifier),
      appLocaleProvider.overrideWith((ref) => localeProvider),
    ],
    child: const SplashController()
  ));
  
  // 在应用启动后初始化LocaleProvider
  WidgetsBinding.instance.addPostFrameCallback((_) async {
    await localeProvider.init();
    logger.info('语言设置初始化完成');
  });
}