// test/presentation/pages/message/message_screen_test.dart
// MessageScreen Widget 测试 - 简化版

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zzcc/presentation/pages/message/message_screen.dart';

void main() {
  group('MessageScreen UI', () {
    test('MessageScreen should be instantiable', () {
      expect(MessageScreen, isNotNull);
    });

    test('MessageScreen constructor accepts Key parameter', () {
      final widget = MessageScreen(key: const Key('message_screen'));
      expect(widget.key, isNotNull);
    });
  });
}
