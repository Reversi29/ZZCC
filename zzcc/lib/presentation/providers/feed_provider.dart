// lib/presentation/providers/feed_provider.dart
//
// 广场内容状态管理。
// 按类型缓存内容列表，支持点赞/播放状态本地交互。

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/feed_content_model.dart';
import '../../data/sources/feed_remote_source.dart';

/// 广场内容 Provider（全局单例）。
final feedProvider = ChangeNotifierProvider<FeedProvider>((ref) {
  return FeedProvider();
});

/// 广场内容状态。
class FeedProvider extends ChangeNotifier {
  final FeedRemoteSource _source = MockFeedRemoteSource();

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

  /// 切换点赞状态。
  void toggleLike(FeedContent item) {
    final liked = !(_liked[item.id] ?? false);
    _liked[item.id] = liked;
    notifyListeners();
  }

  /// 切换关注状态。
  void toggleFollow(String author) {
    _followed[author] = !(_followed[author] ?? false);
    notifyListeners();
  }

  /// 切换安装状态。
  void toggleInstall(String id) {
    _installed[id] = !(_installed[id] ?? false);
    notifyListeners();
  }
}
