// lib/core/services/torrent_service_web.dart
//
// Web stub — FFI is not available on web platform.

import 'package:zzcc/core/services/logger_service.dart';

abstract class TorrentProgress {
  String get infoHash;
  int get progress;
  int get downloadRate;
  int get uploadRate;
  int get totalDownloaded;
  int get totalUploaded;
  int get totalSize;
  int get peers;
  int get seeds;
}

abstract class TorrentService {
  /// 初始化（web 上为空操作）
  Future<void> init();

  /// 添加种子（web 上返回 -1）
  Future<int> addTorrent(String torrentPath, String downloadPath);

  /// 暂停（web 上为空）
  Future<void> pauseTorrent(String infoHash);

  /// 恢复（web 上为空）
  Future<void> resumeTorrent(String infoHash);

  /// 取消并删除（web 上为空）
  Future<void> cancelTorrent(String infoHash);

  /// 获取进度（web 上返回空 map）
  Map<String, TorrentProgress> getProgress();

  /// 销毁（web 上为空）
  Future<void> dispose();
}
