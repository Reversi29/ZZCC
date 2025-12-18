import 'package:flutter/material.dart';
import 'package:zzcc/data/models/theme_model.dart';
import 'package:zzcc/presentation/widgets/theme_selector.dart';
import 'package:zzcc/presentation/pages/settings/shortcut_settings.dart';
import 'package:zzcc/core/services/config_service.dart';
import 'package:file_picker/file_picker.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/l10n/generated/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/presentation/providers/locale_provider.dart';
import 'package:svg_flag/svg_flag.dart';
import 'package:zzcc/presentation/providers/font_provider.dart';
import 'package:zzcc/presentation/providers/splash_provider.dart';
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
  }

  @override
  Widget build(BuildContext context) {
    final localeProvider = ref.watch(appLocaleProvider);
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
                  subtitle: Text(
                    _configService.appDataPath,
                    overflow: TextOverflow.ellipsis,
                    maxLines: 1,
                  ),
                  trailing: IconButton(
                    icon: const Icon(Icons.edit),
                    onPressed: _isMigrating ? null : () => _changeDataPath(),
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
    