// lib/core/services/torrent_service.dart
import 'dart:ffi';
import 'dart:io';
// import 'dart:isolate';
import 'dart:async';
import 'package:ffi/ffi.dart';
import 'package:event_bus/event_bus.dart';
import 'package:zzcc/core/services/logger_service.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/data/models/torrent_model.dart';
import 'package:base32/base32.dart';

// 全局变量用于存储发送端口
// late final ReceivePort _receivePort;
// late final StreamSubscription _progressSubscription;
final Map<int, String> _cachedInfoHashes = {};

// 进度更新消息类型
class ProgressUpdate {
  final String infoHash;
  final int progress;
  
  ProgressUpdate(this.infoHash, this.progress);
}

// 定义回调函数类型（移到类外部）
typedef ProgressCallbackNative = Void Function(
  Pointer<Utf8> infoHash,
  Int32 progress,
  Int64 downloadRate,
  Int64 uploadRate,
  Int64 totalDownloaded,
  Int64 totalUploaded,
  Int64 totalSize,
  Int32 peers,
  Int32 seeds,
);
typedef ProgressCallbackDart = void Function(
  Pointer<Utf8> infoHash,
  int progress,
  int downloadRate,
  int uploadRate,
  int totalDownloaded,
  int totalUploaded,
  int totalSize,
  int peers,
  int seeds,
);

abstract class TorrentService {
  Future<void> initialize();
  Future<String> startDownload(String magnetUrl, String savePath);
  Future<void> pauseDownload(String taskId, {String? infoHash});
  Future<void> resumeDownload(String taskId, {String? infoHash});
  // optional infoHash can be provided if the service doesn't have mapping (e.g. after restart)
  Future<void> cancelDownload(String taskId, {String? infoHash});
  Future<void> removeTorrentKeepFiles(String taskId, {String? infoHash});
  Future<double> getDownloadProgress(String taskId);
  // Expose progress stream so UI/providers can subscribe to status updates
  Stream<TorrentStatusUpdateEvent> get progressStream;
  // Lookup taskId by infoHash (may return null if not known)
  String? getTaskIdForInfoHash(String infoHash);
  // Register a mapping from taskId to infoHash (useful after restart)
  void registerTaskInfoHash(String taskId, String infoHash);
  void dispose();

  static int lastUpdate = 0;
  
  static void _onProgressUpdate(
    Pointer<Utf8> infoHashPtr,
    int progress,
    int downloadRate,
    int uploadRate,
    int totalDownloaded,
    int totalUploaded,
    int totalSize,
    int peers,
    int seeds,
  ) {
    try {
      // 添加帧时间同步保护
      if (!Platform.isWindows) return;
      
      final now = DateTime.now().millisecondsSinceEpoch;
      const minInterval = 100; // 最小10FPS更新间隔(ms)

      // 使用类级静态变量替代方法内静态变量
      if (now - TorrentService.lastUpdate < minInterval) return;
      TorrentService.lastUpdate = now;

      final eventBus = getIt<EventBus>();
      if (infoHashPtr == nullptr || infoHashPtr.address == 0) {
        getIt<LoggerService>().error('Null infoHashPtr in progress callback');
        return;
      }
      
      // 修复：使用Utf8.fromUtf8安全转换字符串
      final infoHash = infoHashPtr.toDartString();
      getIt<LoggerService>().info('Received progress update for: $infoHash');
      
      // 修复：添加参数验证
      if (progress < 0 || progress > 100) {
        getIt<LoggerService>().warning('Invalid progress value: $progress');
        progress = progress.clamp(0, 100);
      }

      final instance = getIt<TorrentService>() as TorrentServiceImpl;
      for (final entry in instance._taskIdToInfoHash.entries) {
        if (entry.value == infoHash) {
          instance._progressMap[entry.key] = progress / 100.0;
          break;
        }
      }
      
      final status = TorrentStatus(
        infoHash: infoHash,
        progress: progress,
        downloadRate: downloadRate,
        uploadRate: uploadRate,
        totalDownloaded: totalDownloaded,
        totalUploaded: totalUploaded,
        totalSize: totalSize,
        peers: peers,
        seeds: seeds,
      );

      getIt<LoggerService>().info('Progress callback received: '
        'progress=$progress, '
        'downloadRate=$downloadRate, '
        'uploadRate=$uploadRate, '
        'totalDownloaded=$totalDownloaded, '
        'totalUploaded=$totalUploaded, '
        'totalSize=$totalSize, '
        'peers=$peers, '
        'seeds=$seeds');
      
      // 修复：使用try-catch包装事件发送
      try {
        final event = TorrentStatusUpdateEvent(status);
        eventBus.fire(event);
        // 也将事件发送到服务实例的进度流，供界面直接订阅
        try {
          instance._progressController.add(event);
        } catch (e) {
          getIt<LoggerService>().warning('Failed to add progress event to stream: $e');
        }
      } catch (e, stack) {
        getIt<LoggerService>().error('Error firing event: $e\n$stack');
      }
    } catch (e, stack) {
      getIt<LoggerService>().error('Error in _onProgressUpdate: $e\n$stack');
    }
  }
}

class TorrentServiceImpl implements TorrentService {
  final LoggerService _logger = getIt<LoggerService>();
  late final DynamicLibrary _lib;
  Pointer<Void>? _sessionPtr = nullptr;

  // final ReceivePort _receivePort = ReceivePort();
  // StreamSubscription _progressSubscription = const Stream.empty().listen((_) {});

  final StreamController<TorrentStatusUpdateEvent> _progressController = 
      StreamController<TorrentStatusUpdateEvent>.broadcast();

  @override
  Stream<TorrentStatusUpdateEvent> get progressStream => _progressController.stream;

  @override
  String? getTaskIdForInfoHash(String infoHash) {
    try {
      for (final entry in _taskIdToInfoHash.entries) {
        if (entry.value == infoHash) return entry.key;
      }
    } catch (_) {}
    return null;
  }

  @override
  void registerTaskInfoHash(String taskId, String infoHash) {
    try {
      // Normalize if a magnet link or xt parameter was passed in
      String finalHash = infoHash;
      try {
        if (finalHash.startsWith('magnet:')) {
          final parsed = _extractInfoHashFromMagnet(finalHash);
          if (parsed != null && parsed.isNotEmpty) {
            finalHash = parsed;
          }
        }

        // If still base32 (32 chars), try to convert to hex
        if (finalHash.length == 32) {
          try {
            final bytes = base32.decode(finalHash.toUpperCase());
            finalHash = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
          } catch (_) {}
        }
      } catch (_) {}

      _taskIdToInfoHash[taskId] = finalHash.toLowerCase();
    } catch (e) {
      _logger.warning('Failed to register task infoHash: $e');
    }
  }
  
  // 声明函数
  late final void Function(Pointer<Void>, Pointer<NativeFunction<ProgressCallbackNative>>) _setProgressCallback;
  late final Pointer<Void> Function() _createSession;
  late final int Function(Pointer<Void>, Pointer<Utf8>, Pointer<Utf8>) _addTorrent;
  late final int Function(Pointer<Void>, Pointer<Utf8>, Pointer<Utf8>, Pointer<Utf8>) _addTorrentFile;
  late final int Function(Pointer<Void>, Pointer<Utf8>) _pauseTorrent;
  late final int Function(Pointer<Void>, Pointer<Utf8>) _resumeTorrent;
  late final int Function(Pointer<Void>, Pointer<Utf8>) _cancelTorrent;
  late final int Function(Pointer<Void>, Pointer<Utf8>) _removeTorrentKeep;
  late final void Function(Pointer<Void>) _freeSession;
  
  // 添加进度跟踪
  final Map<String, double> _progressMap = {};
  final Map<String, String> _taskIdToInfoHash = {};

  // static TorrentServiceImpl? _instance;

  TorrentServiceImpl() {
    if (Platform.isWindows) {
      _lib = DynamicLibrary.open('torrent_ffi.dll');
    } else if (Platform.isLinux) {
      _lib = DynamicLibrary.open('torrent_ffi.so');
    } else if (Platform.isMacOS) {
      _lib = DynamicLibrary.open('torrent_ffi.dylib');
    } else {
      _lib = DynamicLibrary.process();
    }
    
    _createSession = _lib.lookupFunction<Pointer<Void> Function(), Pointer<Void> Function()>('create_session');
    _addTorrent = _lib.lookupFunction<Int32 Function(Pointer<Void>, Pointer<Utf8>, Pointer<Utf8>), int Function(Pointer<Void>, Pointer<Utf8>, Pointer<Utf8>)>('add_torrent');
    _addTorrentFile = _lib.lookupFunction<Int32 Function(Pointer<Void>, Pointer<Utf8>, Pointer<Utf8>, Pointer<Utf8>), int Function(Pointer<Void>, Pointer<Utf8>, Pointer<Utf8>, Pointer<Utf8>)>('add_torrent_file');
    _pauseTorrent = _lib.lookupFunction<Int32 Function(Pointer<Void>, Pointer<Utf8>), int Function(Pointer<Void>, Pointer<Utf8>)>('pause_torrent');
    _resumeTorrent = _lib.lookupFunction<Int32 Function(Pointer<Void>, Pointer<Utf8>), int Function(Pointer<Void>, Pointer<Utf8>)>('resume_torrent');
    _cancelTorrent = _lib.lookupFunction<Int32 Function(Pointer<Void>, Pointer<Utf8>), int Function(Pointer<Void>, Pointer<Utf8>)>('cancel_torrent');
    _removeTorrentKeep = _lib.lookupFunction<Int32 Function(Pointer<Void>, Pointer<Utf8>), int Function(Pointer<Void>, Pointer<Utf8>)>('remove_torrent_keep');
    _freeSession = _lib.lookupFunction<Void Function(Pointer<Void>), void Function(Pointer<Void>)>('free_session');
    _setProgressCallback = _lib.lookupFunction<Void Function(Pointer<Void>, Pointer<NativeFunction<ProgressCallbackNative>>), void Function(Pointer<Void>, Pointer<NativeFunction<ProgressCallbackNative>>)>('set_progress_callback');
  }

  @override
  Future<void> initialize() async {
    try {
      _logger.info('Initializing torrent service...');
      
      if (_sessionPtr == nullptr || _sessionPtr!.address == 0) {
        _sessionPtr = _createSession();
        
        if (_sessionPtr == nullptr || _sessionPtr!.address == 0) {
          throw Exception('Failed to get torrent session');
        }
        
        final callback = Pointer.fromFunction<ProgressCallbackNative>(TorrentService._onProgressUpdate);
        _setProgressCallback(_sessionPtr!, callback);
      }
    } catch (e, stack) {
      _logger.error('Torrent initialization failed: $e\n$stack');
      rethrow;
    }
  }

  @override
  Future<String> startDownload(String torrentInput, String savePath) async {
    if (_sessionPtr == nullptr) {
      throw Exception('Torrent session not available');
    }
    
    final taskId = '${DateTime.now().millisecondsSinceEpoch}-${torrentInput.hashCode}';
    String infoHash = '';

    try {
      if (torrentInput.startsWith('magnet:')) {
        final uri = Uri.parse(torrentInput);
        final xtParam = uri.queryParameters['xt'] ?? '';
        
        // 支持多种格式的infoHash解析
        final match = RegExp(r'urn:btih:([0-9a-zA-Z]{32,40})').firstMatch(xtParam);
        if (match != null) {
          final hashStr = match.group(1)!;
          
          if (hashStr.length == 40) {
            infoHash = hashStr.toLowerCase();
          } else if (hashStr.length == 32) {
            // Base32转十六进制
            try {
              final bytes = base32.decode(hashStr.toUpperCase());
              infoHash = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
            } catch (e) {
              _logger.warning('Base32 conversion failed: $e');
              infoHash = 'unknown_$taskId';
            }
          }
        }
        
        // 尝试直接使用磁力链接解析
        if (infoHash.isEmpty) {
          infoHash = _extractInfoHashFromMagnet(torrentInput) ?? 'unknown_$taskId';
        }
      } else {
        infoHash = await _addFileTorrent(torrentInput, savePath);
      }
      
      int result;
      if (torrentInput.startsWith('magnet:')) {
        result = await _addMagnetTorrent(torrentInput, savePath);
      } else {
        result = 0;
      }
      
      if (result != 0) {
        throw Exception('Failed to start download (error code: $result)');
      }
      
      // 仅在添加成功后记录映射关系（尽量规范为hex）
      try {
        final normalized = _normalizeInfoHash(infoHash) ?? infoHash;
        _taskIdToInfoHash[taskId] = normalized.toLowerCase();
      } catch (_) {
        _taskIdToInfoHash[taskId] = infoHash;
      }
      _progressMap[taskId] = 0.0;
      
      return taskId;
    } catch (e, stack) {
      _logger.error('Failed to start torrent download: $e\n$stack');
      rethrow;
    }
  }

  /// Normalize various infoHash representations to a 40-char hex string when possible.
  /// Accepts raw hex, magnet links, or base32 strings. Returns null if normalization fails.
  String? _normalizeInfoHash(String? input) {
    if (input == null || input.isEmpty) return null;
    String candidate = input;
    try {
      if (candidate.startsWith('magnet:')) {
        final parsed = _extractInfoHashFromMagnet(candidate);
        if (parsed != null && parsed.isNotEmpty) candidate = parsed;
      }

      // If looks like base32 (32 chars), try to decode to hex
      if (candidate.length == 32) {
        try {
          final bytes = base32.decode(candidate.toUpperCase());
          candidate = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
        } catch (e) {
          // decoding failed
          return null;
        }
      }

      // Validate 40-char hex (optionally allow a trailing null char)
      final hexRegex = RegExp(r'^[0-9a-fA-F]{40}\x00?$');
      if (hexRegex.hasMatch(candidate)) {
        return candidate.toLowerCase();
      }
    } catch (e) {
      _logger.warning('InfoHash normalization failed for input: $input - $e');
    }
    return null;
  }

  String? _extractInfoHashFromMagnet(String magnet) {
    try {
      final params = magnet.split('?').last.split('&');
      for (final param in params) {
        if (param.startsWith('xt=urn:btih:')) {
          return param.substring(12);
        }
      }
    } catch (e) {
      _logger.warning('Magnet URI parsing error: $e');
    }
    return null;
  }

  Future<int> _addMagnetTorrent(String magnet, String savePath) async {
    final sessionPtr = _sessionPtr!;
    final magnetPtr = magnet.toNativeUtf8();
    final savePathPtr = savePath.toNativeUtf8();
    
    try {
      return _addTorrent(sessionPtr, magnetPtr, savePathPtr);
    } finally {
      malloc.free(magnetPtr);
      malloc.free(savePathPtr);
    }
  }

  Future<String> _addFileTorrent(String filePath, String savePath) async {
    try {
      final normalizedPath = filePath.replaceAll('/', '\\');
      _logger.info('Adding torrent file: $normalizedPath');
      
      // 使用Uint8分配内存，然后转换为Utf8指针
      final infoHashPtr = calloc<Uint8>(41).cast<Utf8>();
      
      final result = _addTorrentFile(
        _sessionPtr!, 
        normalizedPath.toNativeUtf8(), 
        savePath.toNativeUtf8(),
        infoHashPtr
      );
      
      if (result != 0) {
        calloc.free(infoHashPtr.cast<Uint8>());
        throw Exception('添加种子文件失败 (错误代码: $result)');
      }
      
      final infoHash = infoHashPtr.toDartString();
      calloc.free(infoHashPtr.cast<Uint8>());
      
      return infoHash;
    } catch (e, stack) {
      _logger.error('File torrent addition failed: $e\n$stack');
      rethrow;
    }
  }

  @override
  Future<double> getDownloadProgress(String taskId) async {
    // 返回缓存的进度值
    return _progressMap[taskId] ?? 0.0;
  }

  @override
  Future<void> pauseDownload(String taskId, {String? infoHash}) async {
    try {
      String? hash = infoHash ?? _taskIdToInfoHash[taskId];
      hash = _normalizeInfoHash(hash) ?? hash;
      if (hash == null) {
        throw Exception('InfoHash not found for task $taskId');
      }

      // Ensure mapping cached for later resume/cancel
      _taskIdToInfoHash[taskId] = hash;

      final infoHashPtr = hash.toNativeUtf8();
      final result = _pauseTorrent(_sessionPtr!, infoHashPtr);
      malloc.free(infoHashPtr);
      
      if (result != 0) {
        throw Exception('Failed to pause download (error code: $result)');
      }
    } catch (e) {
      _logger.error('Failed to pause download: $e');
      rethrow;
    }
  }

  @override
  Future<void> resumeDownload(String taskId, {String? infoHash}) async {
    try {
      String? hash = infoHash ?? _taskIdToInfoHash[taskId];
      hash = _normalizeInfoHash(hash) ?? hash;
      if (hash == null) {
        throw Exception('InfoHash not found for task $taskId');
      }

      _taskIdToInfoHash[taskId] = hash;

      final infoHashPtr = hash.toNativeUtf8();
      final result = _resumeTorrent(_sessionPtr!, infoHashPtr);
      malloc.free(infoHashPtr);
      
      if (result != 0) {
        throw Exception('Failed to resume download (error code: $result)');
      }
    } catch (e) {
      _logger.error('Failed to resume download: $e');
      rethrow;
    }
  }

  @override
  Future<void> cancelDownload(String taskId, {String? infoHash}) async {
    try {
      final raw = infoHash ?? _taskIdToInfoHash[taskId];
      final finalInfoHash = _normalizeInfoHash(raw);

      if (finalInfoHash == null) {
        final msg = 'Invalid or missing infoHash for task $taskId (raw: $raw)';
        _logger.error(msg);
        throw Exception(msg);
      }

      _logger.info('Cancelling torrent for task $taskId with infoHash $finalInfoHash');
      final infoHashPtr = finalInfoHash.toNativeUtf8();
      final result = _cancelTorrent(_sessionPtr!, infoHashPtr);
      malloc.free(infoHashPtr);

      if (result != 0) {
        throw Exception('Failed to cancel download (error code: $result, infoHash: $finalInfoHash)');
      }

      // 清理映射关系
      _progressMap.remove(taskId);
      _taskIdToInfoHash.remove(taskId);
    } catch (e) {
      _logger.error('Failed to cancel download: $e');
      rethrow;
    }
  }

  @override
  Future<void> removeTorrentKeepFiles(String taskId, {String? infoHash}) async {
    try {
      final raw = infoHash ?? _taskIdToInfoHash[taskId];
      final finalInfoHash = _normalizeInfoHash(raw);

      if (finalInfoHash == null) {
        final msg = 'Invalid or missing infoHash for task $taskId (raw: $raw)';
        _logger.error(msg);
        throw Exception(msg);
      }

      _logger.info('Removing torrent (keep files) for task $taskId with infoHash $finalInfoHash');
      final infoHashPtr = finalInfoHash.toNativeUtf8();
      final result = _removeTorrentKeep(_sessionPtr!, infoHashPtr);
      malloc.free(infoHashPtr);

      if (result != 0) {
        throw Exception('Failed to remove torrent (keep files) (error code: $result, infoHash: $finalInfoHash)');
      }

      // Remove mapping; we are no longer tracking this task
      _progressMap.remove(taskId);
      _taskIdToInfoHash.remove(taskId);
    } catch (e) {
      _logger.error('Failed to remove torrent (keep files): $e');
      rethrow;
    }
  }

  @override
  void dispose() {
    _clearProgressCallback();
    _progressController.close();  // 添加流控制器关闭

    final sessionPtr = _sessionPtr;
    if (sessionPtr != nullptr) {
      _freeSession(sessionPtr!);
      _sessionPtr = nullptr;
      
      // 清除缓存
      _cachedInfoHashes.clear();
      _progressMap.clear();
    }
  }

  void _clearProgressCallback() {
    try {
      final clearCallback = _lib.lookupFunction<Void Function(), void Function()>('clear_progress_callback');
      clearCallback();
    } catch (e) {
      _logger.warning('Failed to clear progress callback: $e');
    }
  }

  Future<String> addTorrent({
    required String torrentPath,
    required String savePath,
    String? incompletePath,
    bool startImmediately = true,
    List<String>? selectedFileIds,
    String? category,
    List<String>? tags,
    String? stopCondition,
    bool addToTopOfQueue = false,
    bool skipHashCheck = false,
    bool downloadInOrder = false,
    bool downloadFirstLastPieces = false,
    String? contentLayout,
    bool isManualMode = false,
  }) async {
    // 实现添加torrent的逻辑
    // 返回任务ID
    return await startDownload(torrentPath, savePath);
  }
}