import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/data/models/theme_model.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/presentation/providers/user_provider.dart';
import 'package:zzcc/core/di/service_locator.dart';

/// Hive box key for theme persistence.
const _themeKey = 'theme_v1';

final themeProvider = StateNotifierProvider<ThemeNotifier, CustomTheme>(
  (ref) => ThemeNotifier(
    ref.read(userProvider.notifier),
    getIt<StorageService>(),
  ),
);

class ThemeNotifier extends StateNotifier<CustomTheme> {
  final UserNotifier _userNotifier;
  final StorageService _storageService;

  ThemeNotifier(this._userNotifier, this._storageService)
      : super(CustomTheme.defaultLight) {
    _loadTheme();
  }

  Future<void> _loadTheme() async {
    try {
      final userDataPath = _userNotifier.state.userDataPath;
      if (userDataPath == null || userDataPath.isEmpty) return;

      final uid = _userNotifier.state.uid;
      final raw = await _storageService.getUserInfoByKey(uid, _themeKey);
      if (raw == null) return;

      Map<String, dynamic>? json;
      if (raw is String) {
        try {
          json = jsonDecode(raw) as Map<String, dynamic>;
        } catch (_) {}
      } else if (raw is Map) {
        json = Map<String, dynamic>.from(raw);
      }
      if (json == null) return;

      final loaded = CustomTheme.fromJson(json);
      if (mounted) state = loaded;
    } catch (_) {
      // 加载失败保持默认
    }
  }

  Future<void> _saveTheme() async {
    try {
      final userDataPath = _userNotifier.state.userDataPath;
      if (userDataPath == null || userDataPath.isEmpty) return;

      final uid = _userNotifier.state.uid;
      await _storageService.saveUserInfo(
        uid,
        {_themeKey: state.toJson()},
      );
    } catch (_) {
      // 保存失败静默忽略
    }
  }

  void changeTheme(CustomTheme newTheme) {
    state = newTheme;
    _saveTheme();
  }

  void setPrimaryColor(Color color) => changeTheme(state.copyWith(primaryColor: color));

  void setLeftSidebarColor(Color color) =>
      changeTheme(state.copyWith(leftSidebarColor: color));

  void setRightPanelColor(Color color) =>
      changeTheme(state.copyWith(rightPanelColor: color));

  void resetToDefault() => changeTheme(CustomTheme.defaultLight);
}
