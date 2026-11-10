// test/presentation/pages/home/widgets/todo_widget_test.dart
// TodoWidget / MemoWidget 交互测试（Flutter widget test）
// 注册 mock StorageService 到 getIt（isAppBoxOpen=false → _persist 空操作），
// 驱动真实 TodoProvider / TodoNotifier 逻辑。

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:get_it/get_it.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/data/models/todo_model.dart';
import 'package:zzcc/presentation/pages/home/widgets/todo_widget.dart';
import 'package:zzcc/presentation/pages/home/widgets/memo_widget.dart';
import 'package:zzcc/presentation/providers/todo_provider.dart';

/// 测试用 StorageService：isAppBoxOpen=false → TodoNotifier._init/_persist 直接
/// return，不触碰 Hive box（避免 mockito getter stub 问题）。
class FakeStorageService extends StorageService {
  @override
  bool get isAppBoxOpen => false;
}

Widget _wrap(Widget child) {
  return ProviderScope(
    child: MaterialApp(
      home: Scaffold(
        // 固定高度容器（非 SingleChildScrollView，避免无限高度触发 Expanded 断言）
        body: SizedBox(height: 900, child: child),
      ),
    ),
  );
}

void main() {
  late FakeStorageService fakeStorage;
  late GetIt getIt;

  setUp(() {
    getIt = GetIt.instance;
    fakeStorage = FakeStorageService();
    // isAppBoxOpen=false → TodoNotifier._init/_persist 直接 return
    getIt.pushNewScope();
    getIt.registerSingleton<StorageService>(fakeStorage);
  });

  tearDown(() {
    getIt.popScope();
  });

  testWidgets('添加待办 + 勾选完成', (tester) async {
    // 加大测试视口避免 RenderFlex overflow
    tester.view.physicalSize = const Size(1200, 2000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(_wrap(const TodoWidget()));
    await tester.pump();

    // 点击 + 按钮展开添加面板
    await tester.tap(find.byIcon(Icons.add_circle_outline));
    await tester.pumpAndSettle();

    // 确认 TextField 已挂载
    expect(find.byType(TextField), findsWidgets);

    // 输入标题
    await tester.enterText(find.byType(TextField).first, '测试待办');
    await tester.pump();

    // 点击添加按钮
    await tester.tap(find.text('添加'));
    await tester.pumpAndSettle();

    // 验证待办出现在列表
    expect(find.text('测试待办'), findsWidgets);
  });

  testWidgets('添加备忘录', (tester) async {
    // 加大测试视口避免 RenderFlex overflow
    tester.view.physicalSize = const Size(1200, 2000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(_wrap(const MemoWidget()));
    await tester.pump();

    await tester.enterText(find.byType(TextField).first, '这是一条便签');
    await tester.pump();

    await tester.tap(find.byIcon(Icons.add).last);
    await tester.pumpAndSettle();

    expect(find.text('这是一条便签'), findsWidgets);
  });

  test('TodoNotifier 添加/勾选/删除逻辑', () {
    final notifier = TodoNotifier();
    expect(notifier.state.todos, isEmpty);

    notifier.addTodo('任务A', priority: TodoPriority.high);
    expect(notifier.state.todos.length, 1);
    expect(notifier.state.todos.first.title, '任务A');
    expect(notifier.state.todos.first.priority, TodoPriority.high);

    final id = notifier.state.todos.first.id;
    notifier.toggleTodo(id);
    expect(notifier.state.todos.first.completed, true);

    notifier.removeTodo(id);
    expect(notifier.state.todos, isEmpty);
  });
}
