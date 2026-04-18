// test/core/services/config_service_test.dart
// ConfigService 测试 - 测试配置持久化功能

import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';
import 'package:get_it/get_it.dart';
import 'package:zzcc/core/services/config_service.dart';
import 'package:zzcc/core/services/logger_service.dart';

// Mock PathProvider for testing
class MockPathProviderPlatform extends Fake
    with MockPlatformInterfaceMixin
    implements PathProviderPlatform {
  final String tempPath;

  MockPathProviderPlatform(this.tempPath);

  @override
  Future<String?> getApplicationSupportPath() async => tempPath;

  @override
  Future<String?> getApplicationDocumentsPath() async => tempPath;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ConfigService', () {
    late Directory tempDir;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp('config_test_');
      PathProviderPlatform.instance = MockPathProviderPlatform(tempDir.path);

      // Register LoggerService in GetIt before ConfigService.init()
      // LoggerService is a singleton that initializes lazily
      if (!GetIt.instance.isRegistered<LoggerService>()) {
        final logger = LoggerService();
        GetIt.instance.registerSingleton<LoggerService>(logger);
      }
    });

    tearDown(() async {
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    test('should have default nebula config values', () async {
      final config = ConfigService();
      await config.init();

      expect(config.nebulaApiBaseUrl, contains('api/v1/'));
      expect(config.nebulaApiKey, isNotEmpty);
    });

    test('should save and retrieve chat auth', () async {
      final config = ConfigService();
      await config.init();

      await config.saveChatAuth(
        accessToken: 'test_token',
        userId: '@test:example.com',
        displayName: 'Test User',
      );

      expect(config.chatAccessToken, 'test_token');
      expect(config.chatUserId, '@test:example.com');
      expect(config.chatDisplayName, 'Test User');
    });

    test('should clear chat auth', () async {
      final config = ConfigService();
      await config.init();

      await config.saveChatAuth(
        accessToken: 'test_token',
        userId: '@test:example.com',
      );

      await config.clearChatAuth();

      expect(config.chatAccessToken, null);
      expect(config.chatUserId, null);
    });

    test('should handle null values in chat auth', () async {
      final config = ConfigService();
      await config.init();

      await config.saveChatAuth(
        accessToken: null,
        userId: 'local_uid',
        displayName: null,
      );

      expect(config.chatAccessToken, null);
      expect(config.chatUserId, 'local_uid');
      expect(config.chatDisplayName, null);
    });

    test('should update keep logged in', () async {
      final config = ConfigService();
      await config.init();

      await config.updateKeepLoggedIn(false);

      expect(config.keepLoggedIn, false);
    });

    test('should update nebula API config', () async {
      final config = ConfigService();
      await config.init();

      await config.updateNebulaApiConfig(
        'http://new-server.com/api/',
        'new-api-key',
      );

      expect(config.nebulaApiBaseUrl, 'http://new-server.com/api/');
      expect(config.nebulaApiKey, 'new-api-key');
    });

    test('should persist config across instances', () async {
      final config1 = ConfigService();
      await config1.init();
      await config1.saveChatAuth(
        accessToken: 'persisted_token',
        userId: '@persisted:example.com',
      );

      // Create new instance - should load persisted config
      final config2 = ConfigService();
      await config2.init();

      expect(config2.chatAccessToken, 'persisted_token');
      expect(config2.chatUserId, '@persisted:example.com');
    });

    test('config getter should return full config map', () async {
      final config = ConfigService();
      await config.init();

      final cfg = config.config;
      expect(cfg, isA<Map<String, dynamic>>());
    });

    test('should update splash animation setting', () async {
      final config = ConfigService();
      await config.init();

      await config.updateSplashAnimation(false);

      expect(config.enableSplashAnimation, false);
    });
  });
}
