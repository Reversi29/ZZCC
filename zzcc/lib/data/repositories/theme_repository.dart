import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/data/models/settings_model.dart';
import 'package:flutter/material.dart';

class ThemeRepository {
  final StorageService storage;

  ThemeRepository(this.storage);

  SettingsModel getSettings() {
    return SettingsModel(
      themeMode: storage.getFromAppBox('themeMode') ?? ThemeMode.system,
      notificationsEnabled: storage.getFromAppBox('notificationsEnabled') ?? true,
      playbackSpeed: storage.getFromAppBox('playbackSpeed') ?? 1.0,
    );
  }

  void saveSettings(SettingsModel settings) {
    storage.saveToAppBox('themeMode', settings.themeMode);
    storage.saveToAppBox('notificationsEnabled', settings.notificationsEnabled);
    storage.saveToAppBox('playbackSpeed', settings.playbackSpeed);
  }
}