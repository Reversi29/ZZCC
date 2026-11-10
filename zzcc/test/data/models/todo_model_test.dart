// test/data/models/todo_model_test.dart
// TodoItem / MemoItem / TodoState 模型测试

import 'package:flutter_test/flutter_test.dart';
import 'package:zzcc/data/models/todo_model.dart';

void main() {
  group('TodoItem', () {
    test('toJson/fromJson roundtrip preserves all fields', () {
      final item = TodoItem(
        id: '1',
        title: '测试待办',
        note: '这是备注',
        completed: false,
        priority: TodoPriority.high,
        dueDate: '2026-11-15',
        createdAt: DateTime(2026, 11, 10, 10, 0),
        updatedAt: DateTime(2026, 11, 10, 11, 0),
      );

      final json = item.toJson();
      final restored = TodoItem.fromJson(json);

      expect(restored.id, '1');
      expect(restored.title, '测试待办');
      expect(restored.note, '这是备注');
      expect(restored.completed, false);
      expect(restored.priority, TodoPriority.high);
      expect(restored.dueDate, '2026-11-15');
      expect(restored.createdAt, DateTime(2026, 11, 10, 10, 0));
      expect(restored.updatedAt, DateTime(2026, 11, 10, 11, 0));
    });

    test('copyWith updates only specified fields', () {
      final item = TodoItem(
        id: '1',
        title: '原始',
        note: '',
        completed: false,
        priority: TodoPriority.normal,
        createdAt: DateTime(2026),
        updatedAt: DateTime(2026),
      );

      final updated = item.copyWith(completed: true, priority: TodoPriority.low);

      expect(updated.id, '1');
      expect(updated.title, '原始');
      expect(updated.completed, true);
      expect(updated.priority, TodoPriority.low);
      expect(updated.note, '');
    });
  });

  group('MemoItem', () {
    test('toJson/fromJson roundtrip preserves all fields', () {
      final memo = MemoItem(
        id: 'm1',
        content: '备忘录内容',
        colorHex: '#E1F5FE',
        createdAt: DateTime(2026, 11, 10),
        updatedAt: DateTime(2026, 11, 10),
      );

      final json = memo.toJson();
      final restored = MemoItem.fromJson(json);

      expect(restored.id, 'm1');
      expect(restored.content, '备忘录内容');
      expect(restored.colorHex, '#E1F5FE');
      expect(restored.createdAt, DateTime(2026, 11, 10));
    });
  });

  group('TodoState', () {
    test('fromStored handles Map and String', () {
      final state = TodoState(
        todos: [
          TodoItem(
            id: '1',
            title: 'A',
            createdAt: DateTime(2026),
            updatedAt: DateTime(2026),
          ),
        ],
        memos: [
          MemoItem(
            id: 'm1',
            content: 'note',
            createdAt: DateTime(2026),
            updatedAt: DateTime(2026),
          ),
        ],
      );

      // Map 形式
      final fromMap = TodoState.fromStored(state.toJson());
      expect(fromMap.todos.length, 1);
      expect(fromMap.memos.length, 1);
      expect(fromMap.todos.first.title, 'A');

      // null
      expect(TodoState.fromStored(null).todos, isEmpty);
      expect(TodoState.fromStored(null).memos, isEmpty);
    });

    test('fromStored handles corrupted data gracefully', () {
      final fromCorrupt = TodoState.fromStored('not valid json {{{');
      expect(fromCorrupt.todos, isEmpty);
      expect(fromCorrupt.memos, isEmpty);
    });
  });
}
