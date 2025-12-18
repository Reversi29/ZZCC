// lib/data/models/torrent_model.dart
class TorrentInfo {
  final String id;
  final String name;
  final String? magnetUrl;
  final String? savePath;
  final double? progress;
  final String? totalSize;
  final String? downloadedSize;
  final int? peers;
  final int? seeds;
  final bool? isPaused;
  final String? uploadRate;
  // Additional fields
  final String? status;
  final String? downloadRate;
  final String? uploadSpeed;
  final String? remainingTime;
  final double? ratio;
  final String? category;
  final List<String>? tags;
  final String? availability;
  final String? selectedSize;

  TorrentInfo({
    required this.id,
    required this.name,
    this.magnetUrl,
    this.savePath,
    this.progress,
    this.totalSize,
    this.downloadedSize,
    this.peers,
    this.seeds,
    this.isPaused,
    this.uploadRate,
    this.status,
    this.downloadRate,
    this.uploadSpeed,
    this.remainingTime,
    this.ratio,
    this.category,
    this.tags,
    this.availability,
    this.selectedSize,
  });

  TorrentInfo copyWith({
    String? id,
    String? name,
    String? magnetUrl,
    String? savePath,
    double? progress,
    String? totalSize,
    String? downloadedSize,
    int? peers,
    int? seeds,
    bool? isPaused,
    String? uploadRate,
    String? status,
    String? downloadRate,
    String? uploadSpeed,
    String? remainingTime,
    double? ratio,
    String? category,
    List<String>? tags,
    String? availability,
    String? selectedSize,
  }) {
    return TorrentInfo(
      id: id ?? this.id,
      name: name ?? this.name,
      magnetUrl: magnetUrl ?? this.magnetUrl,
      savePath: savePath ?? this.savePath,
      progress: progress ?? this.progress,
      totalSize: totalSize ?? this.totalSize,
      downloadedSize: downloadedSize ?? this.downloadedSize,
      peers: peers ?? this.peers,
      seeds: seeds ?? this.seeds,
      isPaused: isPaused ?? this.isPaused,
      uploadRate: uploadRate ?? this.uploadRate,
      status: status ?? this.status,
      downloadRate: downloadRate ?? this.downloadRate,
      uploadSpeed: uploadSpeed ?? this.uploadSpeed,
      remainingTime: remainingTime ?? this.remainingTime,
      ratio: ratio ?? this.ratio,
      category: category ?? this.category,
      tags: tags ?? this.tags,
      availability: availability ?? this.availability,
      selectedSize: selectedSize ?? this.selectedSize,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'name': name,
      'magnetUrl': magnetUrl,
      'savePath': savePath,
      'progress': progress,
      'totalSize': totalSize,
      'downloadedSize': downloadedSize,
      'isPaused': isPaused,
      'status': status,
      'downloadRate': downloadRate,
      'uploadSpeed': uploadSpeed,
      'remainingTime': remainingTime,
      'ratio': ratio,
      'category': category,
      'tags': tags,
      'availability': availability,
      'peers': peers,
      'seeds': seeds,
      'selectedSize': selectedSize,
    };
  }

  factory TorrentInfo.fromMap(Map<String, dynamic> map) {
    return TorrentInfo(
      id: map['id'] as String,
      name: map['name'] as String,
      magnetUrl: map['magnetUrl'] as String?,
      savePath: map['savePath'] as String?,
      progress: map['progress'] is num ? (map['progress'] as num).toDouble() : null,
      totalSize: map['totalSize'] as String?,
      downloadedSize: map['downloadedSize'] as String?,
      isPaused: map['isPaused'] as bool?,
      status: map['status'] as String?,
      downloadRate: map['downloadRate'] as String?,
      uploadSpeed: map['uploadSpeed'] as String?,
      remainingTime: map['remainingTime'] as String?,
      ratio: map['ratio'] is num ? (map['ratio'] as num).toDouble() : null,
      category: map['category'] as String?,
      tags: (map['tags'] as List?)?.cast<String>(),
      availability: map['availability'] as String?,
      peers: map['peers'] is int ? map['peers'] as int : (map['peers'] is num ? (map['peers'] as num).toInt() : 0),
      seeds: map['seeds'] is int ? map['seeds'] as int : (map['seeds'] is num ? (map['seeds'] as num).toInt() : 0),
      selectedSize: map['selectedSize'] as String?,
    );
  }
}

class TorrentStatus {
  final String infoHash;
  final int progress;
  final int downloadRate;
  final int uploadRate;
  final int totalDownloaded;
  final int totalUploaded;
  final int totalSize;
  final int peers;
  final int seeds;

  TorrentStatus({
    required this.infoHash,
    required this.progress,
    required this.downloadRate,
    required this.uploadRate,
    required this.totalDownloaded,
    required this.totalUploaded,
    required this.totalSize,
    required this.peers,
    required this.seeds,
  });
}

class TorrentStatusUpdateEvent {
  final TorrentStatus status;
  
  TorrentStatusUpdateEvent(this.status);
}