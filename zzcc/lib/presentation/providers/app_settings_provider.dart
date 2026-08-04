// lib/presentation/providers/app_settings_provider.dart
//
// 应用「时间与地区」设置的 Riverpod 状态管理。
// 持久化到 StorageService 的 app_settings Hive 盒子，键名 'appSettings'。

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/data/models/app_settings_model.dart';

final appSettingsProvider =
    StateNotifierProvider<AppSettingsNotifier, AppSettings>(
  (ref) => AppSettingsNotifier(),
);

class AppSettingsNotifier extends StateNotifier<AppSettings> {
  AppSettingsNotifier() : super(const AppSettings()) {
    _init();
  }

  Future<void> _init() async {
    final storage = getIt<StorageService>();
    // app_settings 盒子由 StorageService.init() 在启动时打开；
    // 若尚未打开（极少数时序情况）则跳过加载，不阻塞 UI。
    if (!storage.isAppBoxOpen) return;
    final saved = storage.getFromAppBox('appSettings');
    if (saved is Map) {
      state = AppSettings.fromJson(Map<String, dynamic>.from(saved));
    }
  }

  Future<void> update(AppSettings settings) async {
    state = settings;
    final storage = getIt<StorageService>();
    storage.saveToAppBox('appSettings', settings.toJson());
  }

  Future<void> setCalendar(CalendarSystem v) =>
      update(state.copyWith(calendar: v));
  Future<void> setFirstDayOfWeek(FirstDayOfWeek v) =>
      update(state.copyWith(firstDayOfWeek: v));
  Future<void> setDateFormat(DateFormatPattern v) =>
      update(state.copyWith(dateFormat: v));
  Future<void> setHourFormat(HourSystem v) =>
      update(state.copyWith(hourFormat: v));
  Future<void> setTimeSource(TimeSource v) =>
      update(state.copyWith(timeSource: v));
  Future<void> setTimezone(String v) => update(state.copyWith(timezone: v));
  Future<void> setRegion(String v) => update(state.copyWith(region: v));
  Future<void> setTemperatureUnit(TemperatureUnit v) =>
      update(state.copyWith(temperatureUnit: v));
  Future<void> setMeasurementSystem(MeasurementSystem v) =>
      update(state.copyWith(measurementSystem: v));
}
