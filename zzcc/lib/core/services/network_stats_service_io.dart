// lib/core/services/network_stats_service_io.dart
//
// Native 实现：用 Process/InternetAddress 读取真实接口统计与连通性。
// 定义抽象接口 NetworkStatsService 与实现 NetworkStatsServiceImpl。

import 'dart:io';

import 'package:network_info_plus/network_info_plus.dart';

import 'package:zzcc/core/services/network_stats_service_stub.dart'
    show NetworkStats;

/// 网络统计服务抽象接口（须与 stub/web 实现一致）。
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

/// Native 实现。
class NetworkStatsServiceImpl implements NetworkStatsService {
  @override
  Future<NetworkStats?> getNetworkStats() async {
    try {
      if (Platform.isWindows) {
        return await _getWindowsNetworkStats();
      } else if (Platform.isLinux || Platform.isMacOS) {
        return await _getUnixNetworkStats();
      }
    } catch (_) {
      // 忽略，返回 null
    }
    return null;
  }

  @override
  Future<bool> checkInternet() async {
    try {
      final result = await InternetAddress.lookup('google.com').timeout(
        const Duration(seconds: 5),
        onTimeout: () => throw const SocketException('Connection timeout'),
      );
      return result.isNotEmpty && result[0].rawAddress.isNotEmpty;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<String?> getWifiName() async {
    try {
      return await NetworkInfo().getWifiName();
    } catch (_) {
      return null;
    }
  }

  @override
  Future<String?> getWifiIP() async {
    try {
      return await NetworkInfo().getWifiIP();
    } catch (_) {
      return null;
    }
  }

  Future<NetworkStats> _getWindowsNetworkStats() async {
    final result = await Process.run('powershell', [
      'Get-NetAdapterStatistics | Select-Object Name,ReceivedBytes,SentBytes | ConvertTo-Json'
    ]);

    if (result.exitCode == 0) {
      final output = result.stdout.toString();
      final lines = output.split('\n');
      for (final line in lines) {
        if (line.contains('ReceivedBytes') && line.contains('SentBytes')) {
          final receivedMatch =
              RegExp(r'"ReceivedBytes":\s*(\d+)').firstMatch(line);
          final sentMatch = RegExp(r'"SentBytes":\s*(\d+)').firstMatch(line);

          if (receivedMatch != null && sentMatch != null) {
            return NetworkStats(
              receivedBytes: int.parse(receivedMatch.group(1)!),
              sentBytes: int.parse(sentMatch.group(1)!),
            );
          }
        }
      }
    }

    final netstatResult = await Process.run('netstat', ['-e']);
    if (netstatResult.exitCode == 0) {
      return _parseNetstatOutput(netstatResult.stdout.toString());
    }

    throw Exception('无法获取Windows网络统计信息');
  }

  Future<NetworkStats> _getUnixNetworkStats() async {
    final result = await Process.run('cat', ['/proc/net/dev']);

    if (result.exitCode == 0) {
      return _parseProcNetDev(result.stdout.toString());
    }

    try {
      final ifconfigResult = await Process.run('ifconfig', []);
      if (ifconfigResult.exitCode == 0) {
        return _parseIfconfigOutput(ifconfigResult.stdout.toString());
      }
    } catch (_) {
      // 忽略错误
    }

    final netstatResult = await Process.run('netstat', ['-i']);
    if (netstatResult.exitCode == 0) {
      return _parseNetstatOutput(netstatResult.stdout.toString());
    }

    throw Exception('无法获取Unix网络统计信息');
  }

  NetworkStats _parseProcNetDev(String output) {
    int totalReceived = 0;
    int totalSent = 0;
    final lines = output.split('\n');
    for (final line in lines) {
      final trimmed = line.trim();
      if (trimmed.isEmpty || !trimmed.contains(':')) continue;
      // 跳过 lo (回环)，只统计真实接口
      if (trimmed.startsWith('lo:')) continue;
      final parts = trimmed.split(':');
      if (parts.length < 2) continue;
      final fields = parts[1].trim().split(RegExp(r'\s+'));
      if (fields.length < 9) continue;
      final received = int.tryParse(fields[0]) ?? 0;
      final sent = int.tryParse(fields[8]) ?? 0;
      totalReceived += received;
      totalSent += sent;
    }
    return NetworkStats(receivedBytes: totalReceived, sentBytes: totalSent);
  }

  NetworkStats _parseIfconfigOutput(String output) {
    int totalReceived = 0;
    int totalSent = 0;
    final lines = output.split('\n');
    for (final line in lines) {
      final rxMatch =
          RegExp(r'RX bytes[:\s]+(\d+)').firstMatch(line);
      final txMatch =
          RegExp(r'TX bytes[:\s]+(\d+)').firstMatch(line);
      if (rxMatch != null) {
        totalReceived += int.tryParse(rxMatch.group(1)!) ?? 0;
      }
      if (txMatch != null) {
        totalSent += int.tryParse(txMatch.group(1)!) ?? 0;
      }
    }
    return NetworkStats(receivedBytes: totalReceived, sentBytes: totalSent);
  }

  NetworkStats _parseNetstatOutput(String output) {
    int totalReceived = 0;
    int totalSent = 0;
    final lines = output.split('\n');
    for (final line in lines) {
      final trimmed = line.trim();
      if (trimmed.isEmpty || !trimmed.contains(':')) continue;
      final parts = trimmed.split(RegExp(r'\s+'));
      if (parts.length < 2) continue;
      // netstat -i 格式：Iface MTU RX-OK RX-ERR RX-DRP RX-OVR TX-OK ...
      final rxOk = parts.length > 3 ? int.tryParse(parts[3]) ?? 0 : 0;
      final txOk = parts.length > 7 ? int.tryParse(parts[7]) ?? 0 : 0;
      totalReceived += rxOk;
      totalSent += txOk;
    }
    return NetworkStats(receivedBytes: totalReceived, sentBytes: totalSent);
  }
}
