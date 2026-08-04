import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:zzcc/data/models/weather_model.dart';
import 'package:zzcc/data/sources/weather_remote_source.dart';
import 'package:zzcc/presentation/providers/geo_provider.dart';

/// 当前位置的天气。依赖于 geoProvider，位置变化会自动重新拉取。
final weatherProvider = FutureProvider<WeatherData>((ref) async {
  final geo = await ref.watch(geoProvider.future);
  return WeatherRemoteSource().fetchWeather(geo.latitude, geo.longitude);
});
