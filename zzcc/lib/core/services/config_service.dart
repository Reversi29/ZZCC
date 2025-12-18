// lib/core/services/config_service.dart
import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:crypto/crypto.dart';
import 'package:path_provider/path_provider.dart';
import 'package:zzcc/core/services/logger_service.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/core/di/service_locator.dart';

class ConfigService {
  static const String _configFileName = 'zzcc_config.json';
  Map<String, dynamic> _config = {};
  late String _configPath;

  // 添加获取整个配置的方法
  Map<String, dynamic> get config => _config;

  bool get keepLoggedIn => _config['keepLoggedIn'] ?? false;

  Future<void> updateKeepLoggedIn(bool value) async {
    _config['keepLoggedIn'] = value;
    await _saveConfig();
  }

  // 添加检查登录状态的方法
  Future<bool> isUserLoggedIn() async {
    if (!keepLoggedIn) return false;
    
    try {
      final storage = getIt<StorageService>();
      return storage.getCurrentUser() != null;
    } catch (e) {
      getIt<LoggerService>().error('Error reading user registry: $e');
      return false;
    }
  }

  Future<void> init() async {
    try {
      // 获取应用程序运行目录
      final executablePath = Platform.resolvedExecutable;
      final appDir = File(executablePath).parent.path;
      _configPath = '$appDir/$_configFileName';

      getIt<LoggerService>().debug('配置文件路径: $_configPath');
      
      final file = File(_configPath);
      if (await file.exists()) {
        final content = await file.readAsString();
        _config = json.decode(content);
      } else {
        // 设置默认路径
        final defaultPath = await _getDefaultAppDataPath();
        _config = {
          'appDataPath': defaultPath,
          'keepLoggedIn': true,
          };
        await _saveConfig();
      }
      getIt<LoggerService>().debug('APP基本设置: $_config');
    } catch (e) {
      getIt<LoggerService>().error('Config init failed: $e');
      rethrow;
    }
  }

  String get appDataPath {
    final path = _config['appDataPath'] ?? '';
    return _replaceUsernamePlaceholder(path);
  }

  String _replaceUsernamePlaceholder(String path) {
    if (path.contains('<username>')) {
      final username = Platform.environment['USERNAME'] ?? 
                      Platform.environment['USER'] ?? 
                      'user';
      return path.replaceAll('<username>', username);
    }
    return path;
  }

  Future<void> updateAppDataPath(
    String newPath, {
    void Function(int current, int total)? onProgress,
    bool Function()? shouldCancel,
  }) async {
    newPath = _replaceUsernamePlaceholder(newPath);
    final oldPath = appDataPath;

    if (oldPath == newPath) return;

    final oldDir = Directory(oldPath);
    final newDir = Directory(newPath);

    // 检查目标目录是否为空
    if (await newDir.exists()) {
      final isEmpty = await _isDirectoryEmpty(newDir);
      if (!isEmpty) {
        throw Exception('目标文件夹必须为空');
      }
    } else {
      await newDir.create(recursive: true);
    }

    final storageService = getIt<StorageService>();
    await storageService.closeHive();

    if (await oldDir.exists()) {
      await _migrateData(
        oldDir, 
        newDir, 
        onProgress: onProgress,
        shouldCancel: shouldCancel,
      );
      
      // 检查是否取消了迁移
      if (shouldCancel != null && shouldCancel()) {
        // 删除已复制的文件
        await newDir.delete(recursive: true);
        throw Exception('迁移已取消');
      }
      
      await oldDir.delete(recursive: true);
      getIt<LoggerService>().debug('Deleted old data directory: $oldPath');
    }

    _config['appDataPath'] = newPath;
    await _saveConfig();
  }

  Future<bool> _isDirectoryEmpty(Directory dir) async {
    try {
      final files = await dir.list().toList();
      return files.isEmpty;
    } catch (e) {
      return false;
    }
  }

  Future<void> _migrateData(
    Directory source, 
    Directory target, {
    void Function(int current, int total)? onProgress,
    bool Function()? shouldCancel,
  }) async {
    try {
      if (!await target.exists()) {
        await target.create(recursive: true);
      }

      final sourceFiles = await source.list(recursive: true).toList();
      final logger = getIt<LoggerService>();
      final totalFiles = sourceFiles.length;
      int currentFile = 0;

      for (var entity in sourceFiles) {
        // 检查是否取消了迁移
        if (shouldCancel != null && shouldCancel()) {
          return;
        }
        
        currentFile++;
        onProgress?.call(currentFile, totalFiles);
        
        if (entity is File) {
            // 跳过lock文件
          if (path.basename(entity.path).endsWith('.lock')) {
            logger.debug('Skipping lock file: ${entity.path}');
            continue;
          }
          
          final relativePath = path.relative(entity.path, from: source.path);
          final destFile = File(path.join(target.path, relativePath));
          
          if (!await destFile.parent.exists()) {
            await destFile.parent.create(recursive: true);
          }

          final sourceHash = await _calculateFileHash(entity);
          await entity.copy(destFile.path);
          final destHash = await _calculateFileHash(destFile);

          if (sourceHash != destHash) {
            logger.error('Hash mismatch: ${entity.path}');
            throw Exception('File hash verification failed for ${entity.path}');
          }
        } else if (entity is Directory) {
          // 确保目标目录存在
          final relativePath = path.relative(entity.path, from: source.path);
          final destDir = Directory(path.join(target.path, relativePath));
          if (!await destDir.exists()) {
            await destDir.create(recursive: true);
          }
        }
      }
      
      logger.debug('Successfully migrated $totalFiles items from ${source.path} to ${target.path}');
    } catch (e) {
      getIt<LoggerService>().error('Data migration failed: $e');
      rethrow;
    }
  }

  Future<String> _calculateFileHash(File file) async {
    final stream = file.openRead();
    final hash = await sha256.bind(stream).first;
    return hash.toString();
  }

  Future<void> _saveConfig() async {
    final file = File(_configPath);
    await file.writeAsString(json.encode(_config));
  }

  Future<String> _getDefaultAppDataPath() async {
    if (Platform.isWindows) {
      final appData = Platform.environment['LOCALAPPDATA']!;
      return '$appData\\zzcc\\';
    }
    final dir = await getApplicationDocumentsDirectory();
    return '${dir.path}/';
  }

  bool get enableSplashAnimation {
    return _config['enableSplashAnimation'] ?? true; // 默认开启
  }

  Future<void> updateSplashAnimation(bool enable) async {
    _config['enableSplashAnimation'] = enable;
    await _saveConfig();
  }
}