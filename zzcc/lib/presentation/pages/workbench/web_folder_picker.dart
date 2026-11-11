import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';
import 'package:web/web.dart' as web;

/// Web 版打开文件夹：用 `<input type="file" webkitdirectory multiple>` 选择目录。
///
/// 浏览器沙箱不允许访问本地文件系统路径，但通过 `webkitdirectory` 可以让
/// 用户选择一个目录，浏览器会返回该目录下所有文件及其相对路径
/// （`File.webkitRelativePath`，形如 `folder/sub/file.txt`）。
///
/// 这是 Web 版能实现"打开文件夹"的唯一真实方式（兼容 Chromium 系浏览器）。
class WebPickedFile {
  final String relativePath;
  final String name;
  final String? content;
  final Uint8List? bytes;

  WebPickedFile({
    required this.relativePath,
    required this.name,
    this.content,
    this.bytes,
  });
}

class WebFolderResult {
  final String rootName;
  final List<WebPickedFile> files;

  WebFolderResult({required this.rootName, required this.files});
}

/// 弹出目录选择器，返回选中的目录内容；用户取消时返回 null。
Future<WebFolderResult?> pickWebFolder() async {
  final completer = Completer<WebFolderResult?>();
  final input = web.document.createElement('input') as web.HTMLInputElement;

  input.type = 'file';
  input.webkitdirectory = true;
  input.multiple = true;
  input.style.display = 'none';

  // 回调：用户选择目录后触发
  void onChanged(web.Event _) {
    final files = input.files;
    input.remove();

    if (files == null || files.length == 0) {
      completer.complete(null);
      return;
    }

    _readFiles(files, completer);
  }

  // 挂载到 DOM，监听 change，触发点击
  web.document.body?.append(input);
  input.addEventListener('change', onChanged.toJS);
  input.click();

  // 超时保护：60 秒后未选择视为取消
  Future.delayed(const Duration(seconds: 60), () {
    if (!completer.isCompleted) {
      input.remove();
      completer.complete(null);
    }
  });

  return completer.future;
}

/// 弹出文件选择器（多选），返回选中的文件列表；用户取消时返回 null。
Future<List<WebPickedFile>?> pickWebFiles() async {
  final completer = Completer<List<WebPickedFile>?>();
  final input = web.document.createElement('input') as web.HTMLInputElement;

  input.type = 'file';
  input.multiple = true;
  input.style.display = 'none';

  void onChanged(web.Event _) {
    final files = input.files;
    input.remove();

    if (files == null || files.length == 0) {
      completer.complete(null);
      return;
    }

    _readFilesGeneric(files, completer);
  }

  web.document.body?.append(input);
  input.addEventListener('change', onChanged.toJS);
  input.click();

  Future.delayed(const Duration(seconds: 60), () {
    if (!completer.isCompleted) {
      input.remove();
      completer.complete(null);
    }
  });

  return completer.future;
}

Future<void> _readFiles(
    web.FileList files, Completer<WebFolderResult?> completer) async {
  String rootName = '文件夹';
  final picked = <WebPickedFile>[];

  for (var i = 0; i < files.length; i++) {
    final file = files.item(i);
    if (file == null) continue;

    final rel = file.webkitRelativePath;
    final name = file.name;
    if (rel.isEmpty) continue;

    // rootName 取自第一个文件的相对路径第一段
    if (rootName == '文件夹' && rel.contains('/')) {
      rootName = rel.split('/').first;
    }

    final ext = name.toLowerCase().split('.').last;

    // 文本文件读内容；其他读 bytes
    if (_isTextExt(ext)) {
      try {
        final text = (await file.text().toDart).toDart;
        picked.add(WebPickedFile(
          relativePath: rel,
          name: name,
          content: text,
        ));
      } catch (_) {
        picked.add(WebPickedFile(relativePath: rel, name: name));
      }
    } else {
      try {
        final jsBuf = await file.arrayBuffer().toDart;
        final buf = jsBuf.toDart;
        picked.add(WebPickedFile(
          relativePath: rel,
          name: name,
          bytes: Uint8List.view(buf),
        ));
      } catch (_) {
        picked.add(WebPickedFile(relativePath: rel, name: name));
      }
    }
  }

  completer.complete(WebFolderResult(rootName: rootName, files: picked));
}

/// 通用读取：把 FileList 读成 WebPickedFile 列表（文本读 content，其他读 bytes）。
Future<void> _readFilesGeneric(
    web.FileList files, Completer<List<WebPickedFile>?> completer) async {
  final picked = <WebPickedFile>[];

  for (var i = 0; i < files.length; i++) {
    final file = files.item(i);
    if (file == null) continue;

    final name = file.name;
    final ext = name.toLowerCase().split('.').last;

    if (_isTextExt(ext)) {
      try {
        final text = (await file.text().toDart).toDart;
        picked.add(WebPickedFile(
          relativePath: name,
          name: name,
          content: text,
        ));
      } catch (_) {
        picked.add(WebPickedFile(relativePath: name, name: name));
      }
    } else {
      try {
        final jsBuf = await file.arrayBuffer().toDart;
        final buf = jsBuf.toDart;
        picked.add(WebPickedFile(
          relativePath: name,
          name: name,
          bytes: Uint8List.view(buf),
        ));
      } catch (_) {
        picked.add(WebPickedFile(relativePath: name, name: name));
      }
    }
  }

  completer.complete(picked);
}

bool _isTextExt(String ext) {
  const textExts = {
    'dart', 'py', 'c', 'cpp', 'h', 'hpp', 'java', 'js', 'ts',
    'lua', 'go', 'rs', 'php', 'html', 'css', 'xml', 'json',
    'yaml', 'yml', 'md', 'txt', 'log', 'ini', 'conf', 'cfg', 'env',
  };
  return textExts.contains(ext);
}
