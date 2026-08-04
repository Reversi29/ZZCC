import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/geo_model.dart';

/// IP 定位数据源：通过 ipwho.is 免费接口获取当前网络位置（HTTPS，无需 API key）。
class GeoRemoteSource {
  static const _endpoint = 'https://ipwho.is/';

  Future<GeoInfo> fetchGeo() async {
    final uri = Uri.parse(_endpoint);
    final resp = await http
        .get(uri, headers: {'User-Agent': 'zzcc-app'})
        .timeout(const Duration(seconds: 10));

    if (resp.statusCode != 200) {
      throw Exception('IP 定位请求失败：${resp.statusCode}');
    }

    final json = jsonDecode(resp.body) as Map<String, dynamic>;
    // ipwho.is 失败时返回 {"success": false, "message": "..."}
    if (json['success'] == false) {
      throw Exception('IP 定位失败：${json['message'] ?? '未知错误'}');
    }
    return GeoInfo.fromJson(json);
  }
}
