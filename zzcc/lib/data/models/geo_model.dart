/// IP 定位结果（经 ipapi.co 获取）。
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

  factory GeoInfo.fromJson(Map<String, dynamic> json) {
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

  /// 用于界面展示的位置名：城市 · 省 · 国家。
  String get displayName {
    final parts = [city, region, country]
        .where((e) => e != null && e.isNotEmpty)
        .map((e) => e!)
        .toList();
    return parts.isEmpty ? '未知位置' : parts.join(' · ');
  }
}
