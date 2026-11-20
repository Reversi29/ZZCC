// lib/presentation/pages/square/widgets/feed_video_view.dart
//
// 视频 tab：抖音式全屏竖屏短视频滑动。
// PageView 垂直翻页，当前页自动播放、离开暂停。
// 借鉴抖音核心交互：全屏视频 + 右侧互动栏 + 底部作者信息。

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:video_player/video_player.dart';

import '../../../../data/models/feed_content_model.dart';
import '../../../../presentation/providers/feed_provider.dart';

/// 全屏竖屏短视频滑动页。
class FeedVideoView extends ConsumerStatefulWidget {
  const FeedVideoView({super.key});

  @override
  ConsumerState<FeedVideoView> createState() => _FeedVideoViewState();
}

class _FeedVideoViewState extends ConsumerState<FeedVideoView>
    with AutomaticKeepAliveClientMixin {
  final PageController _pageController = PageController();
  final List<_VideoPlayerEntry> _players = [];
  int _currentIndex = 0;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(feedProvider.notifier).load(FeedContentType.video);
    });
  }

  @override
  void dispose() {
    _pageController.dispose();
    for (final p in _players) {
      p.controller.dispose();
    }
    super.dispose();
  }

  Future<void> _loadVideo(FeedContent item) async {
    // 已加载则直接播放
    final idx = _players.indexWhere((p) => p.item.id == item.id);
    if (idx >= 0) {
      final p = _players[idx];
      if (!p.initialized) {
        await p.controller.initialize();
        p.initialized = true;
        if (mounted) setState(() {});
      }
      await p.controller.play();
      return;
    }

    final controller = VideoPlayerController.networkUrl(
      Uri.parse(item.videoUrl!),
      videoPlayerOptions: VideoPlayerOptions(
        // Web 自动播放需 muted（浏览器策略）
        mixWithOthers: true,
      ),
    );
    final entry = _VideoPlayerEntry(item: item, controller: controller);
    _players.add(entry);

    try {
      await controller.initialize();
      entry.initialized = true;
      if (mounted) setState(() {});
      await controller.setLooping(true);
      await controller.play();
    } catch (e) {
      entry.error = e.toString();
      if (mounted) setState(() {});
    }
  }

  void _onPageChanged(int index) {
    // 暂停旧视频
    if (_currentIndex < _players.length &&
        _players[_currentIndex].initialized) {
      _players[_currentIndex].controller.pause();
    }
    _currentIndex = index;
    final items = ref.read(feedProvider).contents(FeedContentType.video);
    if (index < items.length) {
      _loadVideo(items[index]);
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final feed = ref.watch(feedProvider);
    final contents = feed.contents(FeedContentType.video);
    final loading = feed.isLoading(FeedContentType.video);

    if (loading && contents.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (contents.isEmpty) {
      return const Center(child: Text('暂无视频内容'));
    }

    return PageView.builder(
      controller: _pageController,
      scrollDirection: Axis.vertical,
      onPageChanged: _onPageChanged,
      itemCount: contents.length,
      itemBuilder: (context, index) {
        final item = contents[index];
        // 预加载相邻视频
        if (index < contents.length - 1) {
          _preload(contents[index + 1]);
        }
        return _VideoPage(
          item: item,
          entry: _players.firstWhere(
            (p) => p.item.id == item.id,
            orElse: () => _VideoPlayerEntry(item: item, controller: VideoPlayerController.networkUrl(Uri.parse(item.videoUrl!))),
          ),
          isActive: index == _currentIndex,
          onLike: () => ref.read(feedProvider.notifier).toggleLike(item),
          isLiked: feed.isLiked(item.id),
          onFollow: () =>
              ref.read(feedProvider.notifier).toggleFollow(item.author),
          isFollowed: feed.isFollowed(item.author),
        );
      },
    );
  }

  void _preload(FeedContent item) {
    if (_players.any((p) => p.item.id == item.id)) return;
    final controller = VideoPlayerController.networkUrl(
      Uri.parse(item.videoUrl!),
    );
    _players.add(_VideoPlayerEntry(item: item, controller: controller));
    controller.initialize().then((_) {
      if (mounted) setState(() {});
    }).catchError((_) {});
  }
}

class _VideoPlayerEntry {
  final FeedContent item;
  final VideoPlayerController controller;
  bool initialized = false;
  String? error;
  _VideoPlayerEntry({required this.item, required this.controller});
}

class _VideoPage extends StatelessWidget {
  final FeedContent item;
  final _VideoPlayerEntry entry;
  final bool isActive;
  final bool isLiked;
  final bool isFollowed;
  final VoidCallback onLike;
  final VoidCallback onFollow;

  const _VideoPage({
    required this.item,
    required this.entry,
    required this.isActive,
    required this.isLiked,
    required this.isFollowed,
    required this.onLike,
    required this.onFollow,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        // 视频画面
        if (entry.initialized)
          Center(
            child: AspectRatio(
              aspectRatio: entry.controller.value.aspectRatio,
              child: VideoPlayer(entry.controller),
            ),
          )
        else if (entry.error != null)
          _VideoError(item: item, error: entry.error!)
        else
          CachedNetworkImage(
            imageUrl: item.coverImage,
            fit: BoxFit.cover,
            placeholder: (_, __) => Container(
              color: Colors.black,
              child: const Center(
                child: CircularProgressIndicator(color: Colors.white),
              ),
            ),
          ),
        // 渐变遮罩（底部）
        Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Colors.black26, Colors.transparent, Colors.black54],
            ),
          ),
        ),
        // 右侧互动栏
        Positioned(
          right: 10,
          bottom: 90,
          child: _VideoActionBar(
            item: item,
            isLiked: isLiked,
            isFollowed: isFollowed,
            onLike: onLike,
            onFollow: onFollow,
          ),
        ),
        // 底部信息
        Positioned(
          left: 14,
          right: 70,
          bottom: 18,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '@${item.author}',
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 15,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                item.title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
              const SizedBox(height: 6),
              if (item.tags.isNotEmpty)
                Text(
                  item.tags.map((t) => '#$t').join(' '),
                  style: const TextStyle(color: Colors.white70, fontSize: 12),
                ),
            ],
          ),
        ),
        // 顶部返回提示
        SafeArea(
          child: Align(
            alignment: Alignment.topCenter,
            child: Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                '上滑查看更多',
                style: TextStyle(color: Colors.white.withValues(alpha: 0.6)),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _VideoActionBar extends StatelessWidget {
  final FeedContent item;
  final bool isLiked;
  final bool isFollowed;
  final VoidCallback onLike;
  final VoidCallback onFollow;

  const _VideoActionBar({
    required this.item,
    required this.isLiked,
    required this.isFollowed,
    required this.onLike,
    required this.onFollow,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // 头像 + 关注
        Column(
          children: [
            CircleAvatar(
              radius: 22,
              backgroundImage: NetworkImage(item.authorAvatar),
              backgroundColor: Colors.grey[300],
            ),
            const SizedBox(height: 6),
            InkWell(
              onTap: onFollow,
              child: Icon(
                isFollowed ? Icons.check : Icons.add_circle,
                color: Colors.red,
                size: 26,
              ),
            ),
          ],
        ),
        const SizedBox(height: 18),
        // 点赞
        _RoundAction(
          icon: isLiked ? Icons.favorite : Icons.favorite_border,
          color: isLiked ? Colors.red : Colors.white,
          label: _formatCount(item.likes + (isLiked ? 1 : 0)),
          onTap: onLike,
        ),
        const SizedBox(height: 16),
        // 评论
        _RoundAction(
          icon: Icons.mode_comment_outlined,
          label: _formatCount(item.comments),
          onTap: () {},
        ),
        const SizedBox(height: 16),
        // 分享
        _RoundAction(
          icon: Icons.share_outlined,
          label: _formatCount(item.shares),
          onTap: () {},
        ),
      ],
    );
  }
}

class _RoundAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color? color;
  const _RoundAction({
    required this.icon,
    required this.label,
    required this.onTap,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(24),
      child: Column(
        children: [
          Icon(icon, color: color ?? Colors.white, size: 32),
          const SizedBox(height: 4),
          Text(
            label,
            style: const TextStyle(color: Colors.white, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _VideoError extends StatelessWidget {
  final FeedContent item;
  final String error;
  const _VideoError({required this.item, required this.error});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.videocam_off, color: Colors.white54, size: 48),
            const SizedBox(height: 12),
            Text(
              '视频加载失败',
              style: TextStyle(color: Colors.white.withValues(alpha: 0.8)),
            ),
            const SizedBox(height: 4),
            Text(
              error,
              style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.4), fontSize: 12),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}

String _formatCount(int n) {
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(1)}w';
  if (n >= 1000) return '${(n / 1000).toStringAsFixed(1)}k';
  return '$n';
}
