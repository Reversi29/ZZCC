// lib/core/di/service_locator.dart
import 'package:get_it/get_it.dart';
import 'package:zzcc/core/services/logger_service.dart';
import 'package:zzcc/core/services/net_service.dart';
import 'package:zzcc/core/services/torrent_service.dart';
import 'package:zzcc/data/repositories/file_repository.dart';
import 'package:zzcc/presentation/providers/workbench_provider.dart';
import 'package:zzcc/core/services/audio_analysis_service.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:event_bus/event_bus.dart';
import 'package:zzcc/core/services/config_service.dart';
import 'package:zzcc/core/services/torrent_metadata_service.dart';

final getIt = GetIt.instance;

Future<void> setupServiceLocator() async {
  getIt.registerSingleton<EventBus>(EventBus());
  getIt.registerLazySingleton<LoggerService>(() => LoggerService());
  // getIt.registerLazySingleton<StorageService>(() => StorageService()); 
  getIt.registerLazySingleton<TorrentService>(() => TorrentServiceImpl());
  getIt.registerSingleton<TorrentMetadataService>(TorrentMetadataService(getIt<LoggerService>()));
  getIt.registerLazySingleton<ApiService>(() => ApiServiceImpl());
  getIt.registerLazySingleton<FileRepository>(() => FileRepositoryImpl());
  getIt.registerLazySingleton(() => WorkbenchProvider());
  getIt.registerLazySingleton(() => AudioAnalysisService());
  
  // 添加配置服务
  final configService = ConfigService();
  await configService.init();
  getIt.registerSingleton<ConfigService>(configService);
  
  // 初始化并注册存储服务
  final storageService = StorageService();
  await storageService.init(configService.appDataPath);
  getIt.registerSingleton<StorageService>(storageService);
}