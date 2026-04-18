// test/data/models/chat_user_test.dart
// ChatUser 模型测试

import 'package:flutter_test/flutter_test.dart';
import 'package:zzcc/data/models/chat_user.dart';

void main() {
  group('ChatUser', () {
    test('should create ChatUser with all fields', () {
      final user = ChatUser(
        userId: '@test:example.com',
        displayName: 'Test User',
        avatarUrl: 'https://example.com/avatar.png',
        accessToken: 'token123',
        deviceId: 'device123',
        homeServer: 'example.com',
        needsSync: false,
      );

      expect(user.userId, '@test:example.com');
      expect(user.displayName, 'Test User');
      expect(user.avatarUrl, 'https://example.com/avatar.png');
      expect(user.accessToken, 'token123');
      expect(user.deviceId, 'device123');
      expect(user.homeServer, 'example.com');
      expect(user.needsSync, false);
    });

    test('isAuthenticated should be true when has token', () {
      final user = ChatUser(
        userId: '@test:example.com',
        accessToken: 'valid_token',
        needsSync: false,
      );

      expect(user.isAuthenticated, true);
    });

    test('isAuthenticated should be true when needsSync', () {
      final user = ChatUser(
        userId: 'local_uid_123',
        accessToken: null,
        needsSync: true,
      );

      expect(user.isAuthenticated, true);
    });

    test('isAuthenticated should be false when no token and no needsSync', () {
      final user = ChatUser(
        userId: '',
        accessToken: null,
        needsSync: false,
      );

      expect(user.isAuthenticated, false);
    });

    test('should serialize to JSON', () {
      final user = ChatUser(
        userId: '@test:example.com',
        displayName: 'Test User',
        accessToken: 'token123',
        needsSync: true,
      );

      final json = user.toJson();

      expect(json['userId'], '@test:example.com');
      expect(json['displayName'], 'Test User');
      expect(json['accessToken'], 'token123');
      expect(json['needsSync'], true);
    });

    test('should not include null values in JSON', () {
      final user = ChatUser(
        userId: '@test:example.com',
        needsSync: false,
      );

      final json = user.toJson();

      expect(json.containsKey('displayName'), false);
      expect(json.containsKey('accessToken'), false);
      expect(json.containsKey('needsSync'), false); // false is default, not included
    });

    test('should deserialize from JSON', () {
      final json = {
        'userId': '@test:example.com',
        'displayName': 'Test User',
        'accessToken': 'token123',
        'needsSync': true,
      };

      final user = ChatUser.fromJson(json);

      expect(user.userId, '@test:example.com');
      expect(user.displayName, 'Test User');
      expect(user.accessToken, 'token123');
      expect(user.needsSync, true);
    });

    test('should deserialize from auth response', () {
      final response = {
        'user_id': '@test:example.com',
        'access_token': 'token123',
        'device_id': 'device123',
        'home_server': 'example.com',
      };

      final user = ChatUser.fromAuthResponse(response);

      expect(user.userId, '@test:example.com');
      expect(user.accessToken, 'token123');
      expect(user.deviceId, 'device123');
      expect(user.homeServer, 'example.com');
      expect(user.needsSync, false);
    });

    test('copyWith should create updated copy', () {
      final user = ChatUser(
        userId: '@test:example.com',
        displayName: 'Old Name',
        accessToken: 'token123',
        needsSync: false,
      );

      final updated = user.copyWith(displayName: 'New Name');

      expect(updated.userId, '@test:example.com');
      expect(updated.displayName, 'New Name');
      expect(updated.accessToken, 'token123');
    });

    test('displayNameOrId should return display name when available', () {
      final user = ChatUser(
        userId: '@testuser:example.com',
        displayName: 'Test User',
      );

      expect(user.displayNameOrId, 'Test User');
    });

    test('displayNameOrId should return localpart when no display name', () {
      final user = ChatUser(
        userId: '@testuser:example.com',
      );

      expect(user.displayNameOrId, 'testuser');
    });

    test('should support equality', () {
      final user1 = ChatUser(userId: '@test:example.com', accessToken: 'token');
      final user2 = ChatUser(userId: '@test:example.com', accessToken: 'token');
      final user3 = ChatUser(userId: '@other:example.com', accessToken: 'token');

      expect(user1 == user2, true);
      expect(user1 == user3, false);
    });
  });
}
