// lib/presentation/providers/shared_file_settings_provider.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/data/models/shared_file_settings_model.dart';
import 'package:zzcc/data/repositories/shared_file_settings_repository.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/services/storage_service.dart';

// 1. 异步加载设置
final sharedFileSettingsFutureProvider = FutureProvider<SharedFileSettingsModel>((ref) async {
  final storageService = getIt<StorageService>();
  final repository = SharedFileSettingsRepository(storageService);
  return await repository.getSettings();
});

// 2. 定义 StateNotifierProvider
final sharedFileSettingsNotifierProvider = StateNotifierProvider<SharedFileSettingsNotifier, SharedFileSettingsModel>((ref) {
  final repository = SharedFileSettingsRepository(getIt<StorageService>());
  return SharedFileSettingsNotifier(repository);
});

// 3. 便捷 Provider：直接获取状态
final sharedFileSettingsProvider = Provider<SharedFileSettingsModel>((ref) {
  return ref.watch(sharedFileSettingsNotifierProvider);
});

class SharedFileSettingsNotifier extends StateNotifier<SharedFileSettingsModel> {
  final SharedFileSettingsRepository _repository;

  SharedFileSettingsNotifier(this._repository) : super(SharedFileSettingsModel()) {
    // 初始化时加载保存的设置
    _loadSettings();
  }

  // 从本地存储加载设置
  Future<void> _loadSettings() async {
    try {
      final settings = await _repository.getSettings();
      state = settings;
    } catch (e) {
      // 加载失败时使用默认值
      state = SharedFileSettingsModel();
    }
  }

  // 更新方法 - 操作 state 对象并同步到本地存储
  Future<void> updateIsManualMode(bool value) async {
    state = state.copyWith(isManualMode: value);
    await _repository.updateSettingField('isManualMode', value);
  }

  Future<void> updateUseDifferentIncompletePath(bool value) async {
    state = state.copyWith(useDifferentIncompletePath: value);
    await _repository.updateSettingField('useDifferentIncompletePath', value);
  }

  Future<void> updateRememberLastPath(bool value) async {
    state = state.copyWith(rememberLastPath: value);
    await _repository.updateSettingField('rememberLastPath', value);
  }

  Future<void> updateLastUsedPath(String? path) async {
    state = state.copyWith(lastUsedPath: path);
    await _repository.updateSettingField('lastUsedPath', path);
  }

  Future<void> updateIncompleteTorrentPath(String? path) async {
    state = state.copyWith(incompleteTorrentPath: path);
    await _repository.updateSettingField('incompleteTorrentPath', path);
  }

  Future<void> updateDefaultSavePath(String? path) async {
    state = state.copyWith(defaultSavePath: path);
    await _repository.updateSettingField('defaultSavePath', path);
  }

  Future<void> updateMaxDownloadSpeed(String speed) async {
    state = state.copyWith(maxDownloadSpeed: speed);
    await _repository.updateSettingField('maxDownloadSpeed', speed);
  }

  Future<void> updateMaxUploadSpeed(String speed) async {
    state = state.copyWith(maxUploadSpeed: speed);
    await _repository.updateSettingField('maxUploadSpeed', speed);
  }

  Future<void> updateSharedSettings(String? path, String speedDown, String speedUp) async {
    // 先更新状态
    state = state.copyWith(
      defaultSavePath: path,
      maxDownloadSpeed: speedDown,
      maxUploadSpeed: speedUp,
    );
    // 再保存到本地存储
    await _repository.saveSettings(state);
  }

  // 保存完整设置对象
  Future<void> saveSettings(SharedFileSettingsModel settings) async {
    state = settings;
    await _repository.saveSettings(settings);
  }
}