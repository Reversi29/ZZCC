// test/data/models/chat_room_test.dart
// ChatRoom 模型测试

import 'package:flutter_test/flutter_test.dart';
import 'package:zzcc/data/models/chat_room.dart';

void main() {
  group('ChatRoom', () {
    test('should create ChatRoom with required fields', () {
      final room = ChatRoom(roomId: '!test:example.com');

      expect(room.roomId, '!test:example.com');
      expect(room.name, null);
      expect(room.topic, null);
      expect(room.isDirect, false);
      expect(room.unreadCount, 0);
    });

    test('should create ChatRoom with all fields', () {
      final room = ChatRoom(
        roomId: '!test:example.com',
        name: 'Test Room',
        topic: 'A test room',
        isDirect: false,
        lastMessage: 'Hello',
        lastMessageTimestamp: 1704067200000,
        unreadCount: 2,
      );

      expect(room.roomId, '!test:example.com');
      expect(room.name, 'Test Room');
      expect(room.topic, 'A test room');
      expect(room.isDirect, false);
      expect(room.lastMessage, 'Hello');
      expect(room.lastMessageTimestamp, 1704067200000);
      expect(room.unreadCount, 2);
    });

    test('should deserialize from JSON', () {
      final json = {
        'roomId': '!test:example.com',
        'name': 'Test Room',
        'topic': 'A test room',
        'isDirect': true,
        'unreadCount': 5,
      };

      final room = ChatRoom.fromJson(json);

      expect(room.roomId, '!test:example.com');
      expect(room.name, 'Test Room');
      expect(room.isDirect, true);
      expect(room.unreadCount, 5);
    });

    test('should deserialize from Matrix response', () {
      final response = {
        'room_id': '!test:example.com',
        'name': 'Test Room',
        'topic': 'A test room',
      };

      final room = ChatRoom.fromMatrixResponse(response);

      expect(room.roomId, '!test:example.com');
      expect(room.name, 'Test Room');
      expect(room.topic, 'A test room');
    });

    test('should handle missing optional fields in Matrix response', () {
      final response = {
        'room_id': '!test:example.com',
      };

      final room = ChatRoom.fromMatrixResponse(response);

      expect(room.roomId, '!test:example.com');
      expect(room.name, null);
      expect(room.topic, null);
    });

    test('displayName should return name when available', () {
      final room = ChatRoom(
        roomId: '!test:example.com',
        name: 'Test Room',
      );

      expect(room.displayName, 'Test Room');
    });

    test('displayName should return localpart when no name', () {
      final room = ChatRoom(roomId: '!roomid123:example.com');

      expect(room.displayName, 'roomid123');
    });

    test('displayName should return full roomId when no match', () {
      final room = ChatRoom(roomId: 'invalid_room_id');

      expect(room.displayName, 'invalid_room_id');
    });

    test('should support equality based on roomId', () {
      final room1 = ChatRoom(roomId: '!test:example.com', name: 'Room 1');
      final room2 = ChatRoom(roomId: '!test:example.com', name: 'Room 2');
      final room3 = ChatRoom(roomId: '!other:example.com');

      expect(room1 == room2, true); // Same roomId
      expect(room1 == room3, false);
    });

    test('copyWith should create updated copy', () {
      final room = ChatRoom(
        roomId: '!test:example.com',
        name: 'Old Name',
        unreadCount: 0,
      );

      final updated = room.copyWith(name: 'New Name', unreadCount: 5);

      expect(updated.roomId, '!test:example.com');
      expect(updated.name, 'New Name');
      expect(updated.unreadCount, 5);
    });
  });
}
