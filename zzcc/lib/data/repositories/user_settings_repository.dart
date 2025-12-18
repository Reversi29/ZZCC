// lib/data/repositories/user_settings_repository.dart
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/data/models/user_settings_model.dart';

class UserSettingsRepository {
  final StorageService storage;

  UserSettingsRepository(this.storage);

  // 获取指定用户的设置
  Future<UserSettingsModel?> getSettings(String ciphertext) async {
    return await storage.getUserSettings(ciphertext);
  }

  // 保存用户设置
  Future<void> saveSettings(String ciphertext, UserSettingsModel settings) async {
    await storage.saveUserSettings(ciphertext, settings);
  }

  // 更新特定设置字段
  Future<void> updateSettingField(
    String ciphertext, 
    String field, 
    dynamic value
  ) async {
    await storage.updateUserSettingsField(ciphertext, field, value);
  }

  // 清除用户设置
  Future<void> clearSettings(String ciphertext) async {
    await storage.clearUserSettings(ciphertext);
  }
}