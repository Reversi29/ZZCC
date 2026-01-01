import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/data/models/torrent_model.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/core/services/torrent_metadata_service.dart';
import 'package:zzcc/core/services/torrent_service.dart';
import 'package:zzcc/core/services/logger_service.dart';

class DownloadState {
  final String? savePath;
  final String? incompletePath;
  final List<TorrentInfo> torrents;

  const DownloadState({
    this.savePath,
    this.incompletePath,
    required this.torrents,
  });

  DownloadState copyWith({
    String? savePath,
    String? incompletePath,
    List<TorrentInfo>? torrents,
  }) {
    return DownloadState(
      savePath: savePath ?? this.savePath,
      incompletePath: incompletePath ?? this.incompletePath,
      torrents: torrents ?? this.torrents,
    );
  }
}

class DownloadProvider extends StateNotifier<DownloadState> {
  DownloadProvider() : super(const DownloadState(torrents: [])) {
    _storage = getIt<StorageService>();
    _loadSavedTorrents();
    // Subscribe to torrent progress events from the native service
    try {
      final service = getIt<TorrentService>();
      service.progressStream.listen((event) async {
        try {
          final infoHash = event.status.infoHash;
          final taskId = service.getTaskIdForInfoHash(infoHash);
          if (taskId == null) return;

          final progress = (event.status.progress / 100.0).clamp(0.0, 1.0);
          final downloadRate = event.status.downloadRate; // bytes/sec
          final uploadRate = event.status.uploadRate; // bytes/sec
          final totalDownloaded = event.status.totalDownloaded;
          final totalSize = event.status.totalSize;

          String downloadRateText = _formatBytesPerSec(downloadRate);
          String uploadRateText = _formatBytesPerSec(uploadRate);

          String? remaining;
          if (downloadRate > 0 && totalSize > 0 && totalDownloaded <= totalSize) {
            final secs = (totalSize - totalDownloaded) ~/ (downloadRate > 0 ? downloadRate : 1);
            remaining = _formatDurationSeconds(secs);
          }

          // Update the torrent entry
          state = state.copyWith(
            torrents: state.torrents.map((t) {
              if (t.id == taskId) {
                String statusText = t.status ?? (t.isPaused == true ? '已暂停' : '下载中');
                // If no data exchange and not paused, mark as waiting
                if ((downloadRate == 0 && uploadRate == 0) && !(t.isPaused ?? false) && (t.progress ?? 0) == 0) {
                  statusText = '等待中';
                }

                final updated = t.copyWith(
                  progress: progress,
                  downloadedSize: _formatBytes(totalDownloaded),
                  downloadRate: downloadRateText,
                  uploadSpeed: uploadRateText,
                  remainingTime: remaining,
                  status: statusText,
                  peers: event.status.peers,
                  seeds: event.status.seeds,
                );
                try { _storage.updateTorrentTask(taskId, updated.toMap()); } catch (_) {}
                return updated;
              }
              return t;
            }).toList(),
          );
        } catch (_) {}
      });
    } catch (_) {}
  }
  late final StorageService _storage;
  
  // 存储活动下载任务的 ID
  final Set<String> _activeTorrents = {};

  void setSavePath(String? path) {
    state = state.copyWith(savePath: path);
  }

  void addTorrent(TorrentInfo torrent) {
    state = state.copyWith(
      torrents: [...state.torrents, torrent],
    );
    _activeTorrents.add(torrent.id);
    // 持久化
    try {
      _storage.saveTorrentTask(torrent);
    } catch (_) {}
  }
  
  void removeTorrent(String id) {
    _activeTorrents.remove(id);
    state = state.copyWith(
      torrents: state.torrents.where((t) => t.id != id).toList(),
    );
    try {
      _storage.deleteTorrentTask(id);
    } catch (_) {}
  }

  /// Remove torrent and optionally delete downloaded files.
  Future<void> removeTorrentWithFiles(String id, {required bool deleteFiles}) async {
    try {
      final service = getIt<TorrentService>();
      // Try to supply infoHash when possible (helps after app restart)
      String? infoHashArg;
      final idx = state.torrents.indexWhere((t) => t.id == id);
      if (idx != -1) {
        final torrent = state.torrents[idx];
        if (torrent.magnetUrl != null && torrent.magnetUrl!.startsWith('magnet:')) {
          infoHashArg = torrent.magnetUrl!; // service will extract underlying hash if needed
        }
      }

      if (deleteFiles) {
        try {
          await service.cancelDownload(id, infoHash: infoHashArg);
        } catch (_) {}
      } else {
        try {
          await service.removeTorrentKeepFiles(id, infoHash: infoHashArg);
        } catch (_) {}
      }
    } catch (_) {}

    _activeTorrents.remove(id);
    state = state.copyWith(
      torrents: state.torrents.where((t) => t.id != id).toList(),
    );
    try {
      _storage.deleteTorrentTask(id);
    } catch (_) {}
  }

  void updateTorrentProgress(String id, double progress, String downloadedSize) {
    // 只更新活动的下载任务
    if (id.isEmpty || progress < 0 || progress > 1) return;
    if (_activeTorrents.contains(id)) {
      state = state.copyWith(
        torrents: state.torrents.map((t) {
          if (t.id == id) {
            final updated = t.copyWith(progress: progress, downloadedSize: downloadedSize);
            try { _storage.updateTorrentTask(id, updated.toMap()); } catch (_) {}
            return updated;
          }
          return t;
        }).toList(),
      );
    }
  }
  
  void cancelAllTasks() {
    _activeTorrents.clear();
  }

  void pauseTorrent(String id) {
    _pauseOrResume(id, pause: true);
  }

  void resumeTorrent(String id) {
    _pauseOrResume(id, pause: false);
  }

  Future<void> _pauseOrResume(String id, {required bool pause}) async {
    state = state.copyWith(
      torrents: state.torrents.map((t) {
        if (t.id == id) {
          final updated = t.copyWith(isPaused: pause);
          try { _storage.updateTorrentTask(id, updated.toMap()); } catch (_) {}
          return updated;
        }
        return t;
      }).toList(),
    );

    try {
      final service = getIt<TorrentService>();
      final torrent = state.torrents.firstWhere((t) => t.id == id, orElse: () => throw Exception('Torrent not found'));
      final infoHash = await _ensureInfoHash(id, torrent);
      if (infoHash == null) {
        throw Exception('InfoHash unavailable for task $id');
      }
      if (pause) {
        await service.pauseDownload(id, infoHash: infoHash);
      } else {
        await service.resumeDownload(id, infoHash: infoHash);
      }
    } catch (e) {
      // Log but keep state updated; consider surfacing to UI if needed
      try {
        getIt<LoggerService>().error('Failed to ${pause ? 'pause' : 'resume'} download $id: $e');
      } catch (_) {}
    }
  }

  Future<String?> _ensureInfoHash(String id, TorrentInfo torrent) async {
    final service = getIt<TorrentService>();
    // Try to derive from magnet or torrent path
    final magnet = torrent.magnetUrl;
    String? derived;
    if (magnet != null && magnet.isNotEmpty) {
      derived = _extractInfoHashFromMagnet(magnet);
      // If path to .torrent file, try to compute hash
      if ((derived == null || derived.isEmpty) && magnet.toLowerCase().endsWith('.torrent')) {
        try {
          final meta = getIt<TorrentMetadataService>();
          derived = await meta.computeInfoHashFromFile(magnet);
        } catch (_) {}
      }
    }

    if (derived != null && derived.isNotEmpty) {
      try { service.registerTaskInfoHash(id, derived); } catch (_) {}
      return derived;
    }
    return null;
  }

  String? _extractInfoHashFromMagnet(String magnet) {
    try {
      final params = magnet.split('?').last.split('&');
      for (final p in params) {
        if (p.startsWith('xt=urn:btih:')) {
          return p.substring(12);
        }
      }
    } catch (_) {}
    return null;
  }

  Future<void> setIncompletePath(String path) async {
    state = state.copyWith(incompletePath: path);
    // 如果需要持久化存储
    // await _storageService.saveIncompletePath(path);
  }

  Future<void> addTorrentWithDetails({
    required String taskId,
    required String torrentPath,
    required String savePath,
    required bool startImmediately,
    // 其他参数...
    int? selectedTotalBytes,
    String? selectedSizeReadable,
  }) async {
    String displayName = torrentPath.split('/').last;
    String totalSize = '0 B';

    try {
      // If it's a torrent file path, try to parse metadata for a better display name
      final metadataService = getIt<TorrentMetadataService>();
      if (torrentPath.toLowerCase().endsWith('.torrent')) {
        try {
          final meta = await metadataService.parseTorrentFile(torrentPath);
          if (meta.containsKey('name')) {
            displayName = meta['name'] as String;
          } else if (meta.containsKey('files')) {
            final files = meta['files'] as List<dynamic>;
            if (files.isNotEmpty) {
              displayName = (files.first['name'] as String).split('/').last;
            }
          }
          if (meta.containsKey('length')) {
            final len = meta['length'] as int;
            totalSize = len > 0 ? _formatBytes(len) : totalSize;
          }
        } catch (_) {
          // ignore metadata parse errors and fall back to path name
        }
      } else if (torrentPath.startsWith('magnet:')) {
        try {
          final meta = await metadataService.parseMagnetLink(torrentPath);
          if (meta.containsKey('name')) {
            displayName = meta['name'] as String;
          }
        } catch (_) {}
      }
    } catch (_) {}

    final torrentInfo = TorrentInfo(
      id: taskId,
      name: displayName,
      magnetUrl: torrentPath,
      savePath: savePath,
      progress: 0.0,
      totalSize: totalSize,
      downloadedSize: '0 B',
      peers: 0,
      seeds: 0,
      isPaused: !startImmediately,
      selectedSize: selectedSizeReadable ?? (selectedTotalBytes != null ? _formatBytes(selectedTotalBytes) : null),
    );
    
    state = state.copyWith(
      torrents: [...state.torrents, torrentInfo]
    );
    try { await _storage.saveTorrentTask(torrentInfo); } catch (_) {}
  }

  String _formatBytes(int bytes) {
    const suffixes = ['B', 'KB', 'MB', 'GB', 'TB'];
    double size = bytes.toDouble();
    int i = 0;
    while (size >= 1024 && i < suffixes.length - 1) {
      size /= 1024;
      i++;
    }
    return '${size.toStringAsFixed(i == 0 ? 0 : 2)} ${suffixes[i]}';
  }

  String _formatBytesPerSec(int bytesPerSec) {
    if (bytesPerSec <= 0) return '-';
    const suffixes = ['B/s', 'KB/s', 'MB/s', 'GB/s', 'TB/s'];
    double size = bytesPerSec.toDouble();
    int i = 0;
    while (size >= 1024 && i < suffixes.length - 1) {
      size /= 1024;
      i++;
    }
    return '${size.toStringAsFixed(i == 0 ? 0 : 2)} ${suffixes[i]}';
  }

  String _formatDurationSeconds(int seconds) {
    if (seconds < 60) return '${seconds}s';
    final h = seconds ~/ 3600;
    final m = (seconds % 3600) ~/ 60;
    final s = seconds % 60;
    if (h > 0) return '${h}h ${m}m';
    if (m > 0) return '${m}m ${s}s';
    return '${s}s';
  }

  Future<void> _loadSavedTorrents() async {
    try {
      final list = await _storage.getAllTorrentTasks();
      if (list.isNotEmpty) {
        state = state.copyWith(torrents: list);
        _activeTorrents.addAll(list.map((e) => e.id));

        // Register infoHash/magnet mappings in the TorrentService so operations
        // (pause/resume/cancel/remove) work after an app restart. For .torrent
        // files we attempt to compute the info-hash from the file and register
        // that; for magnet links we register the magnet directly.
        try {
          final service = getIt<TorrentService>();
          final metaService = getIt<TorrentMetadataService>();
          for (final t in list) {
            try {
              if (t.magnetUrl != null && t.magnetUrl!.isNotEmpty) {
                final url = t.magnetUrl!;
                if (url.toLowerCase().endsWith('.torrent')) {
                  try {
                    final infoHash = await metaService.computeInfoHashFromFile(url);
                    service.registerTaskInfoHash(t.id, infoHash);
                  } catch (e) {
                    // fallback: register raw path so later attempts can try other strategies
                    service.registerTaskInfoHash(t.id, url);
                  }
                } else {
                  // magnet or other: register directly
                  service.registerTaskInfoHash(t.id, url);
                }
              }
            } catch (_) {}
          }
        } catch (_) {}
      }
    } catch (_) {}
  }
}

final downloadProvider = StateNotifierProvider<DownloadProvider, DownloadState>((ref) {
  return DownloadProvider();
});