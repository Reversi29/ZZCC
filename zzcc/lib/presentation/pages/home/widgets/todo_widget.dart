// lib/presentation/pages/home/widgets/todo_widget.dart
//
// 待办事项 + 备忘录组件。
// 真实功能：待办增删改查、勾选完成、优先级、截止日期、备注；
//           备忘录便签（自由文本、颜色标记、自动保存）。
// 数据持久化到 StorageService app_settings（Web 端 IndexedDB）。

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/data/models/todo_model.dart';
import 'package:zzcc/presentation/providers/todo_provider.dart';

class TodoWidget extends ConsumerStatefulWidget {
  const TodoWidget({super.key});

  @override
  ConsumerState<TodoWidget> createState() => _TodoWidgetState();
}

class _TodoWidgetState extends ConsumerState<TodoWidget> {
  // 待办输入
  final TextEditingController _newTodoController = TextEditingController();
  final TextEditingController _newNoteController = TextEditingController();
  TodoPriority _newPriority = TodoPriority.normal;
  String? _newDueDate;

  // 备忘录输入
  final TextEditingController _newMemoController = TextEditingController();

  // 折叠状态
  bool _showMemoSection = true;
  bool _showAddPanel = false;

  @override
  void dispose() {
    _newTodoController.dispose();
    _newNoteController.dispose();
    _newMemoController.dispose();
    super.dispose();
  }

  String _formatDate(String? date) {
    if (date == null || date.isEmpty) return '';
    final parts = date.split('-');
    if (parts.length == 3) return '${parts[1]}/${parts[2]}';
    return date;
  }

  Future<void> _pickDueDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: now,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 5),
      helpText: '选择截止日期',
    );
    if (picked != null) {
      setState(() {
        _newDueDate =
            '${picked.year.toString().padLeft(4, '0')}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}';
      });
    }
  }

  void _submitNewTodo() {
    final title = _newTodoController.text.trim();
    if (title.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('请输入待办标题')),
      );
      return;
    }
    ref.read(todoProvider.notifier).addTodo(
          title,
          note: _newNoteController.text.trim(),
          priority: _newPriority,
          dueDate: _newDueDate,
        );
    _newTodoController.clear();
    _newNoteController.clear();
    setState(() {
      _newPriority = TodoPriority.normal;
      _newDueDate = null;
    });
  }

  void _submitNewMemo() {
    final content = _newMemoController.text.trim();
    if (content.isEmpty) return;
    ref.read(todoProvider.notifier).addMemo(content);
    _newMemoController.clear();
  }

  void _startEdit(TodoItem todo) {
    final titleController = TextEditingController(text: todo.title);
    final noteController = TextEditingController(text: todo.note);
    var priority = todo.priority;
    String? dueDate = todo.dueDate;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('编辑待办'),
          content: SizedBox(
            width: 340,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: titleController,
                  autofocus: true,
                  decoration: const InputDecoration(
                    labelText: '标题',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: noteController,
                  maxLines: 3,
                  decoration: const InputDecoration(
                    labelText: '备注',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    const Text('优先级', style: TextStyle(fontSize: 13)),
                    const SizedBox(width: 8),
                    DropdownButton<TodoPriority>(
                      value: priority,
                      isDense: true,
                      underline: const SizedBox(),
                      items: TodoPriority.values
                          .map((p) => DropdownMenuItem(
                                value: p,
                                child: Text(p.label,
                                    style: const TextStyle(fontSize: 13)),
                              ))
                          .toList(),
                      onChanged: (p) =>
                          setDialogState(() => priority = p ?? TodoPriority.normal),
                    ),
                    const Spacer(),
                    TextButton.icon(
                      onPressed: () async {
                        final now = DateTime.now();
                        final initial = dueDate != null
                            ? (DateTime.tryParse(dueDate!) ?? now)
                            : now;
                        final picked = await showDatePicker(
                          context: ctx,
                          initialDate: initial,
                          firstDate: DateTime(now.year - 1),
                          lastDate: DateTime(now.year + 5),
                        );
                        if (picked != null) {
                          setDialogState(() {
                            dueDate =
                                '${picked.year.toString().padLeft(4, '0')}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}';
                          });
                        }
                      },
                      icon: const Icon(Icons.event, size: 16),
                      label: Text(
                          dueDate ?? '截止日期',
                          style: const TextStyle(fontSize: 12)),
                    ),
                  ],
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () {
                final title = titleController.text.trim();
                if (title.isEmpty) {
                  Navigator.pop(ctx);
                  return;
                }
                ref.read(todoProvider.notifier).updateTodo(
                      todo.id,
                      title: title,
                      note: noteController.text.trim(),
                      priority: priority,
                      dueDate: dueDate,
                    );
                Navigator.pop(ctx);
              },
              child: const Text('保存'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(todoProvider);
    final todos = ref.read(todoProvider.notifier).sortedTodos;
    final activeCount = todos.where((t) => !t.completed).length;
    final memos = state.memos;

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(12.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 标题栏
            Row(
              children: [
                const Icon(Icons.checklist, size: 22, color: Colors.teal),
                const SizedBox(width: 8),
                const Text('待办事宜', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                const Spacer(),
                if (activeCount > 0)
                  Text('$activeCount 项待办',
                      style: const TextStyle(fontSize: 11, color: Colors.grey)),
                IconButton(
                  tooltip: '新增待办',
                  icon: const Icon(Icons.add_circle_outline, size: 20),
                  onPressed: () => setState(() => _showAddPanel = !_showAddPanel),
                ),
                IconButton(
                  tooltip: '清空已完成',
                  icon: const Icon(Icons.clear_all, size: 20),
                  onPressed: () {
                    if (state.todos.any((t) => t.completed)) {
                      ref.read(todoProvider.notifier).clearCompleted();
                    }
                  },
                ),
              ],
            ),

            // 新增待办面板
            if (_showAddPanel) _buildAddPanel(),

            const Divider(height: 12),

            // 待办列表
            if (todos.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Text('暂无待办，点击 + 添加',
                    style: TextStyle(fontSize: 12, color: Colors.grey[500])),
              )
            else
              Flexible(
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: todos.length,
                  itemBuilder: (context, i) => _buildTodoRow(todos[i]),
                ),
              ),

            // 备忘录区
            const Divider(height: 16),
            InkWell(
              onTap: () => setState(() => _showMemoSection = !_showMemoSection),
              child: Row(
                children: [
                  Icon(Icons.sticky_note_2_outlined,
                      size: 18, color: Colors.amber[700]),
                  const SizedBox(width: 6),
                  const Text('备忘录',
                      style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                  const Spacer(),
                  Text('${memos.length} 条',
                      style: const TextStyle(fontSize: 11, color: Colors.grey)),
                  Icon(_showMemoSection ? Icons.expand_less : Icons.expand_more,
                      size: 18),
                ],
              ),
            ),
            if (_showMemoSection) _buildMemoSection(memos),
          ],
        ),
      ),
    );
  }

  Widget _buildAddPanel() {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _newTodoController,
            decoration: const InputDecoration(
              hintText: '待办标题',
              isDense: true,
              border: OutlineInputBorder(),
            ),
            onSubmitted: (_) => _submitNewTodo(),
          ),
          const SizedBox(height: 6),
          TextField(
            controller: _newNoteController,
            maxLines: 2,
            decoration: const InputDecoration(
              hintText: '备注（可选）',
              isDense: true,
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              DropdownButton<TodoPriority>(
                value: _newPriority,
                isDense: true,
                underline: const SizedBox(),
                items: TodoPriority.values
                    .map((p) => DropdownMenuItem(
                          value: p,
                          child: Text(p.label,
                              style: const TextStyle(fontSize: 12)),
                        ))
                    .toList(),
                onChanged: (p) =>
                    setState(() => _newPriority = p ?? TodoPriority.normal),
              ),
              const SizedBox(width: 8),
              TextButton.icon(
                onPressed: _pickDueDate,
                icon: const Icon(Icons.event, size: 16),
                label: Text(_newDueDate == null
                    ? '截止日期'
                    : _formatDate(_newDueDate)),
                style: TextButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                  textStyle: const TextStyle(fontSize: 12),
                ),
              ),
              if (_newDueDate != null)
                IconButton(
                  icon: const Icon(Icons.close, size: 14),
                  onPressed: () => setState(() => _newDueDate = null),
                ),
              const Spacer(),
              FilledButton(
                onPressed: _submitNewTodo,
                style: FilledButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                ),
                child: const Text('添加', style: TextStyle(fontSize: 12)),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildTodoRow(TodoItem todo) {
    final overdue = !todo.completed &&
        todo.dueDate != null &&
        DateTime.tryParse(todo.dueDate!) != null &&
        DateTime.tryParse(todo.dueDate!)!.isBefore(DateTime.now());
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Checkbox(
            value: todo.completed,
            visualDensity: VisualDensity.compact,
            onChanged: (_) =>
                ref.read(todoProvider.notifier).toggleTodo(todo.id),
          ),
          Expanded(
            child: InkWell(
              onTap: () => _startEdit(todo),
              onLongPress: () => _showTodoMenu(todo),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            todo.title,
                            style: TextStyle(
                              fontSize: 13,
                              decoration: todo.completed
                                  ? TextDecoration.lineThrough
                                  : null,
                              color: todo.completed ? Colors.grey : null,
                              fontWeight: todo.priority == TodoPriority.high
                                  ? FontWeight.bold
                                  : null,
                            ),
                          ),
                        ),
                        _priorityChip(todo.priority),
                      ],
                    ),
                    if (todo.note.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          todo.note,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              fontSize: 11, color: Colors.grey[600]),
                        ),
                      ),
                    if (todo.dueDate != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Row(
                          children: [
                            Icon(Icons.event, size: 12, color: overdue ? Colors.red : Colors.grey),
                            const SizedBox(width: 2),
                            Text(
                              _formatDate(todo.dueDate) + (overdue ? ' · 已逾期' : ''),
                              style: TextStyle(
                                  fontSize: 11,
                                  color: overdue ? Colors.red : Colors.grey),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _priorityChip(TodoPriority p) {
    Color color;
    switch (p) {
      case TodoPriority.high:
        color = Colors.red;
      case TodoPriority.normal:
        color = Colors.blueGrey;
      case TodoPriority.low:
        color = Colors.green;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(p.label,
          style: TextStyle(fontSize: 10, color: color)),
    );
  }

  void _showTodoMenu(TodoItem todo) {
    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.edit),
              title: const Text('编辑'),
              onTap: () {
                Navigator.pop(ctx);
                _startEdit(todo);
              },
            ),
            ListTile(
              leading: const Icon(Icons.delete_outline),
              title: const Text('删除'),
              onTap: () {
                Navigator.pop(ctx);
                ref.read(todoProvider.notifier).removeTodo(todo.id);
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMemoSection(List<MemoItem> memos) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 4),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _newMemoController,
                decoration: const InputDecoration(
                  hintText: '写备忘录...',
                  isDense: true,
                  border: OutlineInputBorder(),
                ),
                onSubmitted: (_) => _submitNewMemo(),
              ),
            ),
            const SizedBox(width: 6),
            IconButton(
              icon: const Icon(Icons.add, size: 20),
              onPressed: _submitNewMemo,
            ),
          ],
        ),
        const SizedBox(height: 6),
        if (memos.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Text('暂无备忘录',
                style: TextStyle(fontSize: 11, color: Colors.grey[500])),
          )
        else
          Flexible(
            child: ListView.builder(
              shrinkWrap: true,
              itemCount: memos.length,
              itemBuilder: (context, i) => _buildMemoItem(memos[i]),
            ),
          ),
      ],
    );
  }

  Widget _buildMemoItem(MemoItem memo) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: InkWell(
        onTap: () => _showMemoEditor(memo),
        onLongPress: () {
          ref.read(todoProvider.notifier).removeMemo(memo.id);
        },
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: _memoColor(memo.colorHex),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: Colors.grey.withValues(alpha: 0.2)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                memo.content,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 12),
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  Icon(Icons.edit_note, size: 12, color: Colors.grey[600]),
                  const SizedBox(width: 2),
                  Text(
                    _formatMemoTime(memo.updatedAt),
                    style: TextStyle(fontSize: 10, color: Colors.grey[600]),
                  ),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.delete_outline, size: 14),
                    visualDensity: VisualDensity.compact,
                    onPressed: () =>
                        ref.read(todoProvider.notifier).removeMemo(memo.id),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showMemoEditor(MemoItem memo) {
    final controller = TextEditingController(text: memo.content);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('编辑备忘录'),
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

  String _formatMemoTime(DateTime t) {
    final now = DateTime.now();
    if (t.year == now.year && t.month == now.month && t.day == now.day) {
      return '今天 ${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
    }
    return '${t.month}/${t.day}';
  }
}
