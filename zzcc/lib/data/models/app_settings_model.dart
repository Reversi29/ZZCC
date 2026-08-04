// lib/data/models/app_settings_model.dart
//
// 应用级「时间与地区」设置模型。
// 这些设置影响全应用的时间/日期/数字/温度/计量显示。

enum CalendarSystem {
  gregorian, // 公历
  lunar, // 农历
}

enum FirstDayOfWeek {
  monday, // 周一为每周第一天 (DateTime.weekday = 1)
  sunday, // 周日为每周第一天 (DateTime.weekday = 7)
}

enum DateFormatPattern {
  yyyyMmDd, // 2026-08-03
  ddMmYyyy, // 03/08/2026
  mmDdYyyy, // 08/03/2026
  yyyySlashMmSlashDd, // 2026/08/03
}

enum HourSystem {
  h24, // 24 小时制
  h12, // 12 小时制
}

enum TimeSource {
  device, // 设备时间
  network, // 网络时间（校时）
}

enum TemperatureUnit {
  celsius, // 摄氏度
  fahrenheit, // 华氏度
}

enum MeasurementSystem {
  metric, // 公制 (km / kg / cm)
  imperial, // 英制 (mi / lb / inch)
}

/// 应用「时间与地区」相关设置。
class AppSettings {
  final CalendarSystem calendar;
  final FirstDayOfWeek firstDayOfWeek;
  final DateFormatPattern dateFormat;
  final HourSystem hourFormat;
  final TimeSource timeSource;

  /// 时区 ID，对应 [kTimezoneOffsets] 中的键。
  final String timezone;

  /// 地区代码，对应 [kRegionLocales] 中的键，用于数字/货币格式化。
  final String region;

  final TemperatureUnit temperatureUnit;
  final MeasurementSystem measurementSystem;

  const AppSettings({
    this.calendar = CalendarSystem.gregorian,
    this.firstDayOfWeek = FirstDayOfWeek.monday,
    this.dateFormat = DateFormatPattern.yyyyMmDd,
    this.hourFormat = HourSystem.h24,
    this.timeSource = TimeSource.device,
    this.timezone = 'Asia/Shanghai',
    this.region = 'CN',
    this.temperatureUnit = TemperatureUnit.celsius,
    this.measurementSystem = MeasurementSystem.metric,
  });

  AppSettings copyWith({
    CalendarSystem? calendar,
    FirstDayOfWeek? firstDayOfWeek,
    DateFormatPattern? dateFormat,
    HourSystem? hourFormat,
    TimeSource? timeSource,
    String? timezone,
    String? region,
    TemperatureUnit? temperatureUnit,
    MeasurementSystem? measurementSystem,
  }) {
    return AppSettings(
      calendar: calendar ?? this.calendar,
      firstDayOfWeek: firstDayOfWeek ?? this.firstDayOfWeek,
      dateFormat: dateFormat ?? this.dateFormat,
      hourFormat: hourFormat ?? this.hourFormat,
      timeSource: timeSource ?? this.timeSource,
      timezone: timezone ?? this.timezone,
      region: region ?? this.region,
      temperatureUnit: temperatureUnit ?? this.temperatureUnit,
      measurementSystem: measurementSystem ?? this.measurementSystem,
    );
  }

  Map<String, dynamic> toJson() => {
        'calendar': calendar.name,
        'firstDayOfWeek': firstDayOfWeek.name,
        'dateFormat': dateFormat.name,
        'hourFormat': hourFormat.name,
        'timeSource': timeSource.name,
        'timezone': timezone,
        'region': region,
        'temperatureUnit': temperatureUnit.name,
        'measurementSystem': measurementSystem.name,
      };

  factory AppSettings.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const AppSettings();
    return AppSettings(
      calendar: _enumFromString(CalendarSystem.values, json['calendar'], CalendarSystem.gregorian),
      firstDayOfWeek:
          _enumFromString(FirstDayOfWeek.values, json['firstDayOfWeek'], FirstDayOfWeek.monday),
      dateFormat:
          _enumFromString(DateFormatPattern.values, json['dateFormat'], DateFormatPattern.yyyyMmDd),
      hourFormat: _enumFromString(HourSystem.values, json['hourFormat'], HourSystem.h24),
      timeSource: _enumFromString(TimeSource.values, json['timeSource'], TimeSource.device),
      timezone: (json['timezone'] as String?) ?? 'Asia/Shanghai',
      region: (json['region'] as String?) ?? 'CN',
      temperatureUnit:
          _enumFromString(TemperatureUnit.values, json['temperatureUnit'], TemperatureUnit.celsius),
      measurementSystem: _enumFromString(
          MeasurementSystem.values, json['measurementSystem'], MeasurementSystem.metric),
    );
  }
}

T _enumFromString<T extends Enum>(List<T> values, String? name, T fallback) {
  if (name == null) return fallback;
  for (final v in values) {
    if (v.name == name) return v;
  }
  return fallback;
}

/// 日历系统显示标签。
const Map<CalendarSystem, String> calendarLabels = {
  CalendarSystem.gregorian: '公历',
  CalendarSystem.lunar: '农历',
};

/// 每周第一天显示标签。
const Map<FirstDayOfWeek, String> firstDayOfWeekLabels = {
  FirstDayOfWeek.monday: '周一',
  FirstDayOfWeek.sunday: '周日',
};

/// 日期格式显示标签（标签内展示示例）。
const Map<DateFormatPattern, String> dateFormatLabels = {
  DateFormatPattern.yyyyMmDd: '2026-08-03',
  DateFormatPattern.ddMmYyyy: '03/08/2026',
  DateFormatPattern.mmDdYyyy: '08/03/2026',
  DateFormatPattern.yyyySlashMmSlashDd: '2026/08/03',
};

/// 小时制显示标签。
const Map<HourSystem, String> hourFormatLabels = {
  HourSystem.h24: '24 小时制',
  HourSystem.h12: '12 小时制',
};

/// 时间来源显示标签。
const Map<TimeSource, String> timeSourceLabels = {
  TimeSource.device: '设备时间',
  TimeSource.network: '网络时间',
};

/// 温度单位显示标签。
const Map<TemperatureUnit, String> temperatureUnitLabels = {
  TemperatureUnit.celsius: '摄氏度 (°C)',
  TemperatureUnit.fahrenheit: '华氏度 (°F)',
};

/// 计量系统显示标签。
const Map<MeasurementSystem, String> measurementSystemLabels = {
  MeasurementSystem.metric: '公制 (km/kg/cm)',
  MeasurementSystem.imperial: '英制 (mi/lb/in)',
};

/// 地区代码 -> intl locale（用于数字/货币格式化）。
const Map<String, String> kRegionLocales = {
  'CN': 'zh_CN',
  'US': 'en_US',
  'GB': 'en_GB',
  'JP': 'ja_JP',
  'DE': 'de_DE',
  'FR': 'fr_FR',
};

/// 地区显示标签。
const Map<String, String> regionLabels = {
  'CN': '中国大陆',
  'US': '美国',
  'GB': '英国',
  'JP': '日本',
  'DE': '德国',
  'FR': '法国',
};

/// 常见时区 -> UTC 偏移（分钟）。
/// 说明：采用固定偏移，未处理夏令时（DST）。
const Map<String, int> kTimezoneOffsets = {
  'UTC': 0,
  'Asia/Shanghai': 480,
  'Asia/Hong_Kong': 480,
  'Asia/Tokyo': 540,
  'Asia/Kolkata': 330,
  'Asia/Dubai': 240,
  'Europe/London': 0,
  'Europe/Paris': 60,
  'Europe/Moscow': 180,
  'America/New_York': -300,
  'America/Los_Angeles': -480,
  'Australia/Sydney': 600,
};

/// 时区显示标签（含 GMT 偏移）。
String timezoneLabel(String id) {
  final offset = kTimezoneOffsets[id] ?? 0;
  final sign = offset >= 0 ? '+' : '-';
  final abs = offset.abs();
  final hh = (abs ~/ 60).toString().padLeft(2, '0');
  final mm = (abs % 60).toString().padLeft(2, '0');
  return '$id (GMT$sign$hh:$mm)';
}
