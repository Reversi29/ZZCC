// lib/core/utils/network_time.dart
//
// 网络时间来源（用于「时间来源 = 网络」选项）。
// 失败时返回 null，由调用方回退到设备时间。

import 'dart:convert';
import 'package:http/http.dart' as http;

class NetworkTime {
  NetworkTime._();

  /// 尝试从公开时间 API 获取 UTC 时刻；失败返回 null。
  static Future<DateTime?> fetchUtc() async {
    try {
      final resp = await http
          .get(Uri.parse('https://worldtimeapi.org/api/timezone/Etc/UTC'))
          .timeout(const Duration(seconds: 5));
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body) as Map<String, dynamic>;
        final uni = data['unixtime'] as int?;
        if (uni != null) {
          return DateTime.fromMillisecondsSinceEpoch(uni * 1000, isUtc: true);
        }
        final dt = data['utc_datetime'] as String?;
        if (dt != null) return DateTime.parse(dt);
      }
    } catch (_) {
      // 忽略网络错误，回退设备时间
    }
    return null;
  }
}
