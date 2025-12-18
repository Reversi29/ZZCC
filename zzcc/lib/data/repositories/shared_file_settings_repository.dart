// lib/data/repositories/shared_file_settings_repository.dart
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/data/models/shared_file_settings_model.dart';

class SharedFileSettingsRepository {
  final StorageService storage;

  SharedFileSettingsRepository(this.storage);

  // 获取共享文件设置
  Future<SharedFileSettingsModel> getSettings() async {
    return await storage.getSharedFileSettings();
  }

  // 保存共享文件设置
  Future<void> saveSettings(SharedFileSettingsModel settings) async {
    await storage.saveSharedFileSettings(settings);
  }

  // 更新特定设置字段
  Future<void> updateSettingField(String field, dynamic value) async {
    await storage.updateSharedFileSettingField(field, value);
  }

  // 清除共享文件设置
  Future<void> clearSettings() async {
    await storage.clearSharedFileSettings();
  }
}