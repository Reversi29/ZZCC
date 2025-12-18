// import 'package:flutter/material.dart';
import 'package:zzcc/data/models/theme_model.dart';

class UserSettingsModel {
  final CustomTheme? customTheme;
  final bool useSystemTheme;
  final String? preferredFont;
  final bool notificationsEnabled;

  UserSettingsModel({
    this.customTheme,
    this.useSystemTheme = true,
    this.preferredFont,
    this.notificationsEnabled = true,
  });

  UserSettingsModel copyWith({
    CustomTheme? customTheme,
    bool? useSystemTheme,
    String? preferredFont,
    bool? notificationsEnabled,
  }) {
    return UserSettingsModel(
      customTheme: customTheme ?? this.customTheme,
      useSystemTheme: useSystemTheme ?? this.useSystemTheme,
      preferredFont: preferredFont ?? this.preferredFont,
      notificationsEnabled: notificationsEnabled ?? this.notificationsEnabled,
    );
  }
}