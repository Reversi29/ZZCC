// Stub for dart:io on web — all methods throw UnsupportedError.

class Platform {
  static String get operatingSystem => throw UnsupportedError('Platform not available on web');
  static Map<String, String> get environment => {};
  static String get resolvedExecutable => throw UnsupportedError('Platform.resolvedExecutable not available on web');
}

class File {
  final String path;
  File(this.path);
  Future<bool> exists() => throw UnsupportedError('File I/O not available on web');
  Future<String> readAsString() => throw UnsupportedError('File I/O not available on web');
  Future<void> writeAsString(String s) => throw UnsupportedError('File I/O not available on web');
  Future<void> delete({bool recursive = false}) => throw UnsupportedError('File I/O not available on web');
  Future<void> copy(String newPath) => throw UnsupportedError('File I/O not available on web');
  Directory get parent => throw UnsupportedError('File.parent not available on web');
  Future<Stream<List<int>>> openRead() => throw UnsupportedError('File I/O not available on web');
}

class Directory {
  final String path;
  Directory(this.path);
  Future<bool> exists() => throw UnsupportedError('Directory I/O not available on web');
  Future<void> create({bool recursive = false}) => throw UnsupportedError('Directory I/O not available on web');
  Future<void> delete({bool recursive = false}) => throw UnsupportedError('Directory I/O not available on web');
  Future<List<FileSystemEntity>> list({bool recursive = false}) => throw UnsupportedError('Directory listing not available on web');
  Directory get parent => Directory(path.contains('/') ? path.substring(0, path.lastIndexOf('/')) : '.');
}

abstract class FileSystemEntity {
  String get path => throw UnsupportedError('not available');
}
