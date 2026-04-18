// lib/core/services/torrent_service_stub.dart
//
// Web stub — no FFI, all torrent methods are no-ops.

import 'dart:async';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/services/logger_service.dart';
import 'package:zzcc/data/models/torrent_model.dart';

/// Abstract interface — must match torrent_service_io.dart.
abstract class TorrentService {
  Future<void> initialize();
  Future<String> startDownload(String magnetUrl, String savePath);
  Future<void> pauseDownload(String taskId, {String? infoHash});
  Future<void> resumeDownload(String taskId, {String? infoHash});
  Future<void> cancelDownload(String taskId, {String? infoHash});
  Future<void> removeTorrentKeepFiles(String taskId, {String? infoHash});
  Future<double> getDownloadProgress(String taskId);
  Stream<TorrentStatusUpdateEvent> get progressStream;
  String? getTaskIdForInfoHash(String infoHash);
  void registerTaskInfoHash(String taskId, String infoHash);
  void dispose();

  static int lastUpdate = 0;
}

/// Web stub implementation.
class TorrentServiceImpl implements TorrentService {
  final LoggerService _logger = getIt<LoggerService>();
  final StreamController<TorrentStatusUpdateEvent> _controller =
      StreamController<TorrentStatusUpdateEvent>.broadcast();
  final Map<String, String> _taskIdToInfoHash = {};

  @override
  Future<void> initialize() async {
    _logger.info('TorrentService: web stub initialized (FFI disabled)');
  }

  @override
  Future<String> startDownload(String magnetUrl, String savePath) async {
    _logger.warning('startDownload not available on web: $magnetUrl');
    return '';
  }

  @override
  Future<void> pauseDownload(String taskId, {String? infoHash}) async {}

  @override
  Future<void> resumeDownload(String taskId, {String? infoHash}) async {}

  @override
  Future<void> cancelDownload(String taskId, {String? infoHash}) async {}

  @override
  Future<void> removeTorrentKeepFiles(String taskId, {String? infoHash}) async {}

  @override
  Future<double> getDownloadProgress(String taskId) async => 0.0;

  @override
  Stream<TorrentStatusUpdateEvent> get progressStream => _controller.stream;

  @override
  String? getTaskIdForInfoHash(String infoHash) {
    for (final entry in _taskIdToInfoHash.entries) {
      if (entry.value == infoHash) return entry.key;
    }
    return null;
  }

  @override
  void registerTaskInfoHash(String taskId, String infoHash) {
    _taskIdToInfoHash[taskId] = infoHash;
  }

  @override
  void dispose() {
    _controller.close();
    _logger.info('TorrentService: web stub disposed');
  }
}
