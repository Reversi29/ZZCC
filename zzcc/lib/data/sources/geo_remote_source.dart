import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/geo_model.dart';

/// IP 定位数据源：
/// - ip-api.com (HTTP) → 中国地区地名 + 经纬度 + ISP（一个请求搞定）
/// - 降级到 myip.ipip.net 仅获取地名（当主数据源失败时）
class GeoRemoteSource {
  static const _primaryEndpoint = 'http://ip-api.com/json/?lang=zh-CN';
  static const _fallbackEndpoint = 'https://myip.ipip.net';

  /// 解析 myip.ipip.net 返回的文本。
  /// 格式：`当前 IP：<IP>  来自于：<国家> <省> <城市>  <运营商>`
  ({String country, String? region, String? city, String ip, String? isp})
      _parseIpipText(String text) {
    final after = text.split('来自于：');
    if (after.length < 2) {
      throw FormatException('无法解析 myip.ipip.net 响应：$text');
    }
    final loc = after[1].trim();
    final lastSep = loc.lastIndexOf('  ');
    final regionPart = lastSep < 0 ? loc : loc.substring(0, lastSep).trim();
    final ispPart = lastSep < 0 ? null : loc.substring(lastSep).trim();
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
    // 主路径：ip-api.com 一个请求获取所有信息
    try {
      return await _fetchFromIpApi();
    } catch (primaryError) {
      // 降级：只拿地名，经纬度用杭州默认值
      try {
        final fallback = await _fetchFromIpipOnly();
        return GeoInfo.withChineseNames(
          ip: fallback.ip,
          latitude: 30.2936, // 杭州默认
          longitude: 120.1614,
          city: fallback.city,
          region: fallback.region,
          country: fallback.country,
          timezone: 'Asia/Shanghai',
        );
      } catch (fallbackError) {
        // 都失败时抛一个可读错误，避免 Future<void> 显示问题
        throw Exception(
          'IP 定位服务暂时不可用（主源: $primaryError, 降级源: $fallbackError）',
        );
      }
    }
  }

  Future<GeoInfo> _fetchFromIpApi() async {
    final resp = await http
        .get(Uri.parse(_primaryEndpoint), headers: {'User-Agent': 'zzcc-app'})
        .timeout(const Duration(seconds: 10));

    if (resp.statusCode != 200) {
      throw Exception('HTTP ${resp.statusCode}');
    }

    final json = jsonDecode(resp.body) as Map<String, dynamic>;
    if (json['status'] != 'success') {
      throw Exception(json['message'] ?? '查询失败');
    }

    return GeoInfo.withChineseNames(
      ip: json['query'] as String,
      latitude: (json['lat'] as num).toDouble(),
      longitude: (json['lon'] as num).toDouble(),
      city: json['city'] as String?,
      region: json['regionName'] as String?,
      country: json['country'] as String?,
      timezone: json['timezone'] as String?,
    );
  }

  Future<({String country, String? region, String? city, String ip, String? isp})>
      _fetchFromIpipOnly() async {
    final resp = await http
        .get(Uri.parse(_fallbackEndpoint), headers: {'User-Agent': 'zzcc-app'})
        .timeout(const Duration(seconds: 10));
    if (resp.statusCode != 200) {
      throw Exception('HTTP ${resp.statusCode}');
    }
    return _parseIpipText(resp.body.trim());
  }
}