// import 'package:flutter/material.dart';
import 'package:zzcc/data/models/theme_model.dart';

class UserSettingsModel {
  final CustomTheme? customTheme;
  final bool useSystemTheme;
  final String? preferredFont;
  final bool notificationsEnabled;

  // Brain AI 云端模型配置（用户级，存 user_settings.hive）
  final String brainApiBase;
  final String brainApiKey;
  final String brainModel;
  final double brainTemperature;
  final String brainProtocol;

  UserSettingsModel({
    this.customTheme,
    this.useSystemTheme = true,
    this.preferredFont,
    this.notificationsEnabled = true,
    this.brainApiBase = 'http://127.0.0.1:8001/api/v1/',
    this.brainApiKey = '',
    this.brainModel = 'qwen/qwen3.8-flash',
    this.brainTemperature = 0.3,
    this.brainProtocol = 'openai',
  });

  UserSettingsModel copyWith({
    CustomTheme? customTheme,
    bool? useSystemTheme,
    String? preferredFont,
    bool? notificationsEnabled,
    String? brainApiBase,
    String? brainApiKey,
    String? brainModel,
    double? brainTemperature,
    String? brainProtocol,
  }) {
    return UserSettingsModel(
      customTheme: customTheme ?? this.customTheme,
      useSystemTheme: useSystemTheme ?? this.useSystemTheme,
      preferredFont: preferredFont ?? this.preferredFont,
      notificationsEnabled: notificationsEnabled ?? this.notificationsEnabled,
      brainApiBase: brainApiBase ?? this.brainApiBase,
      brainApiKey: brainApiKey ?? this.brainApiKey,
      brainModel: brainModel ?? this.brainModel,
      brainTemperature: brainTemperature ?? this.brainTemperature,
      brainProtocol: brainProtocol ?? this.brainProtocol,
    );
  }
}
