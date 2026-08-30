import 'dart:io';

/// Native-compatible helpers for desktop/mobile file-system features.
abstract class FsHelper {
  static String get pathSeparator => Platform.pathSeparator;


  static bool fileExistsSync(String path) => File(path).existsSync();
  static Future<bool> fileExists(String path) async => File(path).exists();

  static bool directoryExistsSync(String path) => Directory(path).existsSync();
  static Future<bool> directoryExists(String path) async => Directory(path).exists();

  static bool existsSync(String path) => File(path).existsSync() || Directory(path).existsSync();
  static Future<bool> exists(String path) async =>
      await File(path).exists() || await Directory(path).exists();

  static Future<void> deleteEntity(String path, {bool recursive = false}) async {
    if (await File(path).exists()) {
      await File(path).delete();
    } else if (await Directory(path).exists()) {
      await Directory(path).delete(recursive: recursive);
    }
  }

  static Future<void> deleteEntitySyncSafe(String path, {bool recursive = false}) async {
    if (File(path).existsSync()) {
      File(path).deleteSync();
    } else if (Directory(path).existsSync()) {
      Directory(path).deleteSync(recursive: recursive);
    }
  }
}
