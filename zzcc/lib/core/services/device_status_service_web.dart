// lib/core/services/device_status_service_web.dart
//
// Web 实现：用 package:web（dart:js_interop）读取真实浏览器信息。
//   - hardwareConcurrency：真实 CPU 逻辑核心数。
//   - deviceMemory：真实内存 GB（仅 Chromium 系提供）。
//   - userAgent：真实浏览器 UA。
// 定义抽象接口 DeviceStatusService 与实现 DeviceStatusServiceImpl。

import 'package:web/web.dart' as web;

import 'package:zzcc/data/models/device_status_model.dart';

/// 设备状态服务抽象接口（须与 stub/io 实现一致）。
abstract class DeviceStatusService {
  /// 读取设备状态。
  Future<DeviceStatusData> getDeviceStatus();
}

/// Web 实现。
class DeviceStatusServiceImpl implements DeviceStatusService {
  @override
  Future<DeviceStatusData> getDeviceStatus() async {
    try {
      final nav = web.window.navigator;
      final cores = nav.hardwareConcurrency;
      final memGb = nav.deviceMemory;

      final ua = nav.userAgent;
      final osLabel = _detectOs(ua);

      return DeviceStatusData(
        osName: osLabel,
        osVersion: '浏览器环境',
        machine: 'Web 浏览器',
        platformLabel: 'Web',
        isWeb: true,
        usages: [
          DeviceUsage(
            label: 'CPU',
            value: 0.0,
            detail: '$cores 逻辑核心',
            colorKey: 'blue',
          ),
          DeviceUsage(
            label: '内存',
            value: 0.0,
            detail: memGb > 0
                ? '~${memGb.toStringAsFixed(0)} GB 可用'
                : '浏览器未提供',
            colorKey: 'orange',
          ),
          DeviceUsage(
            label: '系统',
            value: 0.0,
            detail: osLabel,
            colorKey: 'green',
          ),
        ],
      );
    } catch (e) {
      return DeviceStatusData.unknown('浏览器读取失败: $e');
    }
  }

  String _detectOs(String ua) {
    if (ua.contains('Windows NT')) return 'Windows';
    if (ua.contains('Mac OS X')) return 'macOS';
    if (ua.contains('Android')) return 'Android';
    if (ua.contains('iPhone') || ua.contains('iPad')) return 'iOS';
    if (ua.contains('Linux')) return 'Linux';
    return '未知系统';
  }
}
