// lib/core/utils/app_format.dart
//
// 依据 AppSettings 对时间/日期/数字/温度/计量进行格式化。
// 这是「时间与地区」设置的实际功能落地点：UI 与业务代码统一调用这里。

import 'package:intl/intl.dart';
import 'package:zzcc/data/models/app_settings_model.dart';
import 'package:zzcc/core/utils/lunar.dart';

class AppFormat {
  AppFormat._();

  /// 将「当前时刻」转换到目标时区的墙上时间。
  /// [instant] 应为 UTC 时刻；若传入本地时间会先转 UTC 再应用偏移。
  static DateTime toTimezone(DateTime instant, AppSettings s) {
    final utc = instant.isUtc ? instant : instant.toUtc();
    final offset = Duration(minutes: kTimezoneOffsets[s.timezone] ?? 0);
    return utc.add(offset);
  }

  /// 当前时刻（已应用所选时区）。
  static DateTime now(AppSettings s) => toTimezone(DateTime.now().toUtc(), s);

  /// 依据历法 + 日期格式格式化日期。
  static String formatDate(DateTime dt, AppSettings s) {
    final zoned = toTimezone(dt, s);
    if (s.calendar == CalendarSystem.lunar) {
      return Lunar.toLunarDate(zoned);
    }
    switch (s.dateFormat) {
      case DateFormatPattern.yyyyMmDd:
        return DateFormat('yyyy-MM-dd').format(zoned);
      case DateFormatPattern.ddMmYyyy:
        return DateFormat('dd/MM/yyyy').format(zoned);
      case DateFormatPattern.mmDdYyyy:
        return DateFormat('MM/dd/yyyy').format(zoned);
      case DateFormatPattern.yyyySlashMmSlashDd:
        return DateFormat('yyyy/MM/dd').format(zoned);
    }
  }

  /// 依据小时制格式化时间。
  static String formatTime(DateTime dt, AppSettings s) {
    final zoned = toTimezone(dt, s);
    if (s.hourFormat == HourSystem.h12) {
      return DateFormat('hh:mm a').format(zoned);
    }
    return DateFormat('HH:mm').format(zoned);
  }

  /// 日期 + 时间。
  static String formatDateTime(DateTime dt, AppSettings s) {
    return '${formatDate(dt, s)} ${formatTime(dt, s)}';
  }

  /// 提供给日历组件使用的「每周第一天」(1=周一 .. 7=周日)。
  static int firstDayOfWeek(AppSettings s) {
    return s.firstDayOfWeek == FirstDayOfWeek.monday ? 1 : 7;
  }

  /// 地区对应的 intl locale（用于数字/货币格式化）。
  static String regionLocale(AppSettings s) =>
      kRegionLocales[s.region] ?? 'zh_CN';

  static String _num(num value, AppSettings s) =>
      NumberFormat.decimalPattern(regionLocale(s)).format(value);

  /// 数字（按地区千分位/小数格式）。
  static String formatNumber(num value, AppSettings s) => _num(value, s);

  /// 温度：输入为摄氏度，按设置输出 °C / °F。
  static String formatTemperature(double celsius, AppSettings s) {
    if (s.temperatureUnit == TemperatureUnit.fahrenheit) {
      final f = celsius * 9 / 5 + 32;
      return '${_num(double.parse(f.toStringAsFixed(1)), s)}°F';
    }
    return '${_num(double.parse(celsius.toStringAsFixed(1)), s)}°C';
  }

  /// 距离：输入为米，按公制/英制输出。
  static String formatDistance(double meters, AppSettings s) {
    if (s.measurementSystem == MeasurementSystem.imperial) {
      final miles = meters / 1609.344;
      return '${_num(double.parse(miles.toStringAsFixed(2)), s)} mi';
    }
    if (meters >= 1000) {
      return '${_num(double.parse((meters / 1000).toStringAsFixed(2)), s)} km';
    }
    return '${_num(meters, s)} m';
  }

  /// 重量：输入为千克，按公制/英制输出。
  static String formatWeight(double kg, AppSettings s) {
    if (s.measurementSystem == MeasurementSystem.imperial) {
      final lb = kg * 2.2046226218;
      return '${_num(double.parse(lb.toStringAsFixed(2)), s)} lb';
    }
    if (kg >= 1000) {
      return '${_num(double.parse((kg / 1000).toStringAsFixed(2)), s)} t';
    }
    return '${_num(double.parse(kg.toStringAsFixed(2)), s)} kg';
  }

  /// 常用时区 ID 列表（供下拉选择）。
  static List<String> get timezoneIds => kTimezoneOffsets.keys.toList();

  /// 可选地区代码列表。
  static List<String> get regionCodes => kRegionLocales.keys.toList();
}
