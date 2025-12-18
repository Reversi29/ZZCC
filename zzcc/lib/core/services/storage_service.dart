// lib/core/services/storage_service.dart
import 'package:hive/hive.dart';
import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:zzcc/core/services/logger_service.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:flutter/material.dart';
import 'package:zzcc/data/models/user_settings_model.dart';
import 'package:zzcc/data/models/theme_model.dart';
import 'package:zzcc/data/models/shared_file_settings_model.dart';
import 'package:zzcc/data/models/torrent_model.dart';
import 'package:synchronized/synchronized.dart';
// import 'dart:convert';

class StorageService {
  late Box _appBox;
  late Box _userRegistryBox;
  late String _storagePath;
  bool _isInitialized = false;
  final _sharedFileSettingsLock = Lock();
  Box? _cachedSharedFileBox;

  Future<void> init(String appDataPath) async {
    if (_isInitialized) return;
    _storagePath = appDataPath;
    Hive.init(_storagePath);
    
    if (!Hive.isBoxOpen('app_settings')) {
      _appBox = await Hive.openBox('app_settings');
    } else {
      _appBox = Hive.box('app_settings');
    }
    
    if (!Hive.isBoxOpen('user_registry')) {
      _userRegistryBox = await Hive.openBox('user_registry');
    } else {
      _userRegistryBox = Hive.box('user_registry');
    }

    _isInitialized = true;
  }

  // 用户注册表操作
  void setCurrentUser(String userId) => _userRegistryBox.put('currentUser', userId);
  String? getCurrentUser() => _userRegistryBox.get('currentUser');
  void clearCurrentUser() => _userRegistryBox.delete('currentUser');
  bool get isUserRegistryEmpty => _userRegistryBox.isEmpty;

  // 应用数据操作
  dynamic getFromAppBox(String key) => _appBox.get(key);
  void saveToAppBox(String key, dynamic value) => _appBox.put(key, value);
  void deleteFromAppBox(String key) => _appBox.delete(key);
  
  // 安全关闭
  Future<void> close() async {
    await _appBox.close();
    await _userRegistryBox.close();
  }

  void registerUser(String uid, String ciphertext) {
    _userRegistryBox.put(uid, ciphertext);
  }

  String? getUserRegistry(String uid) {
    return _userRegistryBox.get(uid);
  }

  Future<Box> _openUserBox(String ciphertext) async {
    final userDir = Directory(path.join(_storagePath, ciphertext));
    if (!await userDir.exists()) {
      await userDir.create(recursive: true);
    }
    return await Hive.openBox('user_data', path: userDir.path);
  }

  // 新增：保存用户信息到对应用户的盒子
  Future<void> saveUserInfo(String ciphertext, Map<String, dynamic> info) async {
    final userBox = await _openUserBox(ciphertext);
    await userBox.putAll(info);
    await userBox.close();
  }

  // 新增：获取指定用户的信息
  Future<Map<String, dynamic>?> getUserInfo(String ciphertext) async {
    try {
      final userBox = await _openUserBox(ciphertext);
      final info = userBox.toMap().cast<String, dynamic>();
      await userBox.close();
      return info;
    } catch (e) {
      return null;
    }
  }

  Future<void> updateUserInfo(String userDataPath, Map<String, dynamic> newInfo) async {
    if (userDataPath.isEmpty) return;

    try {
      // 打开用户数据盒子（user_data.hive）
      final box = await Hive.openBox(
        'user_data',
        path: userDataPath,
      );

      // 合并并更新数据
      for (final entry in newInfo.entries) {
        await box.put(entry.key, entry.value);
      }

      await box.close();
    } catch (e) {
      getIt<LoggerService>().error('更新用户信息失败: $e');
      rethrow;
    }
  }

  // 新增：获取指定用户的特定信息
  Future<dynamic> getUserInfoByKey(String ciphertext, String key) async {
    final userBox = await _openUserBox(ciphertext);
    final value = userBox.get(key);
    await userBox.close();
    return value;
  }

  Future<Map<String, dynamic>> readExternalHiveFile(String filePath) async {
    final file = File(filePath);
    if (!await file.exists()) {
      return {'success': false, 'message': '文件不存在'};
    }

    final dirPath = path.dirname(filePath);
    final fileName = path.basenameWithoutExtension(filePath); // 原文件名（不含扩展名）
    final lockFile = File('$dirPath/$fileName.lock'); // 锁文件路径

    try {
      // 1. 检查并删除残留的锁文件（防止上次异常关闭导致的冲突）
      if (await lockFile.exists()) {
        await lockFile.delete();
      }

      // 2. 打开现有Hive文件（使用原文件名作为Box名称，避免创建新文件）
      final box = await Hive.openBox(
        fileName, // 关键：使用原文件名，而非临时名称
        path: dirPath,
      );

      // 3. 读取数据
      final data = box.toMap().cast<String, dynamic>();
      
      // 4. 强制关闭并清理锁文件
      await box.close();
      if (await lockFile.exists()) {
        await lockFile.delete(); // 确保锁文件被删除
      }

      return {
        'success': true,
        'data': data,
        'message': '读取成功'
      };
    } catch (e) {
      // 异常时清理可能产生的临时文件
      final possibleTempFile = File('$dirPath/$fileName.hive');
      if (await possibleTempFile.exists() && possibleTempFile.path != file.path) {
        await possibleTempFile.delete();
      }
      if (await lockFile.exists()) {
        await lockFile.delete();
      }
      return {'success': false, 'message': '读取失败: ${e.toString()}'};
    }
  }

  // 用户设置相关操作
  Future<Box> _openUserSettingsBox(String ciphertext) async {
    final userDir = Directory(path.join(_storagePath, ciphertext));
    if (!await userDir.exists()) {
      await userDir.create(recursive: true);
    }
    return await Hive.openBox('user_settings', path: userDir.path);
  }

  // 保存用户设置
  Future<void> saveUserSettings(String ciphertext, UserSettingsModel settings) async {
    final settingsBox = await _openUserSettingsBox(ciphertext);
    
    // 将主题颜色转换为可存储的格式
    final themeData = settings.customTheme != null ? {
      'primaryColor': settings.customTheme!.primaryColor.toARGB32(),
      'leftSidebarColor': settings.customTheme!.leftSidebarColor?.toARGB32(),
      'rightPanelColor': settings.customTheme!.rightPanelColor?.toARGB32(),
      'name': settings.customTheme!.name,
      // 图片路径单独处理
      'leftBackgroundImage': settings.customTheme!.leftBackgroundImage?.path,
      'rightBackgroundImage': settings.customTheme!.rightBackgroundImage?.path,
    } : null;

    await settingsBox.putAll({
      'customTheme': themeData,
      'useSystemTheme': settings.useSystemTheme,
      'preferredFont': settings.preferredFont,
      'notificationsEnabled': settings.notificationsEnabled,
    });
    
    await settingsBox.close();
  }

  // 获取用户设置
  Future<UserSettingsModel?> getUserSettings(String ciphertext) async {
    try {
      final settingsBox = await _openUserSettingsBox(ciphertext);
      final settingsData = settingsBox.toMap().cast<String, dynamic>();
      await settingsBox.close();

      // 重建主题对象
      CustomTheme? customTheme;
      if (settingsData['customTheme'] is Map) {
        final themeMap = settingsData['customTheme'] as Map;
        customTheme = CustomTheme(
          primaryColor: Color(themeMap['primaryColor'] as int),
          leftSidebarColor: themeMap['leftSidebarColor'] != null 
              ? Color(themeMap['leftSidebarColor'] as int)
              : null,
          rightPanelColor: themeMap['rightPanelColor'] != null
              ? Color(themeMap['rightPanelColor'] as int)
              : null,
          leftBackgroundImage: themeMap['leftBackgroundImage'] != null
              ? File(themeMap['leftBackgroundImage'] as String)
              : null,
          rightBackgroundImage: themeMap['rightBackgroundImage'] != null
              ? File(themeMap['rightBackgroundImage'] as String)
              : null,
          name: themeMap['name'] as String? ?? '自定义主题',
        );
      }

      return UserSettingsModel(
        customTheme: customTheme,
        useSystemTheme: settingsData['useSystemTheme'] as bool? ?? true,
        preferredFont: settingsData['preferredFont'] as String?,
        notificationsEnabled: settingsData['notificationsEnabled'] as bool? ?? true,
      );
    } catch (e) {
      getIt<LoggerService>().error('获取用户设置失败: $e');
      return null;
    }
  }

  // 更新用户设置的特定字段
  Future<void> updateUserSettingsField(
    String ciphertext, 
    String field, 
    dynamic value
  ) async {
    final settingsBox = await _openUserSettingsBox(ciphertext);
    await settingsBox.put(field, value);
    await settingsBox.close();
  }

  // 清除用户设置
  Future<void> clearUserSettings(String ciphertext) async {
    final settingsBox = await _openUserSettingsBox(ciphertext);
    await settingsBox.clear();
    await settingsBox.close();
  }

  Future<void> _ensureAppBoxOpen() async {
    if (!_appBox.isOpen) {
      _appBox = await Hive.openBox('app_settings');
    }
  }

  Future<void> saveLocale(Locale locale) async {
    await _ensureAppBoxOpen();

    final localeString = '${locale.languageCode}|'
                        '${locale.scriptCode ?? ''}|'
                        '${locale.countryCode ?? ''}';
    await _appBox.put('locale', localeString);
  }

  Future<Locale?> getSavedLocale() async {
    await _ensureAppBoxOpen();
    final dynamic localeData = _appBox.get('locale');
    
    if (localeData is String) {
      try {
        // 安全解析字符串
        final parts = localeData.split('|');
        if (parts.length >= 3) {
          final languageCode = parts[0];
          final scriptCode = parts[1].isEmpty ? null : parts[1];
          final countryCode = parts[2].isEmpty ? null : parts[2];
          
          if (languageCode.isNotEmpty) {
            return Locale.fromSubtags(
              languageCode: languageCode,
              scriptCode: scriptCode,
              countryCode: countryCode,
            );
          }
        }
      } catch (e) {
        getIt<LoggerService>().error('解析语言设置失败: $e');
      }
    }
    
    return null;
  }

  // 1. 保存字体设置
  Future<void> savePreferredFont(String font) async {
    await _ensureAppBoxOpen();
    await _appBox.put('preferredFont', font);
  }

  // 2. 获取保存的字体设置
  Future<String?> getSavedFont() async {
    await _ensureAppBoxOpen();
    return _appBox.get('preferredFont') as String?;
  }

  // 3. 保存启动页动画状态
  Future<void> saveSplashAnimationStatus(bool enabled) async {
    await _ensureAppBoxOpen();
    await _appBox.put('splashAnimationSetting', enabled);
  }

  // 4. 获取启动页动画状态
  Future<bool> getSplashAnimationStatus() async {
    await _ensureAppBoxOpen();
    // 默认启用动画
    return _appBox.get('splashAnimationSetting', defaultValue: true) as bool;
  }

  // 共享文件设置相关操作
  Future<Box> _openSharedFileSettingsBox() async {
    // 缓存存在且未关闭，直接返回
    if (_cachedSharedFileBox != null && _cachedSharedFileBox!.isOpen) {
      return _cachedSharedFileBox!;
    }

    final currentUser = getCurrentUser();
    if (currentUser == null) {
      throw Exception('未找到当前登录用户');
    }
    
    final storedCiphertext = getUserRegistry(currentUser);
    if (storedCiphertext == null) {
      throw Exception('当前用户无加密配置');
    }
    
    final settingsDir = Directory(path.join(_storagePath, storedCiphertext));
    if (!await settingsDir.exists()) {
      await settingsDir.create(recursive: true);
    }

    // 打开box并缓存
    _cachedSharedFileBox = await Hive.openBox(
      'shared_file_settings',
      path: settingsDir.path
    );
    return _cachedSharedFileBox!;
  }

  // 打开或创建同一 settingsDir 下的 torrent 任务数据库盒子
  Future<Box> _openTorrentTasksBox() async {
    final currentUser = getCurrentUser();
    if (currentUser == null) {
      throw Exception('未找到当前登录用户');
    }
    final storedCiphertext = getUserRegistry(currentUser);
    if (storedCiphertext == null) {
      throw Exception('当前用户无加密配置');
    }

    final settingsDir = Directory(path.join(_storagePath, storedCiphertext));
    if (!await settingsDir.exists()) {
      await settingsDir.create(recursive: true);
    }

    // 使用专用盒子名称保存任务队列
    final box = await Hive.openBox('torrent_tasks', path: settingsDir.path);
    return box;
  }

  // 保存单个torrent任务到box（以id为key）
  Future<void> saveTorrentTask(TorrentInfo info) async {
    final box = await _openTorrentTasksBox();
    try {
      await box.put(info.id, info.toMap());
    } finally {
      await box.close();
    }
  }

  Future<List<TorrentInfo>> getAllTorrentTasks() async {
    final box = await _openTorrentTasksBox();
    try {
      final data = box.toMap().cast<String, dynamic>();
      final List<TorrentInfo> list = [];
      for (final entry in data.entries) {
        if (entry.value is Map) {
          list.add(TorrentInfo.fromMap(Map<String, dynamic>.from(entry.value)));
        }
      }
      return list;
    } finally {
      await box.close();
    }
  }

  Future<void> updateTorrentTask(String id, Map<String, dynamic> fields) async {
    final box = await _openTorrentTasksBox();
    try {
      final existing = box.get(id);
      if (existing is Map) {
        final merged = Map<String, dynamic>.from(existing)..addAll(fields);
        await box.put(id, merged);
      } else {
        await box.put(id, fields);
      }
    } finally {
      await box.close();
    }
  }

  Future<void> deleteTorrentTask(String id) async {
    final box = await _openTorrentTasksBox();
    try {
      await box.delete(id);
    } finally {
      await box.close();
    }
  }

  // 保存共享文件设置
  Future<void> saveSharedFileSettings(SharedFileSettingsModel settings) async {
    await _sharedFileSettingsLock.synchronized(() async {
      try {
        final settingsBox = await _openSharedFileSettingsBox();
        
        await settingsBox.putAll({
          'defaultSavePath': settings.defaultSavePath,
          'maxDownloadSpeed': settings.maxDownloadSpeed,
          'maxUploadSpeed': settings.maxUploadSpeed,
          'lastUsedPath': settings.lastUsedPath,
          'incompleteTorrentPath': settings.incompleteTorrentPath,
          'isManualMode': settings.isManualMode,
          'useDifferentIncompletePath': settings.useDifferentIncompletePath,
          'rememberLastPath': settings.rememberLastPath,
        });
        
        // 移除自动关闭：避免后续操作需要重新打开
        // await settingsBox.close();
      } catch (e) {
        getIt<LoggerService>().error('保存共享文件设置失败: $e');
        rethrow; // 抛出异常让上层处理
      }
    });
  }

  // 获取共享文件设置
  Future<SharedFileSettingsModel> getSharedFileSettings() async {
    return await _sharedFileSettingsLock.synchronized(() async {
      try {
        final settingsBox = await _openSharedFileSettingsBox();
        
        // 读取配置（带默认值）
        final settings = SharedFileSettingsModel(
          defaultSavePath: settingsBox.get('defaultSavePath') as String?,
          maxDownloadSpeed: settingsBox.get('maxDownloadSpeed') as String? ?? '无限制',
          maxUploadSpeed: settingsBox.get('maxUploadSpeed') as String? ?? '无限制',
          lastUsedPath: settingsBox.get('lastUsedPath') as String?,
          incompleteTorrentPath: settingsBox.get('incompleteTorrentPath') as String?,
          isManualMode: settingsBox.get('isManualMode') as bool? ?? true,
          useDifferentIncompletePath: settingsBox.get('useDifferentIncompletePath') as bool? ?? false,
          rememberLastPath: settingsBox.get('rememberLastPath') as bool? ?? true,
        );

        // 移除自动关闭
        // await settingsBox.close();
        return settings;
      } catch (e) {
        getIt<LoggerService>().error('获取共享文件设置失败: $e');
        // 返回默认配置，避免页面崩溃
        return SharedFileSettingsModel();
      }
    });
  }

  // 更新共享文件设置的特定字段
  Future<void> updateSharedFileSettingField(String field, dynamic value) async {
    await _sharedFileSettingsLock.synchronized(() async {
      try {
        final settingsBox = await _openSharedFileSettingsBox();
        await settingsBox.put(field, value);
        // 移除自动关闭
      } catch (e) {
        getIt<LoggerService>().error('更新共享文件设置字段失败: $field, $e');
        rethrow;
      }
    });
  }

  // 清除共享文件设置
  Future<void> clearSharedFileSettings() async {
    await _sharedFileSettingsLock.synchronized(() async {
      try {
        final settingsBox = await _openSharedFileSettingsBox();
        await settingsBox.clear();
        // 移除自动关闭
      } catch (e) {
        getIt<LoggerService>().error('清除共享文件设置失败: $e');
        rethrow;
      }
    });
  }

  Future<void> closeHive() async {
    try {
      if (_appBox.isOpen) await _appBox.close();
      if (_userRegistryBox.isOpen) await _userRegistryBox.close();
      
      // 强制关闭所有 Hive 实例
      await Hive.close();
      getIt<LoggerService>().info('所有 Hive 数据库已安全关闭');
    } catch (e) {
      getIt<LoggerService>().error('关闭 Hive 数据库时出错: $e');
    }
  }
}