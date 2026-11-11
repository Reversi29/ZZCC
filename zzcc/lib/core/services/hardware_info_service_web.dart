// lib/core/services/hardware_info_service_web.dart
//
// Web 实现：用 package:web（dart:js_interop）读取真实浏览器信息。
//   - hardwareConcurrency：真实 CPU 逻辑核心数。
//   - deviceMemory：真实内存 GB（仅 Chromium 系提供）。
//   - userAgent：真实浏览器 UA。
// 定义抽象接口 HardwareInfoService 与实现 HardwareInfoServiceImpl。

import 'package:web/web.dart' as web;

/// 硬件信息服务抽象接口（须与 stub/io 实现一致）。
abstract class HardwareInfoService {
  /// 读取硬件信息（设备型号/操作系统/处理器等）。
  Future<Map<String, String>> getHardwareInfo();

  void clearCache();
}

/// Web 实现。
class HardwareInfoServiceImpl extends HardwareInfoService {
  static final HardwareInfoServiceImpl instance = HardwareInfoServiceImpl._();
  HardwareInfoServiceImpl._();

  Map<String, String>? _cachedInfo;

  @override
  Future<Map<String, String>> getHardwareInfo() async {
    if (_cachedInfo != null) return _cachedInfo!;

    try {
      final nav = web.window.navigator;
      final ua = nav.userAgent;

      final info = <String, String>{
        '设备型号': '浏览器',
        '操作系统': _detectOs(ua),
        '处理器': '${nav.hardwareConcurrency} 逻辑核心',
        '内存': _detectMemory(nav),
        '存储': '浏览器环境',
        '显卡': '浏览器渲染',
        '分辨率': '${web.window.innerWidth}×${web.window.innerHeight}',
      };
      _cachedInfo = info;
      return info;
    } catch (_) {
      _cachedInfo = {
        '设备型号': '浏览器',
        '操作系统': '未知',
        '处理器': '未知',
        '内存': '未知',
        '存储': '浏览器环境',
        '显卡': '浏览器渲染',
        '分辨率': '未知',
      };
      return _cachedInfo!;
    }
  }

  String _detectOs(String ua) {
    if (ua.contains('Windows')) return 'Windows';
    if (ua.contains('Mac OS X')) return 'macOS';
    if (ua.contains('Linux')) {
      if (ua.contains('Android')) return 'Android';
      return 'Linux';
    }
    if (ua.contains('iPhone') || ua.contains('iPad')) return 'iOS/iPadOS';
    return '未知系统';
  }

  String _detectMemory(web.Navigator nav) {
    final mem = nav.deviceMemory;
    if (mem > 0) return '${mem.toStringAsFixed(1)} GB';
    return '未知';
  }

  @override
  void clearCache() => _cachedInfo = null;
}
