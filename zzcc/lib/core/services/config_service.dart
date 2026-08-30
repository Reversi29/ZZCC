import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:zzcc/core/services/logger_service.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/core/di/service_locator.dart';

class ConfigService {
  static const String _configFileName = 'zzcc_config.json';
  Map<String, dynamic> _config = {};
  String _configPath = '';

  Map<String, dynamic> get config => _config;
  bool get keepLoggedIn => _config['keepLoggedIn'] ?? false;

  String get nebulaApiBaseUrl =>
      _config['nebulaApiBaseUrl'] ?? 'http://124.223.47.167:8001/api/v1/';
  String get nebulaApiKey =>
      _config['nebulaApiKey'] ?? 'zzcc-secret-key-2025';

  Future<void> updateNebulaApiConfig(String baseUrl, String apiKey) async {
    _config['nebulaApiBaseUrl'] = baseUrl;
    _config['nebulaApiKey'] = apiKey;
    await _saveConfig();
  }

  Future<void> updateKeepLoggedIn(bool value) async {
    _config['keepLoggedIn'] = value;
    await _saveConfig();
  }

  Future<bool> isUserLoggedIn() async {
    if (!keepLoggedIn) return false;
    try {
      return getIt<StorageService>().getCurrentUser() != null;
    } catch (e) {
      getIt<LoggerService>().error('Error reading user registry: $e');
      return false;
    }
  }

  Future<void> init() async {
    try {
      _configPath = await _resolveConfigPath();
      getIt<LoggerService>().debug('配置文件路径: $_configPath');

      _config = await _loadConfig();
      if (_config.isEmpty) {
        _config = {
          'appDataPath': await _defaultAppDataPath(),
          'keepLoggedIn': true,
        };
        await _saveConfig();
      }
      getIt<LoggerService>().debug('APP基本设置: $_config');
    } catch (e) {
      getIt<LoggerService>().error('Config init failed: $e');
      _configPath = '/$_configFileName';
      _config = {'appDataPath': '/', 'keepLoggedIn': true};
    }
  }

  Future<Map<String, dynamic>> _loadConfig() async {
    try {
      final file = File(_configPath);
      if (await file.exists()) {
        final content = await file.readAsString();
        return json.decode(content);
      }
    } catch (_) {
      // Web: no file I/O
    }
    return {};
  }

  Future<String> _resolveConfigPath() async {
    try {
      final os = Platform.operatingSystem;
      if (os == 'macos') {
        final dir = await getApplicationSupportDirectory();
        return '${dir.path}/$_configFileName';
      } else if (os == 'windows') {
        return '${Platform.environment['LOCALAPPDATA']!}\\zzcc\\$_configFileName';
      } else {
        final ep = Platform.resolvedExecutable;
        return path.join(File(ep).parent.path, _configFileName);
      }
    } catch (_) {
      // Web: use IndexedDB-backed path_provider
      final dir = await getApplicationDocumentsDirectory();
      return path.join(dir.path, _configFileName);
    }
  }

  Future<String> _defaultAppDataPath() async {
    try {
      if (Platform.operatingSystem == 'windows') {
        return '${Platform.environment['LOCALAPPDATA']!}\\zzcc\\';
      }
    } catch (_) {}
    final dir = await getApplicationDocumentsDirectory();
    return '${dir.path}/';
  }

  String get appDataPath => _replaceUsernamePlaceholder(_config['appDataPath'] ?? '');

  String _replaceUsernamePlaceholder(String p) {
    if (!p.contains('<username>')) return p;
    String u = 'user';
    try {
      u = Platform.environment['USERNAME'] ??
          Platform.environment['USER'] ??
          'user';
    } catch (_) {}
    return p.replaceAll('<username>', u);
  }

  Future<void> _saveConfig() async {
    try {
      final file = File(_configPath);
      await file.writeAsString(json.encode(_config));
    } catch (_) {
      // Web: config kept in memory only
    }
  }

  Future<bool> _isDirectoryEmpty(Directory dir) async {
    try { return (await dir.list().toList()).isEmpty; } catch (_) { return false; }
  }

  Future<void> _migrateData(
    Directory source,
    Directory target, {
    void Function(int current, int total)? onProgress,
    bool Function()? shouldCancel,
  }) async {
    try {
      if (!await target.exists()) await target.create(recursive: true);
      final files = await source.list(recursive: true).toList();
      final logger = getIt<LoggerService>();
      for (int i = 0; i < files.length; i++) {
        if (shouldCancel != null && shouldCancel()) return;
        onProgress?.call(i + 1, files.length);
        final entity = files[i];
        if (entity is File) {
          if (path.basename(entity.path).endsWith('.lock')) continue;
          final rp = path.relative(entity.path, from: source.path);
          final df = File(path.join(target.path, rp));
          if (!await df.parent.exists()) await df.parent.create(recursive: true);
          await entity.copy(df.path);
        } else if (entity is Directory) {
          final rp = path.relative(entity.path, from: source.path);
          final dd = Directory(path.join(target.path, rp));
          if (!await dd.exists()) await dd.create(recursive: true);
        }
      }
      logger.debug('Migrated ${files.length} items');
    } catch (e) {
      getIt<LoggerService>().error('Migration failed: $e');
      rethrow;
    }
  }

  Future<void> updateAppDataPath(
    String newPath, {
    void Function(int current, int total)? onProgress,
    bool Function()? shouldCancel,
  }) async {
    newPath = _replaceUsernamePlaceholder(newPath);
    if (newPath == appDataPath) return;
    final oldDir = Directory(appDataPath);
    final newDir = Directory(newPath);
    if (await newDir.exists()) {
      if (!await _isDirectoryEmpty(newDir)) throw Exception('目标文件夹必须为空');
    } else {
      await newDir.create(recursive: true);
    }
    await getIt<StorageService>().closeHive();
    if (await oldDir.exists()) {
      await _migrateData(oldDir, newDir, onProgress: onProgress, shouldCancel: shouldCancel);
      if (shouldCancel != null && shouldCancel()) {
        await newDir.delete(recursive: true);
        throw Exception('迁移已取消');
      }
      await oldDir.delete(recursive: true);
    }
    _config['appDataPath'] = newPath;
    await _saveConfig();
  }

  bool get enableSplashAnimation => _config['enableSplashAnimation'] ?? true;
  Future<void> updateSplashAnimation(bool enable) async {
    _config['enableSplashAnimation'] = enable;
    await _saveConfig();
  }

  String? get chatAccessToken => _config['chatAccessToken'] as String?;
  String? get chatUserId => _config['chatUserId'] as String?;
  String? get chatDisplayName => _config['chatDisplayName'] as String?;

  Future<void> saveChatAuth({required String? accessToken, required String? userId, String? displayName}) async {
    _config['chatAccessToken'] = accessToken;
    _config['chatUserId'] = userId;
    _config['chatDisplayName'] = displayName;
    await _saveConfig();
  }

  Future<void> clearChatAuth() async {
    _config.remove('chatAccessToken');
    _config.remove('chatUserId');
    _config.remove('chatDisplayName');
    await _saveConfig();
  }
}
