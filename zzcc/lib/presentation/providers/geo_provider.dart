import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:zzcc/data/models/geo_model.dart';
import 'package:zzcc/data/sources/geo_remote_source.dart';

/// 当前网络位置（IP 定位）。首次访问时拉取并缓存。
final geoProvider = FutureProvider<GeoInfo>((ref) async {
  return GeoRemoteSource().fetchGeo();
});
