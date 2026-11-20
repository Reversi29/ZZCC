// lib/presentation/pages/square/widgets/feed_app_view.dart
//
// 应用 tab：应用市场风格（分类标签 + 应用卡片网格 + 下载/安装按钮）。
// 借鉴应用商店/App Store 布局：顶部分类筛选 + 双列应用卡片。

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:cached_network_image/cached_network_image.dart';

import '../../../../data/models/feed_content_model.dart';
import '../../../../presentation/providers/feed_provider.dart';

/// 应用市场视图。
class FeedAppView extends ConsumerStatefulWidget {
  const FeedAppView({super.key});

  @override
  ConsumerState<FeedAppView> createState() => _FeedAppViewState();
}

class _FeedAppViewState extends ConsumerState<FeedAppView>
    with AutomaticKeepAliveClientMixin {
  String _selectedCategory = '全部';

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(feedProvider.notifier).load(FeedContentType.app);
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final feed = ref.watch(feedProvider);
    final all = feed.contents(FeedContentType.app);
    final loading = feed.isLoading(FeedContentType.app);
    final error = feed.error(FeedContentType.app);

    if (loading && all.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (error != null && all.isEmpty) {
      return _AppError(
        message: error,
        onRetry: () =>
            ref.read(feedProvider.notifier).load(FeedContentType.app),
      );
    }
    if (all.isEmpty) {
      return const Center(child: Text('暂无应用'));
    }

    // 分类筛选
    final categories = <String>{'全部', for (final a in all) if (a.appCategory != null) a.appCategory!}.toList();
    final filtered = _selectedCategory == '全部'
        ? all
        : all.where((a) => a.appCategory == _selectedCategory).toList();

    return Column(
      children: [
        // 分类标签
        SizedBox(
          height: 46,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            children: categories.map((cat) {
              final selected = cat == _selectedCategory;
              return Padding(
                padding: const EdgeInsets.only(right: 8),
                child: ChoiceChip(
                  label: Text(cat),
                  selected: selected,
                  onSelected: (_) =>
                      setState(() => _selectedCategory = cat),
                  labelStyle: TextStyle(
                    fontSize: 13,
                    color: selected ? Colors.white : Colors.grey[700],
                  ),
                  selectedColor: Colors.blue,
                  backgroundColor: Colors.grey[100],
                  showCheckmark: false,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                ),
              );
            }).toList(),
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: () =>
                ref.read(feedProvider.notifier).load(FeedContentType.app,
                    refresh: true),
            child: GridView.builder(
              padding: const EdgeInsets.all(12),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                mainAxisSpacing: 12,
                crossAxisSpacing: 12,
                childAspectRatio: 0.78,
              ),
              itemCount: filtered.length,
              itemBuilder: (context, index) =>
                  _AppCard(item: filtered[index]),
            ),
          ),
        ),
      ],
    );
  }
}

/// 单个应用卡片。
class _AppCard extends ConsumerWidget {
  final FeedContent item;
  const _AppCard({required this.item});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final feed = ref.watch(feedProvider);
    final installed = feed.isInstalled(item.id);
    return Card(
      clipBehavior: Clip.antiAlias,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: Colors.grey.shade200),
      ),
      child: InkWell(
        onTap: () => _showAppDetail(context, item),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 应用图标
              Center(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(18),
                  child: CachedNetworkImage(
                    imageUrl: item.appIcon ?? item.coverImage,
                    width: 64,
                    height: 64,
                    fit: BoxFit.cover,
                    placeholder: (_, __) => Container(
                      width: 64,
                      height: 64,
                      color: Colors.grey[100],
                      child: const Icon(Icons.apps, color: Colors.grey),
                    ),
                    errorWidget: (_, __, ___) => Container(
                      width: 64,
                      height: 64,
                      color: Colors.grey[100],
                      child: const Icon(Icons.apps, color: Colors.grey),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 10),
              Text(
                item.title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    fontSize: 15, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 4),
              Text(
                item.appCategory ?? '应用',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 12, color: Colors.grey[500]),
              ),
              const SizedBox(height: 6),
              Text(
                _formatDownloads(item.appDownloads ?? 0),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 12, color: Colors.grey[500]),
              ),
              const Spacer(),
              // 安装/打开按钮
              SizedBox(
                width: double.infinity,
                height: 30,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                    padding: EdgeInsets.zero,
                    backgroundColor: installed
                        ? Colors.grey[300]
                        : Colors.blue,
                    foregroundColor:
                        installed ? Colors.grey[800] : Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(15),
                    ),
                  ),
                  onPressed: () =>
                      ref.read(feedProvider.notifier).toggleInstall(item),
                  child: Text(
                    installed ? '打开' : '安装',
                    style: const TextStyle(fontSize: 13),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 应用详情弹层。
void _showAppDetail(BuildContext context, FeedContent item) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (context) => _AppDetailSheet(item: item),
  );
}

class _AppDetailSheet extends ConsumerWidget {
  final FeedContent item;
  const _AppDetailSheet({required this.item});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final feed = ref.watch(feedProvider);
    final installed = feed.isInstalled(item.id);
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.7,
      maxChildSize: 0.9,
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
                      ClipRRect(
                        borderRadius: BorderRadius.circular(16),
                        child: CachedNetworkImage(
                          imageUrl: item.appIcon ?? item.coverImage,
                          width: 72,
                          height: 72,
                          fit: BoxFit.cover,
                          placeholder: (_, __) => Container(
                            width: 72,
                            height: 72,
                            color: Colors.grey[100],
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(item.title,
                                style: const TextStyle(
                                    fontSize: 18,
                                    fontWeight: FontWeight.bold)),
                            const SizedBox(height: 4),
                            Text(
                              '${item.appCategory ?? ''} · ${item.appVersion ?? ''}',
                              style: TextStyle(
                                  fontSize: 13, color: Colors.grey[600]),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              '${_formatDownloads(item.appDownloads ?? 0)} 次下载',
                              style: TextStyle(
                                  fontSize: 13, color: Colors.grey[600]),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    height: 40,
                    child: FilledButton(
                      style: FilledButton.styleFrom(
                        backgroundColor:
                            installed ? Colors.grey[300] : Colors.blue,
                        foregroundColor:
                            installed ? Colors.grey[800] : Colors.white,
                      ),
                      onPressed: () =>
                          ref.read(feedProvider.notifier).toggleInstall(item),
                      child: Text(installed ? '打开' : '安装'),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text('应用介绍',
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  Text(
                    '${item.title} 是一款${item.appCategory ?? '应用'}类应用。'
                    '${item.description}\n\n'
                    '支持跨平台运行，提供流畅的交互体验与数据同步能力。'
                    '本应用由 ZZCC 官方团队维护，持续更新迭代。',
                    style: TextStyle(
                        fontSize: 14, height: 1.6, color: Colors.grey[800]),
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
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

String _formatDownloads(int n) {
  if (n >= 1000000) return '${(n / 1000000).toStringAsFixed(1)}M 下载';
  if (n >= 1000) return '${(n / 1000).toStringAsFixed(1)}K 下载';
  return '$n 下载';
}

class _AppError extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _AppError({required this.message, required this.onRetry});

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
