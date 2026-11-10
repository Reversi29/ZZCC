// lib/data/models/todo_model.dart
//
// 待办事项 + 备忘录数据模型。
// 持久化到 StorageService 的 app_settings Hive 盒子（Web 端为 IndexedDB）。

import 'dart:convert';

/// 待办事项优先级。
enum TodoPriority { low, normal, high }

extension TodoPriorityX on TodoPriority {
  String get label {
    switch (this) {
      case TodoPriority.low:
        return '低';
      case TodoPriority.normal:
        return '中';
      case TodoPriority.high:
        return '高';
    }
  }

  int get weight {
    switch (this) {
      case TodoPriority.low:
        return 0;
      case TodoPriority.normal:
        return 1;
      case TodoPriority.high:
        return 2;
    }
  }
}

/// 一条待办事项。
class TodoItem {
  final String id;
  final String title;

  /// 详细备注（备忘录性质，可自由多行文本）。
  final String note;
  final bool completed;
  final TodoPriority priority;

  /// 截止日期（可选，存储为 yyyy-MM-dd 字符串）。
  final String? dueDate;
  final DateTime createdAt;
  final DateTime updatedAt;

  const TodoItem({
    required this.id,
    required this.title,
    this.note = '',
    this.completed = false,
    this.priority = TodoPriority.normal,
    this.dueDate,
    required this.createdAt,
    required this.updatedAt,
  });

  TodoItem copyWith({
    String? title,
    String? note,
    bool? completed,
    TodoPriority? priority,
    String? dueDate,
    DateTime? updatedAt,
  }) {
    return TodoItem(
      id: id,
      title: title ?? this.title,
      note: note ?? this.note,
      completed: completed ?? this.completed,
      priority: priority ?? this.priority,
      dueDate: dueDate ?? this.dueDate,
      createdAt: createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'note': note,
      'completed': completed,
      'priority': priority.index,
      'dueDate': dueDate,
      'createdAt': createdAt.toIso8601String(),
      'updatedAt': updatedAt.toIso8601String(),
    };
  }

  factory TodoItem.fromJson(Map<String, dynamic> json) {
    return TodoItem(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      note: json['note'] as String? ?? '',
      completed: json['completed'] as bool? ?? false,
      priority: TodoPriority.values[
          (json['priority'] as int? ?? TodoPriority.normal.index).clamp(0, 2)],
      dueDate: json['dueDate'] as String?,
      createdAt:
          DateTime.tryParse(json['createdAt'] as String? ?? '') ?? DateTime.now(),
      updatedAt:
          DateTime.tryParse(json['updatedAt'] as String? ?? '') ?? DateTime.now(),
    );
  }
}

/// 一条备忘录（便签式自由文本笔记）。
class MemoItem {
  final String id;
  final String content;
  final String colorHex;
  final DateTime createdAt;
  final DateTime updatedAt;

  const MemoItem({
    required this.id,
    required this.content,
    this.colorHex = '#FFF9C4',
    required this.createdAt,
    required this.updatedAt,
  });

  MemoItem copyWith({
    String? content,
    String? colorHex,
    DateTime? updatedAt,
  }) {
    return MemoItem(
      id: id,
      content: content ?? this.content,
      colorHex: colorHex ?? this.colorHex,
      createdAt: createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'content': content,
      'colorHex': colorHex,
      'createdAt': createdAt.toIso8601String(),
      'updatedAt': updatedAt.toIso8601String(),
    };
  }

  factory MemoItem.fromJson(Map<String, dynamic> json) {
    return MemoItem(
      id: json['id'] as String? ?? '',
      content: json['content'] as String? ?? '',
      colorHex: json['colorHex'] as String? ?? '#FFF9C4',
      createdAt:
          DateTime.tryParse(json['createdAt'] as String? ?? '') ?? DateTime.now(),
      updatedAt:
          DateTime.tryParse(json['updatedAt'] as String? ?? '') ?? DateTime.now(),
    );
  }
}

/// 待办 + 备忘录聚合数据（用于单个 Hive 键持久化）。
class TodoState {
  final List<TodoItem> todos;
  final List<MemoItem> memos;

  const TodoState({this.todos = const [], this.memos = const []});

  TodoState copyWith({List<TodoItem>? todos, List<MemoItem>? memos}) {
    return TodoState(
      todos: todos ?? this.todos,
      memos: memos ?? this.memos,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'todos': todos.map((t) => t.toJson()).toList(),
      'memos': memos.map((m) => m.toJson()).toList(),
    };
  }

  factory TodoState.fromJson(Map<String, dynamic> json) {
    final todoList = (json['todos'] as List<dynamic>? ?? [])
        .map((e) => TodoItem.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
    final memoList = (json['memos'] as List<dynamic>? ?? [])
        .map((e) => MemoItem.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
    return TodoState(todos: todoList, memos: memoList);
  }

  /// 从 Hive 存储的原始值恢复（可能是 Map 或 String）。
  static TodoState fromStored(dynamic stored) {
    if (stored == null) return const TodoState();
    try {
      if (stored is String) {
        return TodoState.fromJson(
            Map<String, dynamic>.from(jsonDecode(stored) as Map));
      }
      if (stored is Map) {
        return TodoState.fromJson(Map<String, dynamic>.from(stored));
      }
    } catch (_) {
      // 损坏数据回退为空状态。
    }
    return const TodoState();
  }
}
