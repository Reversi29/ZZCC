// lib/presentation/pages/square/widgets/feed_article_view.dart
//
// 图文 tab：文章卡片列表（大图 + 标题 + 摘要 + 作者行 + 互动数据）。
// 借鉴头条/知乎图文信息流：大卡片式列表，点开详情弹层。

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:cached_network_image/cached_network_image.dart';

import '../../../../data/models/feed_content_model.dart';
import '../../../../presentation/providers/feed_provider.dart';

/// 图文内容列表。
class FeedArticleView extends ConsumerStatefulWidget {
  const FeedArticleView({super.key});

  @override
  ConsumerState<FeedArticleView> createState() => _FeedArticleViewState();
}

class _FeedArticleViewState extends ConsumerState<FeedArticleView>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(feedProvider.notifier).load(FeedContentType.article);
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final feed = ref.watch(feedProvider);
    final contents = feed.contents(FeedContentType.article);
    final loading = feed.isLoading(FeedContentType.article);
    final error = feed.error(FeedContentType.article);

    if (loading && contents.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (error != null && contents.isEmpty) {
      return _ArticleError(
        message: error,
        onRetry: () =>
            ref.read(feedProvider.notifier).load(FeedContentType.article),
      );
    }
    if (contents.isEmpty) {
      return const Center(child: Text('暂无图文内容'));
    }

    return RefreshIndicator(
      onRefresh: () => ref
          .read(feedProvider.notifier)
          .load(FeedContentType.article, refresh: true),
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: contents.length,
        itemBuilder: (context, index) =>
            _ArticleCard(item: contents[index]),
      ),
    );
  }
}

/// 单篇图文卡片。
class _ArticleCard extends ConsumerWidget {
  final FeedContent item;
  const _ArticleCard({required this.item});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final feed = ref.watch(feedProvider);
    final liked = feed.isLiked(item.id);
    return Card(
      clipBehavior: Clip.antiAlias,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: Colors.grey.shade200),
      ),
      child: InkWell(
        onTap: () => _showArticleDetail(context, item),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 大图
            CachedNetworkImage(
              imageUrl: item.coverImage,
              height: 180,
              width: double.infinity,
              fit: BoxFit.cover,
              placeholder: (_, __) => Container(
                color: Colors.grey[100],
                height: 180,
                child: const Center(
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
              errorWidget: (_, __, ___) => Container(
                color: Colors.grey[100],
                height: 180,
                child: const Icon(Icons.broken_image, color: Colors.grey),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    item.description,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 14, color: Colors.grey[600]),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      CircleAvatar(
                        radius: 14,
                        backgroundImage: NetworkImage(item.authorAvatar),
                        backgroundColor: Colors.grey[200],
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          item.author,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 13,
                            color: Colors.grey[600],
                          ),
                        ),
                      ),
                      Icon(
                        liked ? Icons.favorite : Icons.favorite_border,
                        size: 16,
                        color: liked ? Colors.red : Colors.grey[500],
                      ),
                      const SizedBox(width: 4),
                      Text(
                        '${item.likes + (liked ? 1 : 0)}',
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

/// 图文详情底部弹层。
void _showArticleDetail(BuildContext context, FeedContent item) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (context) => _ArticleDetailSheet(item: item),
  );
}

class _ArticleDetailSheet extends ConsumerWidget {
  final FeedContent item;
  const _ArticleDetailSheet({required this.item});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final feed = ref.watch(feedProvider);
    final liked = feed.isLiked(item.id);
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
                  Text(
                    item.title,
                    style: const TextStyle(
                        fontSize: 20, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      CircleAvatar(
                        radius: 16,
                        backgroundImage: NetworkImage(item.authorAvatar),
                        backgroundColor: Colors.grey[200],
                      ),
                      const SizedBox(width: 8),
                      Text(item.author,
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      const SizedBox(width: 8),
                      Text(
                        '${item.views} 次浏览 · ${item.createdAt.toString().split(' ').first}',
                        style: TextStyle(
                            fontSize: 12, color: Colors.grey[500]),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: CachedNetworkImage(
                      imageUrl: item.coverImage,
                      height: 220,
                      width: double.infinity,
                      fit: BoxFit.cover,
                      placeholder: (_, __) =>
                          Container(color: Colors.grey[100], height: 220),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    item.description,
                    style: TextStyle(
                        fontSize: 15, height: 1.7, color: Colors.grey[800]),
                  ),
                  const SizedBox(height: 14),
                  // 正文模拟段落
                  Text(
                    '${item.description}\n\n'
                    '在类脑系统与知识图谱结合的架构中，图文内容作为信息载体，'
                    '承载着从感知到认知再到决策的完整链路。本文从设计理念、'
                    '核心架构到工程实践展开，为读者提供一个系统化的视角。\n\n'
                    '整体架构采用分层设计：数据层负责采集与存储，逻辑层负责'
                    '推理与融合，展示层负责交互与反馈。各层之间通过标准接口'
                    '解耦，便于后续扩展与维护。',
                    style: TextStyle(
                        fontSize: 15, height: 1.7, color: Colors.grey[800]),
                  ),
                  const SizedBox(height: 16),
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
                      _ArticleAction(
                        icon: liked
                            ? Icons.favorite
                            : Icons.favorite_border,
                        color: liked ? Colors.red : Colors.grey,
                        label: '${item.likes + (liked ? 1 : 0)}',
                        onTap: () =>
                            ref.read(feedProvider.notifier).toggleLike(item),
                      ),
                      _ArticleAction(
                        icon: Icons.chat_bubble_outline,
                        label: '${item.comments}',
                        onTap: () {},
                      ),
                      _ArticleAction(
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

class _ArticleAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color? color;
  const _ArticleAction({
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

class _ArticleError extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ArticleError({required this.message, required this.onRetry});

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
