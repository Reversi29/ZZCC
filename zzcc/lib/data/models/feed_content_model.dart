// lib/data/models/feed_content_model.dart
//
// 广场内容统一数据模型。
// 覆盖推荐/视频/音频三类内容的公共字段 + 类型特有字段。

/// 内容类型。
enum FeedContentType { recommend, video, audio, article, app, project, live }

extension FeedContentTypeX on FeedContentType {
  String get label {
    switch (this) {
      case FeedContentType.recommend:
        return '推荐';
      case FeedContentType.video:
        return '视频';
      case FeedContentType.audio:
        return '音频';
      case FeedContentType.article:
        return '图文';
      case FeedContentType.app:
        return '应用';
      case FeedContentType.project:
        return '项目';
      case FeedContentType.live:
        return '直播';
    }
  }
}

/// 一条广场内容。
class FeedContent {
  final String id;
  final FeedContentType type;

  // 公共字段
  final String title;
  final String description;
  final String author;
  final String authorAvatar;
  final String coverImage;
  final int likes;
  final int comments;
  final int shares;
  final int views;
  final String? durationText;
  final DateTime createdAt;
  final List<String> tags;

  // 视频特有
  final String? videoUrl;

  // 音频特有
  final String? audioUrl;
  final String? audioWaveform; // 可选：波形数据（base64 或 JSON）

  // 应用特有
  final String? appIcon;
  final String? appCategory; // 应用分类
  final String? appVersion; // 应用版本
  final int? appDownloads; // 下载量
  final String? packageName; // 包名

  // 直播特有
  final String? liveStatus; // 直播状态（live/ended）
  final int? liveViewers; // 在线观看人数

  const FeedContent({
    required this.id,
    required this.type,
    required this.title,
    required this.description,
    required this.author,
    required this.authorAvatar,
    required this.coverImage,
    this.likes = 0,
    this.comments = 0,
    this.shares = 0,
    this.views = 0,
    this.durationText,
    required this.createdAt,
    this.tags = const [],
    this.videoUrl,
    this.audioUrl,
    this.audioWaveform,
    this.appIcon,
    this.appCategory,
    this.appVersion,
    this.appDownloads,
    this.packageName,
    this.liveStatus,
    this.liveViewers,
  });
}
