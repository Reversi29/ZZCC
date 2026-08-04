import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/weather_model.dart';

/// 天气数据源：Open-Meteo 免费接口，无需 API key。
/// 文档：https://open-meteo.com/en/docs
class WeatherRemoteSource {
  static const _endpoint = 'https://api.open-meteo.com/v1/forecast';

  Future<WeatherData> fetchWeather(double latitude, double longitude) async {
    final uri = Uri.parse(_endpoint).replace(queryParameters: {
      'latitude': latitude.toString(),
      'longitude': longitude.toString(),
      'current': 'temperature_2m,weather_code',
      'daily': 'weather_code,temperature_2m_max,temperature_2m_min',
      'timezone': 'auto',
      'forecast_days': '3',
    });

    final resp = await http
        .get(uri)
        .timeout(const Duration(seconds: 10));

    if (resp.statusCode != 200) {
      throw Exception('天气请求失败：${resp.statusCode}');
    }

    final json = jsonDecode(resp.body) as Map<String, dynamic>;
    final current = json['current'] as Map<String, dynamic>;
    final daily = json['daily'] as Map<String, dynamic>;

    final times = (daily['time'] as List).cast<String>();
    final codes = (daily['weather_code'] as List).cast<num>();
    final maxs = (daily['temperature_2m_max'] as List).cast<num>();
    final mins = (daily['temperature_2m_min'] as List).cast<num>();

    final dailyList = <DailyForecast>[];
    for (var i = 0; i < times.length; i++) {
      dailyList.add(DailyForecast(
        date: times[i],
        weatherCode: codes[i].toInt(),
        tempMax: maxs[i].toDouble(),
        tempMin: mins[i].toDouble(),
      ));
    }

    final now = WeatherNow(
      temperature: (current['temperature_2m'] as num).toDouble(),
      weatherCode: (current['weather_code'] as num).toInt(),
    );

    return WeatherData(current: now, daily: dailyList);
  }
}
