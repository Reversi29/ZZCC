// lib/presentation/providers/feed_provider.dart
//
// 广场内容状态管理。
// 按类型缓存内容列表，支持点赞/播放状态本地交互。

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/feed_content_model.dart';
import '../../data/sources/feed_remote_source.dart';
import '../../data/sources/feed_api_source.dart';

/// 广场内容 Provider（全局单例）。
final feedProvider = ChangeNotifierProvider<FeedProvider>((ref) {
  return FeedProvider();
});

/// 广场内容状态。
class FeedProvider extends ChangeNotifier {
  final FeedRemoteSource _source = FeedApiSource();

  final Map<FeedContentType, List<FeedContent>> _cache = {};
  final Map<FeedContentType, bool> _loading = {};
  final Map<FeedContentType, String?> _error = {};

  // 点赞状态（id -> liked）
  final Map<String, bool> _liked = {};
  // 关注状态（author -> followed）
  final Map<String, bool> _followed = {};
  // 安装状态（app id -> installed）
  final Map<String, bool> _installed = {};

  List<FeedContent> contents(FeedContentType type) =>
      _cache[type] ?? const [];

  bool isLoading(FeedContentType type) => _loading[type] ?? false;

  String? error(FeedContentType type) => _error[type];

  bool isLiked(String id) => _liked[id] ?? false;

  bool isFollowed(String author) => _followed[author] ?? false;

  bool isInstalled(String id) => _installed[id] ?? false;

  /// 拉取指定类型内容（已有缓存则直接返回）。
  Future<void> load(FeedContentType type, {bool refresh = false}) async {
    if (!refresh && (_cache[type]?.isNotEmpty ?? false)) return;
    _loading[type] = true;
    _error[type] = null;
    notifyListeners();

    try {
      final items = await _source.fetchByType(type);
      _cache[type] = items;
    } catch (e) {
      _error[type] = e.toString();
    } finally {
      _loading[type] = false;
      notifyListeners();
    }
  }

  /// 切换点赞状态（乐观更新 + 后端写入）。
  Future<void> toggleLike(FeedContent item) async {
    final liked = !(_liked[item.id] ?? false);
    _liked[item.id] = liked;
    // 乐观更新计数
    _updateContent(item.id, likes: item.likes + (liked ? 1 : 0));
    notifyListeners();

    try {
      final r = await _source.interact(item.id, 'like',
          userId: _currentUserId());
      final count = (r['count'] as num?)?.toInt();
      if (count != null) {
        _updateContent(item.id, likes: count);
        notifyListeners();
      }
    } catch (e) {
      // 失败回滚乐观状态
      _liked[item.id] = !liked;
      _updateContent(item.id, likes: item.likes);
      notifyListeners();
    }
  }

  /// 切换关注状态。
  void toggleFollow(String author) {
    _followed[author] = !(_followed[author] ?? false);
    notifyListeners();
  }

  /// 切换安装状态（乐观更新 + 后端写入）。
  Future<void> toggleInstall(FeedContent item) async {
    final installed = !(_installed[item.id] ?? false);
    _installed[item.id] = installed;
    notifyListeners();

    try {
      final r = await _source.install(item.id,
          userId: _currentUserId(), packageName: item.packageName);
      final count = (r['count'] as num?)?.toInt();
      if (count != null) {
        _updateContent(item.id, appDownloads: count);
        notifyListeners();
      }
    } catch (e) {
      _installed[item.id] = !installed;
      notifyListeners();
    }
  }

  /// 发表评论（后端写入 + 计数更新）。
  Future<bool> addComment(FeedContent item, String text,
      {String? userId}) async {
    try {
      final r = await _source.interact(item.id, 'comment',
          userId: userId ?? _currentUserId(), payload: text);
      final count = (r['count'] as num?)?.toInt();
      if (count != null) {
        _updateContent(item.id, comments: count);
        notifyListeners();
      }
      return r['added'] == true;
    } catch (e) {
      return false;
    }
  }

  void _updateContent(String id,
      {int? likes, int? comments, int? appDownloads}) {
    for (final type in _cache.keys) {
      final list = _cache[type];
      if (list == null) continue;
      for (var i = 0; i < list.length; i++) {
        if (list[i].id == id) {
          final updated = list[i].copyWith(
            likes: likes,
            comments: comments,
            appDownloads: appDownloads,
          );
          _cache[type] = List.from(list)..[i] = updated;
          return;
        }
      }
    }
  }

  String _currentUserId() => 'test_agent';
}
