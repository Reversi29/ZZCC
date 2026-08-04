import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:zzcc/data/models/weather_model.dart';
import 'package:zzcc/presentation/providers/geo_provider.dart';
import 'package:zzcc/presentation/providers/weather_provider.dart';

class WeatherWidget extends ConsumerWidget {
  const WeatherWidget({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final geo = ref.watch(geoProvider);
    final weather = ref.watch(weatherProvider);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.cloud, size: 30),
                const SizedBox(width: 10),
                const Text('天气预报', style: TextStyle(fontSize: 18)),
                const Spacer(),
                if (geo.hasValue)
                  Text(
                    geo.value!.displayName,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
              ],
            ),
            const SizedBox(height: 10),
            weather.when(
              loading: () => const Center(
                child: Padding(
                  padding: EdgeInsets.all(12.0),
                  child: CircularProgressIndicator(),
                ),
              ),
              error: (e, _) => Text('天气获取失败：$e',
                  style: const TextStyle(color: Colors.red)),
              data: (data) => _buildBody(context, data),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context, WeatherData data) {
    final now = data.current;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(weatherEmoji(now.weatherCode),
                style: const TextStyle(fontSize: 28)),
            const SizedBox(width: 8),
            Text('${now.temperature.toStringAsFixed(1)}°C',
                style: const TextStyle(fontSize: 22)),
            const SizedBox(width: 8),
            Text(weatherText(now.weatherCode), style: const TextStyle(fontSize: 16)),
          ],
        ),
        const SizedBox(height: 12),
        const Divider(height: 1),
        const SizedBox(height: 8),
        ...data.daily.map((d) => _forecastRow(d)),
      ],
    );
  }

  Widget _forecastRow(DailyForecast d) {
    final weekday = _weekdayOf(d.date);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4.0),
      child: Row(
        children: [
          SizedBox(
            width: 56,
            child: Text(weekday, style: const TextStyle(fontSize: 14)),
          ),
          Text(weatherEmoji(d.weatherCode), style: const TextStyle(fontSize: 18)),
          const SizedBox(width: 8),
          Text(weatherText(d.weatherCode), style: const TextStyle(fontSize: 14)),
          const Spacer(),
          Text('${d.tempMin.toStringAsFixed(0)}° / ${d.tempMax.toStringAsFixed(0)}°',
              style: const TextStyle(fontSize: 14)),
        ],
      ),
    );
  }

  String _weekdayOf(String date) {
    const names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
    try {
      final dt = DateTime.parse(date);
      // DateTime.weekday: 1=Mon..7=Sun
      return names[dt.weekday - 1];
    } catch (_) {
      return date;
    }
  }
}
