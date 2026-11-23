// lib/presentation/pages/square/widgets/feed_audio_view.dart
//
// 音频 tab：音频卡片列表 + 底部播放控制条。
// 借鉴音乐/播客类 App 布局：列表卡片 + 全局播放条（播放/暂停/进度/波形）。

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:cached_network_image/cached_network_image.dart';

import '../../../../data/models/feed_content_model.dart';
import '../../../../presentation/providers/feed_provider.dart';

/// 音频内容列表 + 播放控制。
class FeedAudioView extends ConsumerStatefulWidget {
  const FeedAudioView({super.key});

  @override
  ConsumerState<FeedAudioView> createState() => _FeedAudioViewState();
}

class _FeedAudioViewState extends ConsumerState<FeedAudioView>
    with AutomaticKeepAliveClientMixin {
  final AudioPlayer _player = AudioPlayer();
  final PageController _pageController = PageController();

  FeedContent? _current;
  bool _isPlaying = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  StreamSubscription? _sub;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _sub = _player.onPositionChanged.listen((pos) {
      if (mounted) setState(() => _position = pos);
    });
    _player.onDurationChanged.listen((dur) {
      if (mounted) setState(() => _duration = dur);
    });
    _player.onPlayerComplete.listen((_) {
      if (mounted) setState(() => _isPlaying = false);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(feedProvider.notifier).load(FeedContentType.audio);
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    _player.dispose();
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _togglePlay(FeedContent item) async {
    if (_current?.id == item.id) {
      // 同一首：切换播放/暂停
      if (_isPlaying) {
        await _player.pause();
        if (mounted) setState(() => _isPlaying = false);
      } else {
        await _player.resume();
        if (mounted) setState(() => _isPlaying = true);
        // 播放埋点（会话内去重，resume 不会重复计数）
        ref.read(feedProvider.notifier).reportView(item.id);
      }
      return;
    }
    // 换一首：停止旧的，加载新的
    await _player.stop();
    setState(() {
      _current = item;
      _position = Duration.zero;
      _duration = Duration.zero;
      _isPlaying = false;
    });
    try {
      await _player.play(UrlSource(item.audioUrl!));
      if (mounted) setState(() => _isPlaying = true);
      // 播放埋点：实际起播才计观看数（会话内去重）
      ref.read(feedProvider.notifier).reportView(item.id);
    } catch (e) {
      if (mounted) {
        setState(() => _isPlaying = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('播放失败：$e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final feed = ref.watch(feedProvider);
    final contents = feed.contents(FeedContentType.audio);
    final loading = feed.isLoading(FeedContentType.audio);

    if (loading && contents.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (contents.isEmpty) {
      return const Center(child: Text('暂无音频内容'));
    }

    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: contents.length,
            itemBuilder: (context, index) {
              final item = contents[index];
              final isCurrent = _current?.id == item.id;
              return _AudioCard(
                item: item,
                isCurrent: isCurrent,
                isPlaying: isCurrent && _isPlaying,
                onTap: () => _togglePlay(item),
              );
            },
          ),
        ),
        // 底部播放控制条（有当前播放才显示）
        if (_current != null) _PlayerBar(
          item: _current!,
          isPlaying: _isPlaying,
          position: _position,
          duration: _duration,
          onPlayPause: () => _togglePlay(_current!),
        ),
      ],
    );
  }
}

class _AudioCard extends StatelessWidget {
  final FeedContent item;
  final bool isCurrent;
  final bool isPlaying;
  final VoidCallback onTap;

  const _AudioCard({
    required this.item,
    required this.isCurrent,
    required this.isPlaying,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: isCurrent ? Colors.blue : Colors.grey.shade200,
        ),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(
            children: [
              // 封面 + 播放指示
              Stack(
                alignment: Alignment.center,
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: CachedNetworkImage(
                      imageUrl: item.coverImage,
                      width: 64,
                      height: 64,
                      fit: BoxFit.cover,
                      placeholder: (_, __) => Container(
                        width: 64,
                        height: 64,
                        color: Colors.grey[200],
                      ),
                    ),
                  ),
                  if (isCurrent && isPlaying)
                    Container(
                      width: 64,
                      height: 64,
                      decoration: BoxDecoration(
                        color: Colors.black38,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Icon(Icons.graphic_eq,
                          color: Colors.white, size: 28),
                    ),
                ],
              ),
              const SizedBox(width: 12),
              // 标题/作者/时长
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      item.author,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 13, color: Colors.grey[600]),
                    ),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        Icon(Icons.access_time,
                            size: 12, color: Colors.grey[500]),
                        const SizedBox(width: 4),
                        Text(
                          item.durationText ?? '',
                          style: TextStyle(
                              fontSize: 12, color: Colors.grey[500]),
                        ),
                        const SizedBox(width: 10),
                        Text(
                          '${item.likes} 喜欢',
                          style: TextStyle(
                              fontSize: 12, color: Colors.grey[500]),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              // 播放按钮
              IconButton(
                onPressed: onTap,
                icon: Icon(
                  isCurrent && isPlaying
                      ? Icons.pause_circle_filled
                      : Icons.play_circle_filled,
                  size: 42,
                  color: isCurrent ? Colors.blue : Colors.grey[400],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PlayerBar extends StatelessWidget {
  final FeedContent item;
  final bool isPlaying;
  final Duration position;
  final Duration duration;
  final VoidCallback onPlayPause;

  const _PlayerBar({
    required this.item,
    required this.isPlaying,
    required this.position,
    required this.duration,
    required this.onPlayPause,
  });

  String _fmt(Duration d) {
    final m = d.inMinutes;
    final s = d.inSeconds % 60;
    return '$m:${s.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final total = duration.inMilliseconds > 0 ? duration : null;
    return Container(
      height: 72,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: Colors.white,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.08),
            blurRadius: 8,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: Row(
        children: [
          // 封面
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: CachedNetworkImage(
              imageUrl: item.coverImage,
              width: 44,
              height: 44,
              fit: BoxFit.cover,
            ),
          ),
          const SizedBox(width: 10),
          // 标题 + 进度
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Text(_fmt(position),
                        style: TextStyle(
                            fontSize: 11, color: Colors.grey[500])),
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 6),
                        child: LinearProgressIndicator(
                          value: total != null
                              ? (position.inMilliseconds /
                                      total.inMilliseconds)
                                  .clamp(0.0, 1.0)
                              : 0,
                          minHeight: 3,
                          backgroundColor: Colors.grey[200],
                          valueColor: const AlwaysStoppedAnimation(
                              Colors.blue),
                        ),
                      ),
                    ),
                    Text(_fmt(position + const Duration(minutes: 3)),
                        style: TextStyle(
                            fontSize: 11, color: Colors.grey[500])),
                  ],
                ),
              ],
            ),
          ),
          // 播放/暂停
          IconButton(
            onPressed: onPlayPause,
            icon: Icon(
              isPlaying ? Icons.pause_circle : Icons.play_circle,
              size: 40,
              color: Colors.blue,
            ),
          ),
        ],
      ),
    );
  }
}
