// lib/data/models/settings_model.dart
import 'package:flutter/material.dart';

class SettingsModel {
  final ThemeMode themeMode;
  final bool notificationsEnabled;
  final double playbackSpeed;

  SettingsModel({
    required this.themeMode,
    required this.notificationsEnabled,
    required this.playbackSpeed,
  });
}