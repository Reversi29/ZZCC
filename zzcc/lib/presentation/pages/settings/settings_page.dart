import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:zzcc/data/models/theme_model.dart';
import 'package:zzcc/presentation/widgets/theme_selector.dart';
import 'package:zzcc/presentation/pages/settings/shortcut_settings.dart';
import 'dart:async';
import 'package:zzcc/data/models/app_settings_model.dart';
import 'package:zzcc/core/utils/app_format.dart';
import 'package:zzcc/core/utils/network_time.dart';
import 'package:zzcc/presentation/providers/app_settings_provider.dart';
import 'package:zzcc/core/services/config_service.dart';
import 'package:file_picker/file_picker.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/l10n/generated/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/presentation/providers/locale_provider.dart';
import 'package:zzcc/presentation/providers/user_provider.dart';
import 'package:svg_flag/svg_flag.dart';
import 'package:zzcc/presentation/providers/font_provider.dart';
import 'package:zzcc/presentation/providers/splash_provider.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/core/routes/route_names.dart';
import 'package:go_router/go_router.dart';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
// import 'package:flag/flag.dart';

class SettingsPage extends ConsumerStatefulWidget {
  final List<CustomTheme> presetThemes;

  const SettingsPage({super.key, required this.presetThemes});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  late ConfigService _configService;
  bool _isMigrating = false;
  final List<bool> _isExpanded = [true, true, true, true];
  String? _cacheSize;
  bool _isClearingCache = false;
  bool _isClearingData = false;

  static const List<String> availableFonts = [
    'NotoSansSC',
    'MSYH',
    'Simsun',
    'YFJLXS',
    'SJPM',
    'SJXK',
    'XKNLT',
  ];

  @override
  void initState() {
    super.initState();
    _configService = getIt<ConfigService>();
    _loadCacheSize();
  }

  Future<void> _loadCacheSize() async {
    try {
      final tmpDir = await getTemporaryDirectory();
      final size = await _dirSize(tmpDir);
      if (mounted) {
        setState(() => _cacheSize = _formatBytes(size));
      }
    } catch (_) {
      if (mounted) setState(() => _cacheSize = '--');
    }
  }

  Future<int> _dirSize(Directory dir) async {
    int total = 0;
    try {
      await for (final entity in dir.list(recursive: true, followLinks: false)) {
        if (entity is File) total += await entity.length();
      }
    } catch (_) {}
    return total;
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  Future<void> _clearCache() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('清除缓存'),
        content: const Text('确定要清除所有缓存数据吗？此操作不会影响您的账号和设置。'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          TextButton(
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('清除'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() => _isClearingCache = true);
    try {
      // 清除图片缓存
      PaintingBinding.instance.imageCache.clear();
      PaintingBinding.instance.imageCache.clearLiveImages();

      // 清除临时目录
      final tmpDir = await getTemporaryDirectory();
      if (tmpDir.existsSync()) {
        await for (final entity in tmpDir.list()) {
          try {
            if (entity is File) await entity.delete();
            if (entity is Directory) await entity.delete(recursive: true);
          } catch (_) {}
        }
      }

      await _loadCacheSize();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('缓存已清除'), duration: Duration(seconds: 2)),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('清除失败: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _isClearingCache = false);
    }
  }

  Future<void> _clearData() async {
    // 二次确认：需输入"确认"才能执行
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) {
        final controller = TextEditingController();
        return AlertDialog(
          title: const Text('清除所有数据'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '此操作将删除所有本地数据，包括：',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text('• 所有账号信息\n• 聊天记录与认证\n• 个人设置与偏好\n• 下载的文件'),
              const SizedBox(height: 12),
              const Text('此操作不可撤销。'),
              const SizedBox(height: 12),
              TextField(
                controller: controller,
                decoration: const InputDecoration(
                  labelText: '输入"确认"以继续',
                  isDense: true,
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
            TextButton(
              style: TextButton.styleFrom(foregroundColor: Colors.red),
              onPressed: () {
                if (controller.text == '确认') {
                  Navigator.pop(ctx, true);
                }
              },
              child: const Text('清除数据'),
            ),
          ],
        );
      },
    );
    if (confirmed != true) return;

    setState(() => _isClearingData = true);
    try {
      final storageService = getIt<StorageService>();

      // 1. 清除聊天认证
      await _configService.clearChatAuth();

      // 2. 退出登录（清空并关闭 Hive boxes）
      ref.read(userProvider.notifier).logoutUser(); // 重置内存状态
      storageService.clearCurrentUser();
      await storageService.clearAndClose();

      // 3. 删除用户数据目录（除 Hive 自身文件外）
      final dataDir = Directory(_configService.appDataPath);
      if (dataDir.existsSync()) {
        await for (final entity in dataDir.list()) {
          try {
            final path = entity.path;
            if (path.endsWith('.hive') || path.endsWith('.lock')) continue;
            if (entity is File) await entity.delete();
            if (entity is Directory) await entity.delete(recursive: true);
          } catch (_) {}
        }
      }

      // 4. 清除图片缓存
      PaintingBinding.instance.imageCache.clear();
      PaintingBinding.instance.imageCache.clearLiveImages();

      // 5. 重新打开 StorageService（保留 Hive 文件）
      await storageService.reopen();

      // 6. 跳转到登录页
      if (mounted) {
        GoRouter.of(context).go('${RouteNames.root}${RouteNames.login}');
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('数据已清除'), duration: Duration(seconds: 2)),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('清除数据失败: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _isClearingData = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final localeProvider = ref.watch(appLocaleProvider);
    final appSettings = ref.watch(appSettingsProvider);
    final appLocalizations = AppLocalizations.of(context)!;
    final supportedLocales = localeProvider.supportedLocales;
    final allLanguagesText = 'Language · Idioma · 语言 · 語言';

    return Container(
      color: Theme.of(context).colorScheme.surface,
      padding: const EdgeInsets.all(20),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              appLocalizations.settingsTitle,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 20),
            
            // 用户设置分组
            ExpansionTile(
              title: Text(
                appLocalizations.userSettings,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
              ),
              initiallyExpanded: _isExpanded[0],
              onExpansionChanged: (expanded) => setState(() => _isExpanded[0] = expanded),
              children: [
                const SizedBox(height: 10),
                ListTile(
                  title: Text(appLocalizations.autoLogin),
                  trailing: Switch(
                    value: _configService.keepLoggedIn,
                    onChanged: (value) async {
                      await _configService.updateKeepLoggedIn(value);
                      if (mounted) setState(() {});
                    },
                  ),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16),
                  tileColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                ),
                const SizedBox(height: 20),
              ],
            ),
            
            // 主题设置分组
            ExpansionTile(
              title: Text(
                appLocalizations.themeSettings,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
              ),
              initiallyExpanded: _isExpanded[1],
              onExpansionChanged: (expanded) => setState(() => _isExpanded[1] = expanded),
              children: [
                const SizedBox(height: 10),
                ThemeSelector(presetThemes: widget.presetThemes),
                const SizedBox(height: 20),
              ],
            ),
            
            // 应用设置分组
            ExpansionTile(
              title: Text(
                appLocalizations.appSettings,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
              ),
              initiallyExpanded: _isExpanded[2],
              onExpansionChanged: (expanded) => setState(() => _isExpanded[2] = expanded),
              children: [
                const SizedBox(height: 10),

                // ===== 时间与地区设置（位于「语言」之上）=====
                _buildTimeRegionSection(context, appSettings, ref),
                const SizedBox(height: 20),

                // 语言设置行
                Row(
                  children: [
                    Expanded(
                      flex: 2,
                      child: Text(
                        '${appLocalizations.languageSetting} ( $allLanguagesText )',
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      flex: 3,
                      child: DropdownButton<Locale>(
                        isExpanded: true,
                        value: localeProvider.locale,
                        onChanged: (Locale? newValue) {
                          if (newValue != null) localeProvider.setLocale(newValue);
                        },
                        items: supportedLocales.map((Locale locale) {
                          final displayName = _getLanguageName(locale, context);
                          return DropdownMenuItem<Locale>(
                            value: locale,
                            child: Row(
                              children: [
                                _getFlagWidget(locale),
                                const SizedBox(width: 10),
                                Expanded(child: Text(displayName)),
                              ],
                            ),
                          );
                        }).toList(),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                
                // 字体设置行
                Row(
                  children: [
                    Expanded(
                      flex: 2,
                      child: Text(
                        AppLocalizations.of(context)!.fontSetting,
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      flex: 3,
                      child: Consumer(
                        builder: (context, ref, child) {
                          final currentFont = ref.watch(fontFamilyProvider);
                          return DropdownButton<String>(
                            isExpanded: true,
                            value: currentFont,
                            onChanged: (String? newValue) {
                              if (newValue != null) {
                                ref.read(fontFamilyProvider.notifier).updateFont(newValue);
                              }
                            },
                            items: availableFonts.map((String font) {
                              return DropdownMenuItem<String>(
                                value: font,
                                child: Text(
                                  font,
                                  style: TextStyle(fontFamily: font),
                                ),
                              );
                            }).toList(),
                          );
                        },
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),

                // 启动动画设置行
                Row(
                  children: [
                    Expanded(
                      flex: 2,
                      child: Text(
                        appLocalizations.splashAnimationSetting,
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      flex: 3,
                      child: Consumer(
                        builder: (context, ref, child) {
                          final currentValue = ref.watch(splashAnimationProvider);
                          return Switch(
                            value: currentValue,
                            onChanged: (value) {
                              // 调用Notifier的更新方法
                              ref.read(splashAnimationProvider.notifier).updateSplashAnimation(value);
                            },
                          );
                        },
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),

                // 清除缓存
                ListTile(
                  leading: const Icon(Icons.cleaning_services_outlined),
                  title: const Text('清除缓存'),
                  subtitle: Text(_cacheSize ?? '计算中...'),
                  trailing: _isClearingCache
                      ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.chevron_right),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16),
                  tileColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  onTap: _isClearingCache ? null : _clearCache,
                ),
                const SizedBox(height: 10),

                // 清除数据
                ListTile(
                  leading: const Icon(Icons.delete_forever, color: Colors.red),
                  title: const Text('清除数据', style: TextStyle(color: Colors.red)),
                  subtitle: const Text('删除所有本地数据，包括账号、聊天记录和设置'),
                  trailing: _isClearingData
                      ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.chevron_right, color: Colors.red),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16),
                  tileColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  onTap: _isClearingData ? null : _clearData,
                ),
                const SizedBox(height: 20),
              ],
            ),
            
            // 其他设置分组
            ExpansionTile(
              title: Text(
                appLocalizations.otherSettings,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
              ),
              initiallyExpanded: _isExpanded[3],
              onExpansionChanged: (expanded) => setState(() => _isExpanded[3] = expanded),
              children: [
                const SizedBox(height: 10),
                ListTile(
                  leading: const Icon(Icons.keyboard),
                  title: Text(appLocalizations.shortcutSettings),
                  onTap: () {
                    if (mounted) {
                      Navigator.push(context, 
                        MaterialPageRoute(builder: (context) => const ShortcutSettingsScreen()));
                    }
                  },
                ),
                ListTile(
                  leading: const Icon(Icons.folder),
                  title: Text(appLocalizations.currentDataPathWithHint),
                  subtitle: SelectableText(
                    _configService.appDataPath,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        icon: const Icon(Icons.copy, size: 20),
                        onPressed: () async {
                          await Clipboard.setData(
                            ClipboardData(text: _configService.appDataPath),
                          );
                          if (mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('路径已复制')),
                            );
                          }
                        },
                      ),
                      IconButton(
                        icon: const Icon(Icons.edit),
                        onPressed: _isMigrating ? null : () => _changeDataPath(),
                      ),
                    ],
                  ),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16),
                  tileColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                ),
                const SizedBox(height: 10),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _changeDataPath() async {
    final newPath = await FilePicker.platform.getDirectoryPath();
    if (newPath == null) return;

    if (!mounted) return;
    setState(() => _isMigrating = true);

    BuildContext? dialogContext; // 保存对话框上下文
    
    try {
      final migrationProgress = ValueNotifier<MigrationProgress?>(null);
      bool migrationCancelled = false;
      
      // 显示对话框前检查当前上下文是否有效
      if (mounted) {
        showDialog(
          context: context,
          barrierDismissible: false,
          builder: (context) {
            dialogContext = context; // 保存对话框上下文
            return MigrationProgressDialog(
              progress: migrationProgress,
              onCancel: () {
                migrationCancelled = true;
                if (dialogContext != null && Navigator.canPop(dialogContext!)) {
                  Navigator.pop(dialogContext!);
                }
              },
            );
          },
        );
      }

      await _configService.updateAppDataPath(
        newPath, 
        onProgress: (current, total) {
          migrationProgress.value = MigrationProgress(current, total);
        },
        shouldCancel: () => migrationCancelled,
      );

      if (migrationCancelled) {
        // 检查当前组件是否仍挂载
        if (mounted) {
          final appLocalizations = AppLocalizations.of(context);
          if (appLocalizations != null) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(appLocalizations.migrationCancelled),
                behavior: SnackBarBehavior.floating,
                duration: const Duration(seconds: 3),
              )
            );
          }
        }
      } else {
        migrationProgress.value = MigrationProgress.complete();

        // 使用WidgetsBinding确保在下一帧执行
        WidgetsBinding.instance.addPostFrameCallback((_) {
          // 使用当前State的mounted检查
          if (mounted) {
            final appLocalizations = AppLocalizations.of(context);
            if (appLocalizations != null) {
              // 关闭对话框 - 使用保存的对话框上下文
              if (dialogContext != null && Navigator.canPop(dialogContext!)) {
                Navigator.pop(dialogContext!);
              }
              
              // 显示成功消息
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('${appLocalizations.migrationSuccess}$newPath'),
                  behavior: SnackBarBehavior.floating,
                  duration: const Duration(seconds: 3),
                )
              );
            }
          }
        });
      }
    } on Exception catch (e) {
      // 确保对话框关闭
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (dialogContext != null && Navigator.canPop(dialogContext!)) {
          Navigator.pop(dialogContext!);
        }
      });
      
      if (mounted) {
        final appLocalizations = AppLocalizations.of(context);
        if (appLocalizations != null) {
          if (e.toString().contains('目标文件夹必须为空')) {
            showDialog(
              context: context,
              builder: (context) => AlertDialog(
                title: Text(appLocalizations.targetFolderNotEmpty),
                content: Text(appLocalizations.selectEmptyFolderHint),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: Text(appLocalizations.confirm),
                  ),
                ],
              ),
            );
          } else if (e.toString().contains('迁移已取消')) {
            // 用户取消了迁移，不需要额外处理
          } else {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('${appLocalizations.migrationFailed}$e'),
                behavior: SnackBarBehavior.floating,
                backgroundColor: Colors.red,
              )
            );
          }
        }
      }
    } catch (e) {
      // 确保对话框关闭
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (dialogContext != null && Navigator.canPop(dialogContext!)) {
          Navigator.pop(dialogContext!);
        }
      });
      
      if (mounted) {
        final appLocalizations = AppLocalizations.of(context);
        if (appLocalizations != null) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('${appLocalizations.migrationFailed}$e'),
              behavior: SnackBarBehavior.floating,
              backgroundColor: Colors.red,
            )
          );
        }
      }
    } finally {
      if (mounted) {
        setState(() => _isMigrating = false);
      }
    }
  }

  String _getLanguageName(Locale locale, BuildContext context) {
    final appLocalizations = AppLocalizations.of(context)!;
    final languageCode = locale.languageCode;
    final scriptCode = locale.scriptCode;

    if (languageCode == 'zh') {
      switch (scriptCode) {
        case 'Hans': return appLocalizations.simplifiedChinese;
        case 'Hant': return appLocalizations.traditionalChinese;
        default: return appLocalizations.simplifiedChinese;
      }
    }

    switch (languageCode) {
      case 'en': return appLocalizations.english;
      case 'es': return appLocalizations.spanish;
      case 'ja': return '日本語'; // 日语
      case 'ko': return '한국어'; // 韩语
      case 'fr': return 'Français'; // 法语
      case 'de': return 'Deutsch'; // 德语
      case 'ru': return 'Русский'; // 俄语
      case 'ar': return 'العربية'; // 阿拉伯语
      default: return languageCode.toUpperCase();
    }
  }

  Widget _getFlagWidget(Locale locale) {
    // 使用 SVG 国旗组件替代之前的图标
    return SvgFlag(
      FlagData.parse(code: _getCountryCode(locale)),
      width: 30,
      height: 20,
    );
  }

  String _getCountryCode(Locale locale) {
    final languageCode = locale.languageCode;

    switch (languageCode) {
      case 'zh': return 'CN'; // 英语使用美国代码
      case 'en': return 'GB'; // 英语使用美国代码
      case 'es': return 'ES'; // 西班牙语使用西班牙代码
      case 'fr': return 'FR'; // 法语使用法国代码
      case 'de': return 'DE'; // 德语使用德国代码
      case 'ja': return 'JP'; // 日语使用日本代码
      case 'ko': return 'KR'; // 韩语使用韩国代码
      case 'ru': return 'RU'; // 俄语使用俄罗斯代码
      case 'ar': return 'SA'; // 阿拉伯语使用沙特阿拉伯代码
      default: return 'UN'; // 默认使用联合国代码
    }
  }
}

class MigrationProgress {
  final int current;
  final int total;
  final bool isComplete;

  MigrationProgress(this.current, this.total) : isComplete = false;

  MigrationProgress.complete()
    : current = 1,
      total = 1,
      isComplete = true;

  double get progress => isComplete ? 1.0 : current / total;
}

class MigrationProgressDialog extends StatelessWidget {
  final ValueNotifier<MigrationProgress?> progress;
  final VoidCallback onCancel;

  const MigrationProgressDialog({
    super.key,
    required this.progress,
    required this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final appLocalizations = AppLocalizations.of(context)!;
    
    return AlertDialog(
      title: Text(appLocalizations.migratingData),
      content: ValueListenableBuilder<MigrationProgress?>(
        valueListenable: progress,
        builder: (context, value, child) {
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (value?.isComplete == true)
                Text(appLocalizations.migrationComplete, style: const TextStyle(color: Colors.green))
              else
                Text('${appLocalizations.migratingFiles} ${value?.current ?? 0}/${value?.total ?? 1}'),
              const SizedBox(height: 20),
              LinearProgressIndicator(
                value: value?.progress ?? 0,
              ),
            ],
          );
        }
      ),
      actions: [
        TextButton(
          onPressed: onCancel,
          child: Text(appLocalizations.cancel),
        ),
      ],
    );
  }
}

// ===== 时间与地区设置 UI =====

/// 下拉选择行：左侧标签，右侧下拉框。
Widget _dropdownRow<T>({
  required String label,
  required T value,
  required List<DropdownMenuItem<T>> items,
  required void Function(T?) onChanged,
}) {
  return Padding(
    padding: const EdgeInsets.only(bottom: 20),
    child: Row(
      children: [
        Expanded(
          flex: 2,
          child: Text(label,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        ),
        const SizedBox(width: 10),
        Expanded(
          flex: 3,
          child: DropdownButton<T>(
            isExpanded: true,
            value: value,
            items: items,
            onChanged: onChanged,
          ),
        ),
      ],
    ),
  );
}

/// 「应用设置」分组中位于「语言」之上的「时间与地区」设置区块。
Widget _buildTimeRegionSection(BuildContext context, AppSettings s, WidgetRef ref) {
  final notifier = ref.read(appSettingsProvider.notifier);
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Padding(
        padding: EdgeInsets.only(bottom: 12),
        child: Text('时间与地区',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Colors.grey)),
      ),
      _dropdownRow<CalendarSystem>(
        label: '历法',
        value: s.calendar,
        items: CalendarSystem.values
            .map((e) => DropdownMenuItem(value: e, child: Text(calendarLabels[e]!)))
            .toList(),
        onChanged: (v) => notifier.setCalendar(v!),
      ),
      _dropdownRow<FirstDayOfWeek>(
        label: '每周第一天',
        value: s.firstDayOfWeek,
        items: FirstDayOfWeek.values
            .map((e) => DropdownMenuItem(value: e, child: Text(firstDayOfWeekLabels[e]!)))
            .toList(),
        onChanged: (v) => notifier.setFirstDayOfWeek(v!),
      ),
      _dropdownRow<DateFormatPattern>(
        label: '日期格式',
        value: s.dateFormat,
        items: DateFormatPattern.values
            .map((e) => DropdownMenuItem(value: e, child: Text(dateFormatLabels[e]!)))
            .toList(),
        onChanged: (v) => notifier.setDateFormat(v!),
      ),
      _dropdownRow<HourSystem>(
        label: '时间制式',
        value: s.hourFormat,
        items: HourSystem.values
            .map((e) => DropdownMenuItem(value: e, child: Text(hourFormatLabels[e]!)))
            .toList(),
        onChanged: (v) => notifier.setHourFormat(v!),
      ),
      _dropdownRow<TimeSource>(
        label: '时间来源',
        value: s.timeSource,
        items: TimeSource.values
            .map((e) => DropdownMenuItem(value: e, child: Text(timeSourceLabels[e]!)))
            .toList(),
        onChanged: (v) => notifier.setTimeSource(v!),
      ),
      _dropdownRow<String>(
        label: '时区',
        value: s.timezone,
        items: AppFormat.timezoneIds
            .map((id) => DropdownMenuItem(value: id, child: Text(timezoneLabel(id))))
            .toList(),
        onChanged: (v) => notifier.setTimezone(v!),
      ),
      _dropdownRow<String>(
        label: '地区',
        value: s.region,
        items: AppFormat.regionCodes
            .map((code) =>
                DropdownMenuItem(value: code, child: Text(regionLabels[code]!)))
            .toList(),
        onChanged: (v) => notifier.setRegion(v!),
      ),
      _dropdownRow<TemperatureUnit>(
        label: '温度单位',
        value: s.temperatureUnit,
        items: TemperatureUnit.values
            .map((e) => DropdownMenuItem(value: e, child: Text(temperatureUnitLabels[e]!)))
            .toList(),
        onChanged: (v) => notifier.setTemperatureUnit(v!),
      ),
      _dropdownRow<MeasurementSystem>(
        label: '计量系统',
        value: s.measurementSystem,
        items: MeasurementSystem.values
            .map((e) => DropdownMenuItem(value: e, child: Text(measurementSystemLabels[e]!)))
            .toList(),
        onChanged: (v) => notifier.setMeasurementSystem(v!),
      ),
      const SizedBox(height: 8),
      _TimePreview(settings: s),
    ],
  );
}

/// 实时预览：根据当前「时间与地区」设置展示格式化结果。
class _TimePreview extends StatefulWidget {
  final AppSettings settings;
  const _TimePreview({required this.settings});

  @override
  State<_TimePreview> createState() => _TimePreviewState();
}

class _TimePreviewState extends State<_TimePreview> {
  late DateTime _now;
  Timer? _timer;
  Duration? _networkOffset;
  bool _networkFailed = false;

  @override
  void initState() {
    super.initState();
    _now = DateTime.now();
    _tick();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
    _syncNetwork();
  }

  void _tick() {
    if (!mounted) return;
    setState(() {
      if (widget.settings.timeSource == TimeSource.network && _networkOffset != null) {
        _now = DateTime.now().toUtc().add(_networkOffset!);
      } else {
        _now = DateTime.now();
      }
    });
  }

  Future<void> _syncNetwork() async {
    if (widget.settings.timeSource != TimeSource.network) return;
    final utc = await NetworkTime.fetchUtc();
    if (!mounted) return;
    setState(() {
      if (utc != null) {
        _networkOffset = utc.difference(DateTime.now().toUtc());
        _networkFailed = false;
      } else {
        _networkFailed = true;
      }
    });
  }

  @override
  void didUpdateWidget(covariant _TimePreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.settings.timeSource != widget.settings.timeSource) {
      _networkOffset = null;
      _networkFailed = false;
      _syncNetwork();
      _tick();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.settings;
    final dateStr = AppFormat.formatDate(_now, s);
    final timeStr = AppFormat.formatTime(_now, s);
    return Card(
      margin: const EdgeInsets.only(top: 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('预览', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 6),
            Text('日期：$dateStr'),
            Text('时间：$timeStr  (${timezoneLabel(s.timezone)})'),
            Text('温度：${AppFormat.formatTemperature(23.5, s)}'),
            Text('距离：${AppFormat.formatDistance(1234.5, s)}'),
            Text('重量：${AppFormat.formatWeight(68.2, s)}'),
            Text('数字：${AppFormat.formatNumber(1234567.89, s)}'),
            if (s.timeSource == TimeSource.network)
              Text(
                _networkFailed
                    ? '时间来源：网络获取失败，已回退设备时间'
                    : (_networkOffset != null
                        ? '时间来源：网络校时已生效'
                        : '时间来源：网络（获取中…）'),
                style: const TextStyle(fontSize: 12, color: Colors.grey),
              ),
          ],
        ),
      ),
    );
  }
}
    