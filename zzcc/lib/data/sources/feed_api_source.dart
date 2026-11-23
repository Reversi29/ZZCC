// lib/data/sources/feed_api_source.dart
//
// 广场内容真实后端数据源。
// 对接 services/interface/routers/feed.py（/api/v1/feed/*）。
// 后端返回 snake_case JSON，此处解析为前端 FeedContent（camelCase）。
//
// 替换 MockFeedRemoteSource 后视图层无需改动。

import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:logging/logging.dart';

import '../models/feed_content_model.dart';
import 'feed_remote_source.dart';
import '../../core/services/config_service.dart';
import '../../core/di/service_locator.dart';

/// 真实后端数据源。
class FeedApiSource implements FeedRemoteSource {
  final Dio _dio;
  final Logger _log = Logger('FeedApi');

  FeedApiSource({Dio? dio, ConfigService? config})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: config?.nebulaApiBaseUrl ??
                  getIt<ConfigService>().nebulaApiBaseUrl,
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 15),
              headers: {
                'Content-Type': 'application/json',
                'X-API-Key': config?.nebulaApiKey ??
                    getIt<ConfigService>().nebulaApiKey,
              },
            ));

  @override
  Future<List<FeedContent>> fetchByType(FeedContentType type,
      {String? sort}) async {
    final typeStr = type.name; // recommend/video/audio/article/app/project/live
    final query = <String, dynamic>{'page': 1, 'page_size': 50};
    if (sort != null) query['sort'] = sort;
    try {
      _log.info('fetchByType: GET /feed/$typeStr baseUrl=${_dio.options.baseUrl}');
      final resp = await _dio.get(
        '/feed/$typeStr',
        queryParameters: query,
      );
      final data = resp.data;
      if (data is! Map<String, dynamic>) {
        throw FeedApiException('响应格式错误: ${data.runtimeType}');
      }
      if (data['ok'] != true) {
        _log.warning('fetchByType: ok!=true detail=${data['detail']}');
        throw FeedApiException('服务端返回错误: ${data['detail']}');
      }
      final items = data['items'];
      if (items is! List) return const [];
      return items
          .whereType<Map<String, dynamic>>()
          .map(_fromJson)
          .toList();
    } on DioException catch (e) {
      _log.warning('fetchByType DioException: ${e.message} uri=${e.requestOptions.uri}');
      rethrow;
    }
  }

  /// 点赞/评论/分享。返回 {added, count}。
  @override
  Future<Map<String, dynamic>> interact(String contentId, String kind,
      {String? userId, String? payload}) async {
    try {
      final resp = await _dio.post(
        '/feed/$contentId/interact',
        data: {
          'kind': kind,
          'user_id': userId ?? 'anonymous',
          if (payload != null) 'payload': payload,
        },
      );
      final data = resp.data;
      if (data is! Map<String, dynamic>) {
        throw FeedApiException('响应格式错误: ${data.runtimeType}');
      }
      return data;
    } on DioException catch (e) {
      _log.warning('interact DioException: ${e.message}');
      rethrow;
    }
  }

  /// 观看数上报（播放埋点）。返回 {ok, content_id, views}。
  @override
  Future<Map<String, dynamic>> reportView(String contentId) async {
    try {
      final resp = await _dio.post('/feed/view/$contentId/report');
      final data = resp.data;
      if (data is! Map<String, dynamic>) {
        throw FeedApiException('响应格式错误: ${data.runtimeType}');
      }
      return data;
    } on DioException catch (e) {
      // 埋点失败不阻断播放体验，仅记录。
      _log.warning('reportView DioException: ${e.message}');
      return <String, dynamic>{'ok': false};
    }
  }

  /// 应用安装计数。返回 {added, count}。
  @override
  Future<Map<String, dynamic>> install(String contentId,
      {String? userId, String? packageName}) async {
    try {
      final resp = await _dio.post(
        '/feed/$contentId/install',
        data: {
          'user_id': userId ?? 'anonymous',
          if (packageName != null) 'package_name': packageName,
        },
      );
      final data = resp.data;
      if (data is! Map<String, dynamic>) {
        throw FeedApiException('响应格式错误: ${data.runtimeType}');
      }
      return data;
    } on DioException catch (e) {
      _log.warning('install DioException: ${e.message}');
      rethrow;
    }
  }

  /// 后端 snake_case → 前端 FeedContent。
  FeedContent _fromJson(Map<String, dynamic> j) {
    final typeStr = (j['type'] as String?) ?? 'recommend';
    final type = _parseType(typeStr);
    return FeedContent(
      id: (j['id'] as String?) ?? (j['content_id'] as String? ?? ''),
      type: type,
      title: (j['title'] as String?) ?? '',
      description: (j['description'] as String?) ?? '',
      author: (j['author'] as String?) ?? '',
      authorAvatar: (j['author_avatar'] as String?) ?? '',
      coverImage: (j['cover_image'] as String?) ?? '',
      likes: (j['likes'] as num?)?.toInt() ?? 0,
      comments: (j['comments'] as num?)?.toInt() ?? 0,
      shares: (j['shares'] as num?)?.toInt() ?? 0,
      views: (j['views'] as num?)?.toInt() ?? 0,
      durationText: j['duration_text'] as String?,
      createdAt:
          DateTime.tryParse((j['created_at'] as String?) ?? '') ??
              DateTime.now(),
      tags: _parseTags(j['tags']),
      videoUrl: j['video_url'] as String?,
      audioUrl: j['audio_url'] as String?,
      audioWaveform: j['audio_waveform'] as String?,
      appIcon: j['app_icon'] as String?,
      appCategory: j['app_category'] as String?,
      appVersion: j['app_version'] as String?,
      appDownloads: (j['app_downloads'] as num?)?.toInt(),
      packageName: j['package_name'] as String?,
      liveStatus: (j['is_live'] == true) ? 'live' : 'ended',
      liveViewers: (j['viewer_count'] as num?)?.toInt(),
    );
  }

  FeedContentType _parseType(String s) {
    switch (s) {
      case 'video':
        return FeedContentType.video;
      case 'audio':
        return FeedContentType.audio;
      case 'article':
        return FeedContentType.article;
      case 'app':
        return FeedContentType.app;
      case 'project':
        return FeedContentType.project;
      case 'live':
        return FeedContentType.live;
      case 'recommend':
      default:
        return FeedContentType.recommend;
    }
  }

  List<String> _parseTags(dynamic raw) {
    if (raw is List) {
      return raw.whereType<String>().toList();
    }
    if (raw is String && raw.isNotEmpty) {
      try {
        final decoded = jsonDecode(raw);
        if (decoded is List) {
          return decoded.whereType<String>().toList();
        }
      } catch (_) {
        return raw
            .split(',')
            .map((e) => e.trim())
            .where((e) => e.isNotEmpty)
            .toList();
      }
    }
    return const [];
  }
}

class FeedApiException implements Exception {
  final String message;
  FeedApiException(this.message);
  @override
  String toString() => 'FeedApiException: $message';
}
