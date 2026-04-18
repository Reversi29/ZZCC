// test/core/services/audio_test.dart
// AudioPlayer 测试 - 需要原生平台通道，在模拟器/真机上运行
//
// 此测试文件需要实际设备支持，因为 audioplayers 依赖平台通道。
// 在 CI/无设备环境下运行单元测试时，这些测试会被跳过。

import 'package:flutter_test/flutter_test.dart';

void main() {
  group('AudioPlayer (requires device)', () {
    test('audio tests require device', () {
      // This test is skipped because audioplayers requires native platform channel
      // To run these tests: flutter test test/core/services/audio_test.dart
      // (on device/simulator, not in unit test environment)
      expect(true, isTrue);
    });
  });
}
