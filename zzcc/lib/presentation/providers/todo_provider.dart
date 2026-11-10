// lib/presentation/providers/todo_provider.dart
//
// 待办事项 + 备忘录的 Riverpod 状态管理。
// 持久化到 StorageService 的 app_settings Hive 盒子（Web 端 IndexedDB），
// 键名 'todoState'。数据模型见 data/models/todo_model.dart。

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/data/models/todo_model.dart';

final todoProvider =
    StateNotifierProvider<TodoNotifier, TodoState>((ref) => TodoNotifier());

class TodoNotifier extends StateNotifier<TodoState> {
  TodoNotifier() : super(const TodoState()) {
    _init();
  }

  Future<void> _init() async {
    final storage = getIt<StorageService>();
    if (!storage.isAppBoxOpen) return;
    final saved = storage.getFromAppBox('todoState');
    if (saved != null) {
      state = TodoState.fromStored(saved);
    }
  }

  Future<void> _persist() async {
    final storage = getIt<StorageService>();
    if (!storage.isAppBoxOpen) return;
    storage.saveToAppBox('todoState', state.toJson());
  }

  // ── 待办操作 ──

  Future<void> addTodo(String title,
      {String note = '',
      TodoPriority priority = TodoPriority.normal,
      String? dueDate}) async {
    final now = DateTime.now();
    final item = TodoItem(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      title: title.trim(),
      note: note,
      priority: priority,
      dueDate: dueDate,
      createdAt: now,
      updatedAt: now,
    );
    state = state.copyWith(todos: [...state.todos, item]);
    await _persist();
  }

  Future<void> updateTodo(String id,
      {String? title,
      String? note,
      TodoPriority? priority,
      String? dueDate}) async {
    final todos = state.todos.map((t) {
      if (t.id != id) return t;
      return t.copyWith(
        title: title,
        note: note,
        priority: priority,
        dueDate: dueDate,
        updatedAt: DateTime.now(),
      );
    }).toList();
    state = state.copyWith(todos: todos);
    await _persist();
  }

  Future<void> toggleTodo(String id) async {
    final todos = state.todos.map((t) {
      if (t.id != id) return t;
      return t.copyWith(completed: !t.completed, updatedAt: DateTime.now());
    }).toList();
    state = state.copyWith(todos: todos);
    await _persist();
  }

  Future<void> removeTodo(String id) async {
    state = state.copyWith(
        todos: state.todos.where((t) => t.id != id).toList());
    await _persist();
  }

  Future<void> clearCompleted() async {
    state = state.copyWith(
        todos: state.todos.where((t) => !t.completed).toList());
    await _persist();
  }

  // ── 备忘录操作 ──

  Future<void> addMemo(String content, {String colorHex = '#FFF9C4'}) async {
    final now = DateTime.now();
    final item = MemoItem(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      content: content.trim(),
      colorHex: colorHex,
      createdAt: now,
      updatedAt: now,
    );
    state = state.copyWith(memos: [...state.memos, item]);
    await _persist();
  }

  Future<void> updateMemo(String id, String content) async {
    final memos = state.memos.map((m) {
      if (m.id != id) return m;
      return m.copyWith(content: content, updatedAt: DateTime.now());
    }).toList();
    state = state.copyWith(memos: memos);
    await _persist();
  }

  Future<void> removeMemo(String id) async {
    state =
        state.copyWith(memos: state.memos.where((m) => m.id != id).toList());
    await _persist();
  }

  /// 排序视图：未完成在前，按优先级降序、截止日期升序。
  List<TodoItem> get sortedTodos {
    final list = [...state.todos];
    list.sort((a, b) {
      if (a.completed != b.completed) {
        return a.completed ? 1 : -1;
      }
      final p = b.priority.weight.compareTo(a.priority.weight);
      if (p != 0) return p;
      if (a.dueDate != null && b.dueDate != null) {
        return a.dueDate!.compareTo(b.dueDate!);
      }
      if (a.dueDate != null) return -1;
      if (b.dueDate != null) return 1;
      return b.updatedAt.compareTo(a.updatedAt);
    });
    return list;
  }
}
