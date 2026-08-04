/// IP 定位结果（经 myip.ipip.net + ipwho.is 并行获取）。
/// 地名为中文，经纬度来自 ipwho.is。
class GeoInfo {
  final String ip;
  final String? city;
  final String? region;
  final String? country;
  final double latitude;
  final double longitude;
  final String? timezone;

  const GeoInfo({
    required this.ip,
    this.city,
    this.region,
    this.country,
    required this.latitude,
    required this.longitude,
    this.timezone,
  });

  /// 从 ipwho.is JSON 构建（经纬度来源）。
  factory GeoInfo.fromCoordinatesJson(Map<String, dynamic> json) {
    return GeoInfo(
      ip: json['ip']?.toString() ?? '',
      city: json['city']?.toString(),
      region: json['region']?.toString(),
      country: json['country']?.toString(),
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
      timezone: json['timezone']?.toString(),
    );
  }

  /// 从中文地区段构建（myip.ipip.net 解析结果）。
  /// [ip] 和经纬度需另行注入（由 ipwho.is 提供）。
  GeoInfo.withChineseNames({
    required this.ip,
    required this.latitude,
    required this.longitude,
    this.city,
    this.region,
    this.country,
    this.timezone,
  });

  /// 用于界面展示的位置名：城市 · 省 · 国家（全中文）。
  String get displayName {
    final parts = [city, region, country]
        .where((e) => e != null && e.isNotEmpty)
        .map((e) => e!)
        .toList();
    return parts.isEmpty ? '未知位置' : parts.join(' · ');
  }
}
