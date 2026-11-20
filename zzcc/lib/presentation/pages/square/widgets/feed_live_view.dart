// lib/presentation/pages/square/widgets/feed_live_view.dart
//
// 直播 tab：直播卡片流（封面 + 观看人数徽章 + 直播状态）。
// 借鉴抖音/快手直播广场：横滑卡片网格 + 在线观看人数角标。

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:cached_network_image/cached_network_image.dart';

import '../../../../data/models/feed_content_model.dart';
import '../../../../presentation/providers/feed_provider.dart';

/// 直播广场视图。
class FeedLiveView extends ConsumerStatefulWidget {
  const FeedLiveView({super.key});

  @override
  ConsumerState<FeedLiveView> createState() => _FeedLiveViewState();
}

class _FeedLiveViewState extends ConsumerState<FeedLiveView>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(feedProvider.notifier).load(FeedContentType.live);
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final feed = ref.watch(feedProvider);
    final contents = feed.contents(FeedContentType.live);
    final loading = feed.isLoading(FeedContentType.live);
    final error = feed.error(FeedContentType.live);

    if (loading && contents.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (error != null && contents.isEmpty) {
      return _LiveError(
        message: error,
        onRetry: () =>
            ref.read(feedProvider.notifier).load(FeedContentType.live),
      );
    }
    if (contents.isEmpty) {
      return const Center(child: Text('暂无直播'));
    }

    return RefreshIndicator(
      onRefresh: () => ref
          .read(feedProvider.notifier)
          .load(FeedContentType.live, refresh: true),
      child: GridView.builder(
        padding: const EdgeInsets.all(12),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
          childAspectRatio: 0.72,
        ),
        itemCount: contents.length,
        itemBuilder: (context, index) => _LiveCard(item: contents[index]),
      ),
    );
  }
}

/// 单个直播卡片。
class _LiveCard extends ConsumerWidget {
  final FeedContent item;
  const _LiveCard({required this.item});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final live = item.liveStatus == 'live';
    return Card(
      clipBehavior: Clip.antiAlias,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: Colors.grey.shade200),
      ),
      child: InkWell(
        onTap: () => _showLiveDetail(context, item),
        child: Stack(
          fit: StackFit.expand,
          children: [
            // 封面
            CachedNetworkImage(
              imageUrl: item.coverImage,
              fit: BoxFit.cover,
              placeholder: (_, __) => Container(
                color: Colors.grey[100],
                child: const Center(
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
              errorWidget: (_, __, ___) => Container(
                color: Colors.grey[100],
                child: const Icon(Icons.videocam_off, color: Colors.grey),
              ),
            ),
            // 底部渐变
            Container(
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Colors.transparent, Colors.black54],
                ),
              ),
            ),
            // 顶部：直播状态徽章 + 观看人数
            Positioned(
              top: 8,
              left: 8,
              right: 8,
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: live ? Colors.red : Colors.grey[600],
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          live ? Icons.circle : Icons.pause_circle,
                          size: 10,
                          color: Colors.white,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          live ? '直播中' : '已结束',
                          style: const TextStyle(
                              fontSize: 11, color: Colors.white),
                        ),
                      ],
                    ),
                  ),
                  const Spacer(),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: Colors.black45,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.visibility,
                            size: 12, color: Colors.white),
                        const SizedBox(width: 3),
                        Text(
                          _formatViewers(item.liveViewers ?? 0),
                          style: const TextStyle(
                              fontSize: 11, color: Colors.white),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            // 底部信息
            Positioned(
              left: 10,
              right: 10,
              bottom: 10,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    item.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      CircleAvatar(
                        radius: 9,
                        backgroundImage: NetworkImage(item.authorAvatar),
                        backgroundColor: Colors.white24,
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          item.author,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontSize: 12, color: Colors.white70),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 直播详情弹层（模拟直播画面）。
void _showLiveDetail(BuildContext context, FeedContent item) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (context) => _LiveDetailSheet(item: item),
  );
}

class _LiveDetailSheet extends ConsumerWidget {
  final FeedContent item;
  const _LiveDetailSheet({required this.item});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final feed = ref.watch(feedProvider);
    final liked = feed.isLiked(item.id);
    final live = item.liveStatus == 'live';
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.85,
      maxChildSize: 0.95,
      minChildSize: 0.4,
      builder: (context, scrollController) => Column(
        children: [
          const SizedBox(height: 8),
          Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: Colors.grey[300],
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Expanded(
            child: SingleChildScrollView(
              controller: scrollController,
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 直播画面
                  ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        CachedNetworkImage(
                          imageUrl: item.coverImage,
                          height: 260,
                          width: double.infinity,
                          fit: BoxFit.cover,
                          placeholder: (_, __) => Container(
                            color: Colors.grey[100],
                            height: 260,
                          ),
                        ),
                        Positioned(
                          top: 10,
                          left: 10,
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: live ? Colors.red : Colors.grey[600],
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              live ? '● 直播中' : '已结束',
                              style: const TextStyle(
                                  fontSize: 12, color: Colors.white),
                            ),
                          ),
                        ),
                        Positioned(
                          top: 10,
                          right: 10,
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: Colors.black45,
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Icon(Icons.visibility,
                                    size: 14, color: Colors.white),
                                const SizedBox(width: 4),
                                Text(
                                  _formatViewers(item.liveViewers ?? 0),
                                  style: const TextStyle(
                                      fontSize: 12, color: Colors.white),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      CircleAvatar(
                        radius: 18,
                        backgroundImage: NetworkImage(item.authorAvatar),
                        backgroundColor: Colors.grey[200],
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(item.title,
                                style: const TextStyle(
                                    fontWeight: FontWeight.bold,
                                    fontSize: 16)),
                            Text(
                              '${item.author} · ${item.liveViewers ?? 0} 人在看',
                              style: TextStyle(
                                  fontSize: 13, color: Colors.grey[600]),
                            ),
                          ],
                        ),
                      ),
                      TextButton(
                        onPressed: () => ref
                            .read(feedProvider.notifier)
                            .toggleFollow(item.author),
                        child: Text(
                          feed.isFollowed(item.author) ? '已关注' : '关注',
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    '直播间互动',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  // 模拟弹幕
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.grey[100],
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _Danmu(item.author, '主播正在讲解，欢迎来到直播间~'),
                        const SizedBox(height: 6),
                        _Danmu('用户A', '这个直播讲得真清楚'),
                        const SizedBox(height: 6),
                        _Danmu('用户B', '👍 学到了'),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      _LiveAction(
                        icon: liked
                            ? Icons.favorite
                            : Icons.favorite_border,
                        color: liked ? Colors.red : Colors.grey,
                        label: '${item.likes + (liked ? 1 : 0)}',
                        onTap: () =>
                            ref.read(feedProvider.notifier).toggleLike(item),
                      ),
                      _LiveAction(
                        icon: Icons.chat_bubble_outline,
                        label: '${item.comments}',
                        onTap: () {},
                      ),
                      _LiveAction(
                        icon: Icons.share_outlined,
                        label: '${item.shares}',
                        onTap: () {},
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Danmu extends StatelessWidget {
  final String user;
  final String text;
  const _Danmu(this.user, this.text);

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('$user：',
            style: const TextStyle(
                fontWeight: FontWeight.w600, fontSize: 13)),
        Expanded(
          child: Text(text,
              style: TextStyle(fontSize: 13, color: Colors.grey[700])),
        ),
      ],
    );
  }
}

class _LiveAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color? color;
  const _LiveAction({
    required this.icon,
    required this.label,
    required this.onTap,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Row(
          children: [
            Icon(icon, size: 22, color: color ?? Colors.grey[600]),
            const SizedBox(width: 4),
            Text(label,
                style: TextStyle(fontSize: 13, color: Colors.grey[700])),
          ],
        ),
      ),
    );
  }
}

String _formatViewers(int n) {
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(1)}万';
  if (n >= 1000) return '${(n / 1000).toStringAsFixed(1)}k';
  return '$n';
}

class _LiveError extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _LiveError({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, size: 48, color: Colors.grey),
          const SizedBox(height: 12),
          Text('加载失败：$message',
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.grey)),
          const SizedBox(height: 12),
          OutlinedButton(onPressed: onRetry, child: const Text('重试')),
        ],
      ),
    );
  }
}
