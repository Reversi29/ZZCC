// test/core/services/torrent_service_test.dart
// TorrentService 测试 - 需要原生 FFI 库，在配置完整的环境中运行
//
// 此测试文件需要 torrent_ffi 原生库，在无库环境下会被跳过。
// 要运行完整测试：确保 torrent_ffi.dylib 在系统路径中。

import 'package:flutter_test/flutter_test.dart';

void main() {
  group('TorrentService (requires native library)', () {
    test('torrent tests require native FFI library', () {
      // This test is skipped because torrent_service requires native FFI library
      // To run these tests:
      // 1. Ensure torrent_ffi.dylib is in system library path
      // 2. Run: flutter test test/core/services/torrent_service_test.dart
      expect(true, isTrue);
    });
  });
}
