// lib/presentation/pages/shared/widgets/torrent_progress_view.dart
import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:zzcc/data/models/torrent_model.dart';
import 'package:zzcc/core/services/torrent_service.dart';
import 'package:zzcc/core/di/service_locator.dart';

class TorrentProgressView extends StatefulWidget {
  final String infoHash;
  
  const TorrentProgressView({super.key, required this.infoHash});
  
  @override
  State<TorrentProgressView> createState() => _TorrentProgressViewState();
}

class _TorrentProgressViewState extends State<TorrentProgressView> {
  TorrentStatus? _status;
  StreamSubscription? _subscription;
  
  @override
  void initState() {
    super.initState();
    final torrentService = getIt<TorrentService>();
    if (torrentService is TorrentServiceImpl) {
      _subscription = torrentService.progressStream.listen((event) {
        if (event.status.infoHash == widget.infoHash) {
          setState(() => _status = event.status);
        }
      });
    }
  }
  
  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }
  
  @override
  Widget build(BuildContext context) {
    if (_status == null) {
      return const CircularProgressIndicator();
    }
    
    return Column(
      children: [
        LinearProgressIndicator(value: _status!.progress / 100),
        const SizedBox(height: 8),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('${_formatBytes(_status!.downloadRate)}/s'),
            Text('${_status!.progress}%'),
            Text('${_formatBytes(_status!.totalDownloaded)}/${_formatBytes(_status!.totalSize)}'),
          ],
        ),
      ],
    );
  }
  
  String _formatBytes(int bytes) {
    if (bytes <= 0) return "0 B";
    const suffixes = ["B", "KB", "MB", "GB", "TB"];
    final i = (log(bytes) / log(1024)).floor();
    return '${(bytes / pow(1024, i)).toStringAsFixed(1)} ${suffixes[i]}';
  }
}