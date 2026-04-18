// test/data/models/chat_message_test.dart
// ChatMessage 模型测试

import 'package:flutter_test/flutter_test.dart';
import 'package:zzcc/data/models/chat_message.dart';

void main() {
  group('ChatMessage', () {
    test('should create ChatMessage with required fields', () {
      final message = ChatMessage(
        eventId: '\$event123',
        sender: '@user:example.com',
        timestamp: 1704067200000,
        body: 'Hello World',
      );

      expect(message.eventId, '\$event123');
      expect(message.sender, '@user:example.com');
      expect(message.timestamp, 1704067200000);
      expect(message.body, 'Hello World');
      expect(message.msgtype, 'm.text'); // default
      expect(message.isMe, false); // default
    });

    test('should create ChatMessage with all fields', () {
      final message = ChatMessage(
        eventId: '\$event123',
        sender: '@user:example.com',
        timestamp: 1704067200000,
        msgtype: 'm.image',
        body: 'Image description',
        formattedBody: '<b>Bold</b> text',
        isMe: true,
      );

      expect(message.msgtype, 'm.image');
      expect(message.formattedBody, '<b>Bold</b> text');
      expect(message.isMe, true);
    });

    test('should deserialize from JSON', () {
      final json = {
        'eventId': '\$event123',
        'sender': '@user:example.com',
        'timestamp': 1704067200000,
        'msgtype': 'm.text',
        'body': 'Hello World',
        'isMe': false,
      };

      final message = ChatMessage.fromJson(json);

      expect(message.eventId, '\$event123');
      expect(message.sender, '@user:example.com');
      expect(message.body, 'Hello World');
    });

    test('should deserialize from Matrix response', () {
      final response = {
        'event_id': '\$event123',
        'sender': '@user:example.com',
        'timestamp': 1704067200000,
        'msgtype': 'm.text',
        'body': 'Hello World',
      };

      final message = ChatMessage.fromMatrixResponse(response);

      expect(message.eventId, '\$event123');
      expect(message.sender, '@user:example.com');
      expect(message.body, 'Hello World');
    });

    test('should handle different message types', () {
      final textMsg = ChatMessage(
        eventId: '\$1',
        sender: '@user:example.com',
        timestamp: 1704067200000,
        body: 'Text',
        msgtype: 'm.text',
      );

      final imageMsg = ChatMessage(
        eventId: '\$2',
        sender: '@user:example.com',
        timestamp: 1704067200000,
        body: 'Image',
        msgtype: 'm.image',
      );

      expect(textMsg.msgtype, 'm.text');
      expect(imageMsg.msgtype, 'm.image');
    });

    test('senderDisplayName should return localpart', () {
      final message = ChatMessage(
        eventId: '\$1',
        sender: '@testuser:example.com',
        timestamp: 1704067200000,
        body: 'Hello',
      );

      expect(message.senderDisplayName, 'testuser');
    });

    test('senderDisplayName should return full sender when no match', () {
      final message = ChatMessage(
        eventId: '\$1',
        sender: 'invalid_sender',
        timestamp: 1704067200000,
        body: 'Hello',
      );

      expect(message.senderDisplayName, 'invalid_sender');
    });

    test('should support equality based on eventId', () {
      final msg1 = ChatMessage(
        eventId: '\$event123',
        sender: '@a:example.com',
        timestamp: 1,
        body: 'A',
      );
      final msg2 = ChatMessage(
        eventId: '\$event123',
        sender: '@b:example.com',
        timestamp: 2,
        body: 'B',
      );

      expect(msg1 == msg2, true); // Same eventId
    });

    test('copyWith should create updated copy', () {
      final message = ChatMessage(
        eventId: '\$event123',
        sender: '@user:example.com',
        timestamp: 1704067200000,
        body: 'Old body',
      );

      final updated = message.copyWith(body: 'New body', isMe: true);

      expect(updated.eventId, '\$event123');
      expect(updated.body, 'New body');
      expect(updated.isMe, true);
    });
  });
}
