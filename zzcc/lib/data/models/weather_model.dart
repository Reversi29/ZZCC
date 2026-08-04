/// 实时天气。
class WeatherNow {
  final double temperature; // 摄氏度
  final int weatherCode; // WMO 天气代码

  const WeatherNow({required this.temperature, required this.weatherCode});
}

/// 单日预报。
class DailyForecast {
  final String date; // YYYY-MM-DD
  final int weatherCode;
  final double tempMax;
  final double tempMin;

  const DailyForecast({
    required this.date,
    required this.weatherCode,
    required this.tempMax,
    required this.tempMin,
  });
}

/// 天气数据聚合。
class WeatherData {
  final WeatherNow current;
  final List<DailyForecast> daily;

  const WeatherData({required this.current, required this.daily});
}

/// WMO 天气代码 -> 中文描述。
String weatherText(int code) {
  const map = <int, String>{
    0: '晴',
    1: '大致晴朗',
    2: '局部多云',
    3: '阴',
    45: '雾',
    48: '雾凇',
    51: '小毛毛雨',
    53: '毛毛雨',
    55: '大毛毛雨',
    56: '冻毛毛雨',
    57: '强冻毛毛雨',
    61: '小雨',
    63: '中雨',
    65: '大雨',
    66: '冻雨',
    67: '强冻雨',
    71: '小雪',
    73: '中雪',
    75: '大雪',
    77: '雪粒',
    80: '阵雨',
    81: '强阵雨',
    82: '暴雨',
    85: '阵雪',
    86: '强阵雪',
    95: '雷暴',
    96: '雷暴伴冰雹',
    99: '强雷暴伴冰雹',
  };
  return map[code] ?? '未知';
}

/// WMO 天气代码 -> 图标（与 weatherText 对应）。
String weatherEmoji(int code) {
  if (code == 0 || code == 1) return '☀️';
  if (code == 2) return '🌤️';
  if (code == 3) return '☁️';
  if (code == 45 || code == 48) return '🌫️';
  if (code >= 51 && code <= 57) return '🌦️';
  if (code >= 61 && code <= 67) return '🌧️';
  if (code >= 71 && code <= 77) return '🌨️';
  if (code >= 80 && code <= 82) return '🌧️';
  if (code >= 85 && code <= 86) return '🌨️';
  if (code >= 95) return '⛈️';
  return '🌡️';
}
