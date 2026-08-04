import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/geo_model.dart';

/// IP 定位数据源：
/// - myip.ipip.net → 中文地名（省/市，无需 key）
/// - ipwho.is       → 公网 IP + 经纬度（无需 key）
/// 两请求并行，最终合并结果。
class GeoRemoteSource {
  static const _textEndpoint = 'https://myip.ipip.net';
  static const _jsonEndpoint = 'https://ipwho.is/';

  /// 解析 myip.ipip.net 返回的文本。
  /// 格式：`当前 IP：<IP>  来自于：<国家> <省> <城市>  <运营商>`
  ({String country, String? region, String? city, String ip, String? isp})
      _parseIpipText(String text) {
    // "当前 IP：...  来自于：...  电信"
    final after = text.split('来自于：');
    if (after.length < 2) {
      throw FormatException('无法解析 myip.ipip.net 响应：$text');
    }
    final loc = after[1].trim();
    // 最后一个 `  ` 之前是地区，之后是运营商
    final lastSep = loc.lastIndexOf('  ');
    final regionPart = lastSep < 0 ? loc : loc.substring(0, lastSep).trim();
    final ispPart = lastSep < 0 ? null : loc.substring(lastSep).trim();
    // "中国 浙江 杭州" → country, region, city
    final segs = regionPart.split(RegExp(r'\s+'));
    return (
      country: segs.isNotEmpty ? segs[0] : '',
      region: segs.length > 1 ? segs[1] : null,
      city: segs.length > 2 ? segs[2] : null,
      ip: after[0].replaceFirst('当前 IP：', '').trim(),
      isp: ispPart,
    );
  }

  Future<GeoInfo> fetchGeo() async {
    // 两个请求并行
    final results = await Future.wait([
      _fetchChineseNames(),
      _fetchCoordinates(),
    ]);
    final names = results[0] as ({String country, String? region, String? city, String ip, String? isp});
    final coords = results[1] as GeoInfo;

    // 用 ipwho.is 的经纬度 + ipip 的中文地名合并
    return GeoInfo.withChineseNames(
      ip: names.ip,
      latitude: coords.latitude,
      longitude: coords.longitude,
      city: names.city,
      region: names.region,
      country: names.country,
      timezone: coords.timezone,
    );
  }

  Future<({String country, String? region, String? city, String ip, String? isp})>
      _fetchChineseNames() async {
    try {
      final resp = await http
          .get(Uri.parse(_textEndpoint), headers: {'User-Agent': 'zzcc-app'})
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) {
        throw Exception('HTTP ${resp.statusCode}');
      }
      return _parseIpipText(resp.body.trim());
    } catch (e) {
      throw Exception('IP 定位失败（地名）：$e');
    }
  }

  Future<GeoInfo> _fetchCoordinates() async {
    try {
      final resp = await http
          .get(Uri.parse(_jsonEndpoint), headers: {'User-Agent': 'zzcc-app'})
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) {
        throw Exception('HTTP ${resp.statusCode}');
      }
      final json = jsonDecode(resp.body) as Map<String, dynamic>;
      if (json['success'] == false) {
        throw Exception('${json['message'] ?? '未知错误'}');
      }
      return GeoInfo.fromCoordinatesJson(json);
    } catch (e) {
      throw Exception('IP 定位失败（经纬度）：$e');
    }
  }
}
