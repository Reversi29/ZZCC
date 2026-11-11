// lib/core/services/network_stats_service_web.dart
//
// Web 实现：用 package:web（dart:js_interop）读取真实浏览器信息。
//   - checkInternet：读 window.navigator.onLine（真实浏览器在线状态）。
//   - getWifiName/getWifiIP：浏览器无法获取 SSID/IP，返回 null。
// 定义抽象接口 NetworkStatsService 与实现 NetworkStatsServiceImpl。

import 'package:web/web.dart' as web;

import 'package:zzcc/core/services/network_stats_service_stub.dart'
    show NetworkStats;

/// 网络统计服务抽象接口（须与 stub/io 实现一致）。
abstract class NetworkStatsService {
  /// 读取当前网络接口累计收发字节。失败返回 null。
  Future<NetworkStats?> getNetworkStats();

  /// 探测是否有真实互联网连接。失败返回 false。
  Future<bool> checkInternet();

  /// 读取当前 WiFi 名称（SSID）。不支持返回 null。
  Future<String?> getWifiName();

  /// 读取当前 WiFi IP 地址。不支持返回 null。
  Future<String?> getWifiIP();
}

/// Web 实现。
class NetworkStatsServiceImpl implements NetworkStatsService {
  @override
  Future<NetworkStats?> getNetworkStats() async {
    // 浏览器不暴露接口级收发字节统计，返回 null。
    return null;
  }

  @override
  Future<bool> checkInternet() async {
    try {
      // window.navigator.onLine 是浏览器内置在线/离线状态（真实值）。
      return web.window.navigator.onLine;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<String?> getWifiName() async {
    // 浏览器无法获取 SSID。
    return null;
  }

  @override
  Future<String?> getWifiIP() async {
    // 浏览器无法获取 WiFi IP。
    return null;
  }
}
