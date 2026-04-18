// test/data/repositories/chat_repository_test.dart
// ChatRepository 测试（使用 mock）

import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';
import 'package:zzcc/data/repositories/chat_repository.dart';
import 'package:zzcc/data/sources/chat_remote_source.dart';
import 'package:zzcc/data/models/chat_user.dart';
import 'package:zzcc/data/models/chat_room.dart';
import 'package:zzcc/core/services/config_service.dart';

import 'chat_repository_test.mocks.dart';

@GenerateMocks([ChatRemoteSource, ConfigService])
void main() {
  late ChatRepositoryImpl repository;
  late MockChatRemoteSource mockRemoteSource;
  late MockConfigService mockConfig;

  setUp(() {
    mockConfig = MockConfigService();
    mockRemoteSource = MockChatRemoteSource();

    // Stub the config property
    when(mockRemoteSource.config).thenReturn(mockConfig);
    when(mockConfig.chatAccessToken).thenReturn(null);
    when(mockConfig.chatUserId).thenReturn(null);
    when(mockConfig.chatDisplayName).thenReturn(null);

    repository = ChatRepositoryImpl(remoteSource: mockRemoteSource);
  });

  group('Authentication', () {
    test('initial state should not be authenticated', () {
      expect(repository.isAuthenticated, false);
      expect(repository.currentUser, null);
    });

    test('register with server success should set user', () async {
      final serverUser = ChatUser(
        userId: '@test:example.com',
        displayName: 'Test',
        accessToken: 'token123',
        needsSync: false,
      );

      when(mockRemoteSource.register(
        username: 'local_uid',
        password: 'pass123',
        displayName: 'Test',
      )).thenAnswer((_) async => serverUser);

      final result = await repository.register(
        uid: 'local_uid',
        password: 'pass123',
        displayName: 'Test',
      );

      expect(result, isNotNull);
      expect(result!.userId, '@test:example.com');
      expect(repository.isAuthenticated, true);
    });

    test('register with server unreachable should create local user', () async {
      when(mockRemoteSource.register(
        username: anyNamed('username'),
        password: anyNamed('password'),
        displayName: anyNamed('displayName'),
      )).thenAnswer((_) async => null);

      when(mockRemoteSource.config).thenReturn(mockConfig);
      when(mockConfig.saveChatAuth(
        accessToken: anyNamed('accessToken'),
        userId: anyNamed('userId'),
        displayName: anyNamed('displayName'),
      )).thenAnswer((_) async {});

      final result = await repository.register(
        uid: 'local_uid_123',
        password: 'pass123',
        displayName: 'Test',
      );

      expect(result, isNotNull);
      expect(result!.userId, 'local_uid_123');
      expect(result.needsSync, true);
      expect(repository.isAuthenticated, true);
    });

    test('login success should set user', () async {
      final serverUser = ChatUser(
        userId: '@test:example.com',
        accessToken: 'token123',
        needsSync: false,
      );

      when(mockRemoteSource.login(
        username: 'test',
        password: 'pass123',
      )).thenAnswer((_) async => serverUser);

      final result = await repository.login(
        username: 'test',
        password: 'pass123',
      );

      expect(result, isNotNull);
      expect(repository.isAuthenticated, true);
    });

    test('login with 403 should trigger syncAccount', () async {
      when(mockRemoteSource.login(
        username: 'local_uid',
        password: 'pass123',
      )).thenThrow(ChatApiException('Not found', statusCode: 403));

      final syncedUser = ChatUser(
        userId: '@synced:example.com',
        accessToken: 'new_token',
        needsSync: false,
      );

      when(mockRemoteSource.syncAccount(
        localUid: 'local_uid',
        password: 'pass123',
        displayName: anyNamed('displayName'),
      )).thenAnswer((_) async => syncedUser);

      final result = await repository.login(
        username: 'local_uid',
        password: 'pass123',
        displayName: 'Test',
      );

      expect(result, isNotNull);
      expect(result!.userId, '@synced:example.com');
    });

    test('logout should clear user', () async {
      // Setup authenticated state
      when(mockRemoteSource.login(
        username: 'test',
        password: 'pass',
      )).thenAnswer((_) async => ChatUser(
        userId: '@test:example.com',
        accessToken: 'token',
        needsSync: false,
      ));

      await repository.login(username: 'test', password: 'pass');
      expect(repository.isAuthenticated, true);

      // Logout
      when(mockRemoteSource.logout()).thenAnswer((_) async {});
      await repository.logout();

      expect(repository.isAuthenticated, false);
      expect(repository.currentUser, null);
    });
  });

  group('Rooms', () {
    test('getRooms should return list of rooms', () async {
      final rooms = [
        ChatRoom(roomId: '!room1:example.com', name: 'Room 1'),
        ChatRoom(roomId: '!room2:example.com', name: 'Room 2'),
      ];

      when(mockRemoteSource.getRooms()).thenAnswer((_) async => rooms);

      final result = await repository.getRooms();

      expect(result.length, 2);
      expect(result[0].roomId, '!room1:example.com');
    });

    test('createRoom should return created room', () async {
      final newRoom = ChatRoom(
        roomId: '!new:example.com',
        name: 'New Room',
      );

      when(mockRemoteSource.createRoom(
        name: 'New Room',
        topic: anyNamed('topic'),
        invite: anyNamed('invite'),
        isDirect: anyNamed('isDirect'),
      )).thenAnswer((_) async => newRoom);

      final result = await repository.createRoom(name: 'New Room');

      expect(result.roomId, '!new:example.com');
    });
  });

  group('Auth State Stream', () {
    test('should emit auth state changes', () async {
      // Listen before the operation so we don't miss the event
      final states = <bool>[];
      final subscription = repository.authStateStream.listen(states.add);

      when(mockRemoteSource.login(
        username: 'test',
        password: 'pass',
      )).thenAnswer((_) async => ChatUser(
        userId: '@test:example.com',
        accessToken: 'token',
        needsSync: false,
      ));

      await repository.login(username: 'test', password: 'pass');

      // Give time for stream to emit
      await Future.delayed(Duration.zero);

      expect(states, contains(true));

      // Cleanup
      await subscription.cancel();
    });

    test('should emit false on logout', () async {
      // First login to set authenticated state
      when(mockRemoteSource.login(
        username: 'test',
        password: 'pass',
      )).thenAnswer((_) async => ChatUser(
        userId: '@test:example.com',
        accessToken: 'token',
        needsSync: false,
      ));
      await repository.login(username: 'test', password: 'pass');

      // Now listen for logout event
      final states = <bool>[];
      repository.authStateStream.listen(states.add);

      when(mockRemoteSource.logout()).thenAnswer((_) async {});
      await repository.logout();

      // Give time for stream to emit
      await Future.delayed(Duration.zero);

      expect(states, contains(false));
    });
  });

  group('Session Restore', () {
    test('should restore server session from config', () {
      final mockConfig2 = MockConfigService();
      when(mockConfig2.chatAccessToken).thenReturn('saved_token');
      when(mockConfig2.chatUserId).thenReturn('@saved:example.com');
      when(mockConfig2.chatDisplayName).thenReturn('Saved User');

      final mockRemote2 = MockChatRemoteSource();
      when(mockRemote2.config).thenReturn(mockConfig2);

      final repo = ChatRepositoryImpl(remoteSource: mockRemote2);

      expect(repo.isAuthenticated, true);
      expect(repo.currentUser?.userId, '@saved:example.com');
      expect(repo.currentUser?.needsSync, false);
    });

    test('should restore local session from config', () {
      final mockConfig2 = MockConfigService();
      when(mockConfig2.chatAccessToken).thenReturn(null);
      when(mockConfig2.chatUserId).thenReturn('local_uid');
      when(mockConfig2.chatDisplayName).thenReturn('Local User');

      final mockRemote2 = MockChatRemoteSource();
      when(mockRemote2.config).thenReturn(mockConfig2);

      final repo = ChatRepositoryImpl(remoteSource: mockRemote2);

      expect(repo.isAuthenticated, true);
      expect(repo.currentUser?.userId, 'local_uid');
      expect(repo.currentUser?.needsSync, true);
    });
  });
}
