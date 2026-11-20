// lib/presentation/pages/square/widgets/feed_project_view.dart
//
// 项目 tab：开源项目/作品展示卡片列表。
// 借鉴 GitHub Trending 布局：项目封面 + 标题 + 描述 + 作者 + 星标/评论。

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:cached_network_image/cached_network_image.dart';

import '../../../../data/models/feed_content_model.dart';
import '../../../../presentation/providers/feed_provider.dart';

/// 项目展示列表。
class FeedProjectView extends ConsumerStatefulWidget {
  const FeedProjectView({super.key});

  @override
  ConsumerState<FeedProjectView> createState() => _FeedProjectViewState();
}

class _FeedProjectViewState extends ConsumerState<FeedProjectView>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(feedProvider.notifier).load(FeedContentType.project);
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final feed = ref.watch(feedProvider);
    final contents = feed.contents(FeedContentType.project);
    final loading = feed.isLoading(FeedContentType.project);
    final error = feed.error(FeedContentType.project);

    if (loading && contents.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (error != null && contents.isEmpty) {
      return _ProjectError(
        message: error,
        onRetry: () =>
            ref.read(feedProvider.notifier).load(FeedContentType.project),
      );
    }
    if (contents.isEmpty) {
      return const Center(child: Text('暂无项目'));
    }

    return RefreshIndicator(
      onRefresh: () => ref
          .read(feedProvider.notifier)
          .load(FeedContentType.project, refresh: true),
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: contents.length,
        itemBuilder: (context, index) =>
            _ProjectCard(item: contents[index]),
      ),
    );
  }
}

/// 单个项目卡片。
class _ProjectCard extends ConsumerWidget {
  final FeedContent item;
  const _ProjectCard({required this.item});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final feed = ref.watch(feedProvider);
    final starred = feed.isLiked(item.id);
    return Card(
      clipBehavior: Clip.antiAlias,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: Colors.grey.shade200),
      ),
      child: InkWell(
        onTap: () => _showProjectDetail(context, item),
        child: Row(
          children: [
            // 封面
            CachedNetworkImage(
              imageUrl: item.coverImage,
              width: 110,
              height: 110,
              fit: BoxFit.cover,
              placeholder: (_, __) => Container(
                width: 110,
                height: 110,
                color: Colors.grey[100],
                child: const Center(
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
              errorWidget: (_, __, ___) => Container(
                width: 110,
                height: 110,
                color: Colors.grey[100],
                child: const Icon(Icons.broken_image, color: Colors.grey),
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      item.description,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          fontSize: 13, color: Colors.grey[600]),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        CircleAvatar(
                          radius: 9,
                          backgroundImage: NetworkImage(item.authorAvatar),
                          backgroundColor: Colors.grey[200],
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            item.author,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                                fontSize: 12, color: Colors.grey[600]),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Icon(
                          starred
                              ? Icons.star
                              : Icons.star_border,
                          size: 16,
                          color: starred ? Colors.amber : Colors.grey[500],
                        ),
                        const SizedBox(width: 4),
                        Text(
                          '${item.likes + (starred ? 1 : 0)}',
                          style: TextStyle(
                              fontSize: 13, color: Colors.grey[600]),
                        ),
                        const SizedBox(width: 12),
                        Icon(Icons.chat_bubble_outline,
                            size: 16, color: Colors.grey[500]),
                        const SizedBox(width: 4),
                        Text(
                          '${item.comments}',
                          style: TextStyle(
                              fontSize: 13, color: Colors.grey[600]),
                        ),
                        const Spacer(),
                        Text(
                          item.tags.join(' · '),
                          style: TextStyle(
                              fontSize: 11, color: Colors.blue[600]),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 项目详情弹层。
void _showProjectDetail(BuildContext context, FeedContent item) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (context) => _ProjectDetailSheet(item: item),
  );
}

class _ProjectDetailSheet extends ConsumerWidget {
  final FeedContent item;
  const _ProjectDetailSheet({required this.item});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final feed = ref.watch(feedProvider);
    final starred = feed.isLiked(item.id);
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.75,
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
                            Text(item.author,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600)),
                            Text('${item.views} 次浏览',
                                style: TextStyle(
                                    fontSize: 12, color: Colors.grey[500])),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: CachedNetworkImage(
                      imageUrl: item.coverImage,
                      height: 200,
                      width: double.infinity,
                      fit: BoxFit.cover,
                      placeholder: (_, __) =>
                          Container(color: Colors.grey[100], height: 200),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(item.title,
                      style: const TextStyle(
                          fontSize: 18, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  Text(
                    item.description,
                    style: TextStyle(
                        fontSize: 14, height: 1.6, color: Colors.grey[800]),
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 6,
                    children: item.tags
                        .map((t) => Chip(
                              label: Text(t),
                              labelStyle: const TextStyle(fontSize: 12),
                              visualDensity: VisualDensity.compact,
                              backgroundColor: Colors.blue[50],
                            ))
                        .toList(),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      _ProjectAction(
                        icon: starred ? Icons.star : Icons.star_border,
                        color: starred ? Colors.amber : Colors.grey,
                        label: '${item.likes + (starred ? 1 : 0)}',
                        onTap: () =>
                            ref.read(feedProvider.notifier).toggleLike(item),
                      ),
                      _ProjectAction(
                        icon: Icons.chat_bubble_outline,
                        label: '${item.comments}',
                        onTap: () {},
                      ),
                      _ProjectAction(
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

class _ProjectAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color? color;
  const _ProjectAction({
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

class _ProjectError extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ProjectError({required this.message, required this.onRetry});

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
