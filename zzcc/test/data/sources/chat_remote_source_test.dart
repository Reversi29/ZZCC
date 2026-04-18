// test/data/sources/chat_remote_source_test.dart
// ChatRemoteSource 测试

import 'package:flutter_test/flutter_test.dart';
import 'package:dio/dio.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';
import 'package:zzcc/data/sources/chat_remote_source.dart';
import 'package:zzcc/core/services/config_service.dart';

import 'chat_remote_source_test.mocks.dart';

@GenerateMocks([Dio, ConfigService])
void main() {
  late ChatRemoteSource source;
  late MockDio mockDio;
  late MockConfigService mockConfig;

  setUp(() {
    mockDio = MockDio();
    mockConfig = MockConfigService();

    when(mockConfig.nebulaApiBaseUrl).thenReturn('http://test.com/api/v1/');
    when(mockConfig.nebulaApiKey).thenReturn('test_key');
    when(mockConfig.chatAccessToken).thenReturn(null);

    source = ChatRemoteSource(dio: mockDio, config: mockConfig);
  });

  group('Authentication', () {
    test('register success should return user', () async {
      final response = Response(
        data: {
          'data': {
            'user_id': '@test:example.com',
            'display_name': 'Test User',
            'access_token': 'token123',
          }
        },
        statusCode: 201,
        requestOptions: RequestOptions(),
      );

      when(mockDio.post(
        '/chat/register',
        data: anyNamed('data'),
      )).thenAnswer((_) async => response);

      final result = await source.register(
        username: 'test',
        password: 'pass',
        displayName: 'Test User',
      );

      expect(result, isNotNull);
      expect(result!.userId, '@test:example.com');
      expect(source.isAuthenticated, true);
    });

    test('register network failure should return null', () async {
      when(mockDio.post(
        '/chat/register',
        data: anyNamed('data'),
      )).thenThrow(DioException(
        requestOptions: RequestOptions(),
        type: DioExceptionType.connectionTimeout,
      ));

      final result = await source.register(
        username: 'test',
        password: 'pass',
      );

      expect(result, null);
      expect(source.isAuthenticated, false);
    });

    test('login success should return user', () async {
      final response = Response(
        data: {
          'data': {
            'user_id': '@test:example.com',
            'display_name': 'Test User',
            'access_token': 'token123',
          }
        },
        statusCode: 200,
        requestOptions: RequestOptions(),
      );

      when(mockDio.post(
        '/chat/login',
        data: anyNamed('data'),
      )).thenAnswer((_) async => response);

      final result = await source.login(
        username: 'test',
        password: 'pass',
      );

      expect(result, isNotNull);
      expect(result!.accessToken, 'token123');
    });

    test('login 403 should throw ChatApiException', () async {
      when(mockDio.post(
        '/chat/login',
        data: anyNamed('data'),
      )).thenThrow(DioException(
        requestOptions: RequestOptions(),
        response: Response(
          statusCode: 403,
          requestOptions: RequestOptions(),
        ),
      ));

      expect(
        () => source.login(username: 'test', password: 'pass'),
        throwsA(isA<ChatApiException>()),
      );
    });

    test('syncAccount success should return user', () async {
      final response = Response(
        data: {
          'data': {
            'user_id': '@synced:example.com',
            'display_name': 'Synced User',
            'access_token': 'new_token',
            'was_created': true,
          }
        },
        statusCode: 201,
        requestOptions: RequestOptions(),
      );

      when(mockDio.post(
        '/chat/sync-account',
        data: anyNamed('data'),
      )).thenAnswer((_) async => response);

      final result = await source.syncAccount(
        localUid: 'local_123',
        password: 'pass',
        displayName: 'Test',
      );

      expect(result, isNotNull);
      expect(result!.userId, '@synced:example.com');
      expect(result.needsSync, false);
    });

    test('logout should clear token', () async {
      // First login to set token
      source.setAccessToken('test_token');
      expect(source.isAuthenticated, true);

      when(mockDio.post(
        '/chat/logout',
        options: anyNamed('options'),
      )).thenAnswer((_) async => Response(
        data: {},
        statusCode: 200,
        requestOptions: RequestOptions(),
      ));

      await source.logout();

      expect(source.isAuthenticated, false);
    });
  });

  group('Token Management', () {
    test('setAccessToken should update authentication state', () {
      expect(source.isAuthenticated, false);

      source.setAccessToken('new_token');

      expect(source.isAuthenticated, true);
      expect(source.accessToken, 'new_token');
    });

    test('setAccessToken with null should clear authentication', () {
      source.setAccessToken('token');
      expect(source.isAuthenticated, true);

      source.setAccessToken(null);

      expect(source.isAuthenticated, false);
    });
  });

  group('Rooms', () {
    test('getRooms without auth should throw', () async {
      expect(
        () => source.getRooms(),
        throwsA(isA<ChatApiException>()),
      );
    });

    test('getRooms with auth should return rooms', () async {
      source.setAccessToken('valid_token');

      final response = Response(
        data: {
          'data': {
            'rooms': [
              {'room_id': '!room1:example.com', 'name': 'Room 1'},
              {'room_id': '!room2:example.com', 'name': 'Room 2'},
            ],
          }
        },
        statusCode: 200,
        requestOptions: RequestOptions(),
      );

      when(mockDio.get(
        '/chat/rooms',
        options: anyNamed('options'),
      )).thenAnswer((_) async => response);

      final result = await source.getRooms();

      expect(result.length, 2);
    });
  });

  group('Config Access', () {
    test('config getter should return config service', () {
      expect(source.config, mockConfig);
    });
  });
}
