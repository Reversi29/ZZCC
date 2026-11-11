import 'dart:typed_data';

/// 非 Web 平台的 stub 实现：Web 版打开文件夹在非 Web 平台不可用。
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

/// 非 Web 平台返回 null（openFolder 只在 kIsWeb 分支调用，非 Web 不会真调）。
Future<WebFolderResult?> pickWebFolder() async => null;

/// 非 Web 平台返回 null（openFile 只在 kIsWeb 分支调用，非 Web 不会真调）。
Future<List<WebPickedFile>?> pickWebFiles() async => null;
