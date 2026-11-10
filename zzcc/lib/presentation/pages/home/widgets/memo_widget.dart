// lib/presentation/pages/home/widgets/memo_widget.dart
//
// 备忘录便签墙组件（独立功能）。
// 支持：添加便签、编辑、删除、颜色标记、自动保存（IndexedDB）。
// 数据持久化到 StorageService app_settings（键 'todoState' 的 memos）。

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/data/models/todo_model.dart';
import 'package:zzcc/presentation/providers/todo_provider.dart';

class MemoWidget extends ConsumerStatefulWidget {
  const MemoWidget({super.key});

  @override
  ConsumerState<MemoWidget> createState() => _MemoWidgetState();
}

class _MemoWidgetState extends ConsumerState<MemoWidget> {
  final TextEditingController _controller = TextEditingController();
  static const _colors = [
    '#FFF9C4', // 黄
    '#E1F5FE', // 蓝
    '#E8F5E9', // 绿
    '#FCE4EC', // 粉
    '#F3E5F5', // 紫
  ];
  int _colorIndex = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _addMemo() {
    final content = _controller.text.trim();
    if (content.isEmpty) return;
    ref
        .read(todoProvider.notifier)
        .addMemo(content, colorHex: _colors[_colorIndex]);
    _controller.clear();
    setState(() => _colorIndex = (_colorIndex + 1) % _colors.length);
  }

  void _editMemo(MemoItem memo) {
    final controller = TextEditingController(text: memo.content);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('编辑便签'),
        content: TextField(
          controller: controller,
          maxLines: 6,
          autofocus: true,
          decoration: const InputDecoration(
            hintText: '输入内容',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () {
              ref
                  .read(todoProvider.notifier)
                  .updateMemo(memo.id, controller.text.trim());
              Navigator.pop(ctx);
            },
            child: const Text('保存'),
          ),
        ],
      ),
    );
  }

  Color _memoColor(String hex) {
    try {
      final value = hex.replaceFirst('#', '');
      return Color(int.parse('FF$value', radix: 16));
    } catch (_) {
      return const Color(0xFFFFF9C4);
    }
  }

  String _formatTime(DateTime t) {
    final now = DateTime.now();
    if (t.year == now.year && t.month == now.month && t.day == now.day) {
      return '今天 ${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
    }
    return '${t.month}/${t.day} ${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final memos = ref.watch(todoProvider.select((s) => s.memos));

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(12.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.sticky_note_2_outlined,
                    size: 22, color: Colors.amber),
                const SizedBox(width: 8),
                const Text('备忘录',
                    style:
                        TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                const Spacer(),
                Text('${memos.length} 条便签',
                    style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ],
            ),
            const SizedBox(height: 8),
            // 添加便签行
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    decoration: const InputDecoration(
                      hintText: '添加便签...',
                      isDense: true,
                      border: OutlineInputBorder(),
                    ),
                    onSubmitted: (_) => _addMemo(),
                  ),
                ),
                const SizedBox(width: 6),
                // 颜色选择
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.grey.shade300),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: DropdownButton<int>(
                    value: _colorIndex,
                    isDense: true,
                    underline: const SizedBox(),
                    items: List.generate(_colors.length, (i) {
                      return DropdownMenuItem(
                        value: i,
                        child: Container(
                          width: 18,
                          height: 18,
                          decoration: BoxDecoration(
                            color: _memoColor(_colors[i]),
                            borderRadius: BorderRadius.circular(3),
                            border: Border.all(color: Colors.grey.shade300),
                          ),
                        ),
                      );
                    }),
                    onChanged: (v) =>
                        setState(() => _colorIndex = v ?? 0),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.add, size: 20),
                  onPressed: _addMemo,
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (memos.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Center(
                  child: Text('暂无便签，输入内容添加',
                      style: TextStyle(fontSize: 12, color: Colors.grey[500])),
                ),
              )
            else
              Flexible(
                child: GridView.builder(
                  shrinkWrap: true,
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2,
                    mainAxisSpacing: 8,
                    crossAxisSpacing: 8,
                    childAspectRatio: 1.3,
                  ),
                  itemCount: memos.length,
                  itemBuilder: (context, i) {
                    final memo = memos[i];
                    return InkWell(
                      onTap: () => _editMemo(memo),
                      onLongPress: () => ref
                          .read(todoProvider.notifier)
                          .removeMemo(memo.id),
                      child: Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: _memoColor(memo.colorHex),
                          borderRadius: BorderRadius.circular(6),
                          border:
                              Border.all(color: Colors.grey.withValues(alpha: 0.2)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Text(
                                memo.content,
                                maxLines: 5,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 11),
                              ),
                            ),
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    _formatTime(memo.updatedAt),
                                    style: TextStyle(
                                        fontSize: 9, color: Colors.grey[600]),
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                                InkWell(
                                  onTap: () => ref
                                      .read(todoProvider.notifier)
                                      .removeMemo(memo.id),
                                  child: Icon(Icons.close,
                                      size: 12, color: Colors.grey[600]),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}
