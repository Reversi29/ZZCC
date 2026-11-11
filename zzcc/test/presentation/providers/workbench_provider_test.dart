import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:desktop_drop/desktop_drop.dart';
import 'package:cross_file/cross_file.dart' show XFile;
import 'package:get_it/get_it.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/core/services/net_service.dart';
import 'package:zzcc/presentation/providers/workbench_provider.dart';
import 'package:zzcc/presentation/pages/workbench/web_folder_picker_stub.dart'
    show WebPickedFile;

/// 测试用 StorageService：isAppBoxOpen=false → 设置方法安全跳过 Hive box
class FakeStorageService extends StorageService {
  @override
  bool get isAppBoxOpen => false;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late WorkbenchProvider provider;

  setUpAll(() {
    GetIt.instance.reset();
  });

  setUp(() async {
    // 确保注册（每次 setUp 重新注册，避免时序问题）
    if (!GetIt.instance.isRegistered<StorageService>()) {
      GetIt.instance.registerSingleton<StorageService>(FakeStorageService());
    }
    if (!GetIt.instance.isRegistered<ApiService>()) {
      GetIt.instance.registerSingleton<ApiService>(ApiServiceImpl());
    }

    // 创建临时目录作为 git 仓库
    tempDir = await Directory.systemTemp.createTemp('workbench_test_');
    await Process.run('git', ['init', '-q'], workingDirectory: tempDir.path);
    await Process.run('git', ['config', 'user.email', 'test@test.com'],
        workingDirectory: tempDir.path);
    await Process.run('git', ['config', 'user.name', 'Test'],
        workingDirectory: tempDir.path);
    provider = WorkbenchProvider();
  });

  tearDown(() async {
    try {
      await tempDir.delete(recursive: true);
    } catch (_) {}
  });

  Future<void> openFolder(WorkbenchProvider p, String path) async {
    final details = DropDoneDetails(
      files: [XFile(path)],
      localPosition: Offset.zero,
      globalPosition: Offset.zero,
    );
    await p.handleDrop(details);
  }

  test('refreshGitStatus 读取工作区状态', () async {
    // 创建未跟踪文件
    await File('${tempDir.path}/test.txt').writeAsString('hello');
    await openFolder(provider, tempDir.path);

    await provider.refreshGitStatus();
    expect(provider.gitStatus.isNotEmpty, true);
    expect(provider.gitStatus.any((s) => s.path.contains('test.txt')), true);
  });

  test('gitCommit 提交变更', () async {
    await File('${tempDir.path}/test.txt').writeAsString('hello');
    await openFolder(provider, tempDir.path);
    await provider.refreshGitStatus();

    final ok = await provider.gitCommit('测试提交');
    expect(ok, true);

    await provider.refreshGitStatus();
    expect(provider.gitStatus.isEmpty, true);
    expect(provider.gitLog.isNotEmpty, true);
    expect(provider.gitLog.first.message, contains('测试提交'));
  });

  test('searchFiles 按文件名搜索', () async {
    await File('${tempDir.path}/hello.txt').writeAsString('world');
    await File('${tempDir.path}/other.txt').writeAsString('nothing');
    await openFolder(provider, tempDir.path);

    await provider.searchFiles('hello');
    expect(provider.searchResults.isNotEmpty, true);
    expect(provider.searchResults.any((r) => r.name == 'hello.txt'), true);
  });

  test('searchFiles 按内容搜索', () async {
    await File('${tempDir.path}/code.txt').writeAsString('special_keyword_here');
    await openFolder(provider, tempDir.path);

    await provider.searchFiles('special_keyword');
    expect(provider.searchResults.isNotEmpty, true);
    expect(provider.searchResults.first.isContentMatch, true);
  });

  test('编辑器设置读写', () {
    provider.setEditorFontSize(18);
    expect(provider.editorFontSize, 18);

    provider.setEditorTheme('dark');
    expect(provider.editorTheme, 'dark');

    provider.setShowLineNumbers(false);
    expect(provider.showLineNumbers, false);

    provider.setAutoSave(true);
    expect(provider.autoSave, true);
  });

  test('buildFileTreeFromRelativePaths 构建多级目录树', () {
    final root = WorkbenchProvider.buildFileTreeFromRelativePaths([
      WebPickedFile(relativePath: 'proj/lib/a.dart', name: 'a.dart', content: ''),
      WebPickedFile(relativePath: 'proj/lib/b.dart', name: 'b.dart', content: ''),
      WebPickedFile(relativePath: 'proj/README.md', name: 'README.md', content: ''),
    ], 'proj');

    expect(root.name, 'proj');
    expect(root.isDirectory, true);
    expect(root.isExpanded, true);

    // 根有 2 个子节点：lib 目录 + README.md 文件
    expect(root.children.length, 2);

    // lib 目录
    final lib = root.children.firstWhere((n) => n.name == 'lib');
    expect(lib.isDirectory, true);
    expect(lib.path, 'lib');
    expect(lib.children.length, 2);
    expect(lib.children[0].name, 'a.dart');
    expect(lib.children[0].path, 'proj/lib/a.dart');
    expect(lib.children[1].name, 'b.dart');

    // README.md 文件
    final readme = root.children.firstWhere((n) => n.name == 'README.md');
    expect(readme.isDirectory, false);
    expect(readme.path, 'proj/README.md');
  });

  test('buildFileTreeFromRelativePaths 处理根目录文件', () {
    final root = WorkbenchProvider.buildFileTreeFromRelativePaths([
      WebPickedFile(relativePath: 'proj/main.dart', name: 'main.dart', content: ''),
      WebPickedFile(relativePath: 'proj/sub/deep/x.txt', name: 'x.txt', content: ''),
    ], 'proj');

    expect(root.children.length, 2);

    // main.dart 在根
    final main = root.children.firstWhere((n) => n.name == 'main.dart');
    expect(main.isDirectory, false);

    // sub/deep 嵌套目录
    final sub = root.children.firstWhere((n) => n.name == 'sub');
    expect(sub.children.length, 1);
    final deep = sub.children.firstWhere((n) => n.name == 'deep');
    expect(deep.children.length, 1);
    expect(deep.children[0].name, 'x.txt');
  });

  test('openWebFile 未缓存文件安全返回，不添加打开文件', () {
    final before = provider.openedFiles.length;
    provider.openWebFile('nonexistent/path.dart');
    expect(provider.openedFiles.length, before);
  });
}
