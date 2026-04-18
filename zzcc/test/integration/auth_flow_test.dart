// test/integration/auth_flow_test.dart
// 认证流程集成测试

import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';
import 'package:zzcc/data/repositories/chat_repository.dart';
import 'package:zzcc/data/sources/chat_remote_source.dart';
import 'package:zzcc/data/models/chat_user.dart';
import 'package:zzcc/core/services/config_service.dart';
import 'auth_flow_test.mocks.dart';

@GenerateMocks([ChatRemoteSource, ConfigService])
void main() {
  group('Auth Flow Integration', () {
    late ChatRepositoryImpl repository;
    late MockChatRemoteSource mockRemote;
    late MockConfigService mockConfig;

    setUp(() {
      mockConfig = MockConfigService();
      mockRemote = MockChatRemoteSource();

      when(mockRemote.config).thenReturn(mockConfig);
      when(mockConfig.chatAccessToken).thenReturn(null);
      when(mockConfig.chatUserId).thenReturn(null);
      when(mockConfig.chatDisplayName).thenReturn(null);

      repository = ChatRepositoryImpl(remoteSource: mockRemote);
    });

    test('complete flow: offline register -> online login with sync', () async {
      // Step 1: Register when server is unreachable
      when(mockRemote.register(
        username: anyNamed('username'),
        password: anyNamed('password'),
        displayName: anyNamed('displayName'),
      )).thenAnswer((_) async => null);

      when(mockConfig.saveChatAuth(
        accessToken: anyNamed('accessToken'),
        userId: anyNamed('userId'),
        displayName: anyNamed('displayName'),
      )).thenAnswer((_) async {});

      final localUid = 'local_abc123';
      final password = 'test_pass';

      final localUser = await repository.register(
        uid: localUid,
        password: password,
        displayName: 'Test User',
      );

      expect(localUser, isNotNull);
      expect(localUser!.userId, localUid);
      expect(localUser.needsSync, true);
      expect(repository.isAuthenticated, true);

      // Step 2: Login when server is reachable
      // First login attempt returns 403 (account not on server)
      when(mockRemote.login(
        username: localUid,
        password: password,
      )).thenThrow(ChatApiException('Not found', statusCode: 403));

      // Sync account succeeds
      final serverUser = ChatUser(
        userId: '@test:example.com',
        displayName: 'Test User',
        accessToken: 'server_token',
        needsSync: false,
      );

      when(mockRemote.syncAccount(
        localUid: localUid,
        password: password,
        displayName: anyNamed('displayName'),
      )).thenAnswer((_) async => serverUser);

      final loggedInUser = await repository.login(
        username: localUid,
        password: password,
        displayName: 'Test User',
      );

      expect(loggedInUser, isNotNull);
      expect(loggedInUser!.userId, '@test:example.com');
      expect(loggedInUser.needsSync, false);
      expect(repository.isAuthenticated, true);
    });

    test('flow: server register -> direct login', () async {
      final serverUser = ChatUser(
        userId: '@server:example.com',
        displayName: 'Server User',
        accessToken: 'token123',
        needsSync: false,
      );

      // Register on server
      when(mockRemote.register(
        username: anyNamed('username'),
        password: anyNamed('password'),
        displayName: anyNamed('displayName'),
      )).thenAnswer((_) async => serverUser);

      final registered = await repository.register(
        uid: 'local_uid',
        password: 'pass',
        displayName: 'Server User',
      );

      expect(registered!.userId, '@server:example.com');
      expect(registered.needsSync, false);

      // Direct login (no sync needed)
      when(mockRemote.login(
        username: '@server:example.com',
        password: 'pass',
      )).thenAnswer((_) async => serverUser);

      final loggedIn = await repository.login(
        username: '@server:example.com',
        password: 'pass',
      );

      expect(loggedIn!.userId, '@server:example.com');
    });

    test('flow: sync when account already exists on server', () async {
      final localUid = 'existing_local';
      final password = 'pass';

      // Login returns 403
      when(mockRemote.login(
        username: localUid,
        password: password,
      )).thenThrow(ChatApiException('Not found', statusCode: 403));

      // Sync returns existing account (was_created: false)
      final existingUser = ChatUser(
        userId: '@existing:example.com',
        displayName: 'Existing User',
        accessToken: 'existing_token',
        needsSync: false,
      );

      when(mockRemote.syncAccount(
        localUid: localUid,
        password: password,
        displayName: anyNamed('displayName'),
      )).thenAnswer((_) async => existingUser);

      final result = await repository.login(
        username: localUid,
        password: password,
        displayName: 'Test',
      );

      expect(result!.userId, '@existing:example.com');
      expect(result.needsSync, false);
    });

    test('auth state stream should emit during login/logout', () async {
      final states = <bool>[];
      repository.authStateStream.listen(states.add);

      // Login
      when(mockRemote.login(
        username: anyNamed('username'),
        password: anyNamed('password'),
      )).thenAnswer((_) async => ChatUser(
        userId: '@test:example.com',
        accessToken: 'token',
        needsSync: false,
      ));

      await repository.login(username: 'test', password: 'pass');

      // Logout
      when(mockRemote.logout()).thenAnswer((_) async {});
      await repository.logout();

      // Give time for stream to emit
      await Future.delayed(Duration.zero);

      expect(states, contains(true));
      expect(states, contains(false));
    });
  });
}
