import 'dart:convert';
import 'dart:io';
// import 'dart:typed_data';
import 'package:path_provider/path_provider.dart';
import 'package:intl/intl.dart';
import 'package:flutter/foundation.dart' show kDebugMode;
import 'dart:developer';

class LoggerService {
  static final LoggerService _instance = LoggerService._internal();
  late File _logFile;
  bool _initialized = false;

  factory LoggerService() => _instance;

  LoggerService._internal();

  Future<void> init() async {
    if (_initialized) return;
    
    try {
      final directory = await getApplicationDocumentsDirectory();
      _logFile = File('${directory.path}/system_logs.log');
      
      bool fileExists = await _logFile.exists();
      if (!fileExists) {
        // 创建文件并写入UTF-8 BOM
        await _logFile.create();
        await _logFile.writeAsBytes([0xEF, 0xBB, 0xBF]);
      }
      
      _initialized = true;
      
      // 在控制台输出日志文件路径
      if (kDebugMode) {
        log('日志文件路径: ${_logFile.path}');
      }
    } catch (e) {
      // 如果无法创建日志文件，至少记录到控制台
      log('无法初始化日志文件: $e');
    }
  }

  Future<void> _writeLog(String level, String message) async {
    if (!_initialized) {
      // 如果未初始化，尝试初始化
      await init();
    }
    
    final timestamp = DateFormat('yyyy-MM-dd HH:mm:ss').format(DateTime.now());
    final logEntry = '$timestamp [$level] $message';
    
    // 在控制台输出日志（仅在调试模式）
    if (kDebugMode) {
      log(logEntry);
    }
    
    try {
      // 使用UTF8编码器将字符串转换为字节列表
      List<int> bytes = utf8.encode('$logEntry\n');
      // 追加写入文件
      await _logFile.writeAsBytes(bytes, mode: FileMode.append);
    } catch (e) {
      // 如果文件写入失败，至少记录到控制台
      log('写入日志失败: $logEntry | 错误: $e');
    }
  }

  Future<void> info(String message) => _writeLog('INFO', message);
  Future<void> warning(String message) => _writeLog('WARNING', message);
  Future<void> error(String message, [dynamic error]) {
    final errorMsg = error != null ? ': $error' : '';
    return _writeLog('ERROR', '$message$errorMsg');
  }
  Future<void> debug(String message) => _writeLog('DEBUG', message);
}