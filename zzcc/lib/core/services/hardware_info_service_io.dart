// lib/core/services/hardware_info_service_io.dart
//
// Native 实现：用 device_info_plus 的 DeviceInfoPlugin 读取真实硬件信息。
// 定义抽象接口 HardwareInfoService 与实现 HardwareInfoServiceImpl。

import 'dart:io';
import 'package:device_info_plus/device_info_plus.dart';

/// 硬件信息服务抽象接口（须与 stub/web 实现一致）。
abstract class HardwareInfoService {
  /// 读取硬件信息（设备型号/操作系统/处理器等）。
  Future<Map<String, String>> getHardwareInfo();

  void clearCache();
}

/// Native 实现。
class HardwareInfoServiceImpl extends HardwareInfoService {
  static final HardwareInfoServiceImpl instance = HardwareInfoServiceImpl._();
  HardwareInfoServiceImpl._();

  Map<String, String>? _cachedInfo;

  @override
  Future<Map<String, String>> getHardwareInfo() async {
    if (_cachedInfo != null) return _cachedInfo!;

    final info = <String, String>{};
    final deviceInfo = DeviceInfoPlugin();

    try {
      if (Platform.isWindows) {
        final win = await deviceInfo.windowsInfo;
        info['设备型号'] = win.computerName;
        info['操作系统'] = 'Windows ${win.majorVersion}.${win.minorVersion}';
        info['处理器'] = 'Windows 处理器';
      } else if (Platform.isMacOS) {
        final mac = await deviceInfo.macOsInfo;
        info['设备型号'] = mac.model;
        info['操作系统'] = 'macOS ${mac.osRelease}';
        info['处理器'] = 'macOS 处理器';
      } else if (Platform.isAndroid) {
        final android = await deviceInfo.androidInfo;
        info['设备型号'] = android.model;
        info['操作系统'] = 'Android ${android.version.release}';
        info['处理器'] = 'ARM 处理器';
      } else if (Platform.isIOS) {
        final ios = await deviceInfo.iosInfo;
        info['设备型号'] = ios.utsname.machine;
        info['操作系统'] = 'iOS ${ios.systemVersion}';
        info['处理器'] = 'Apple 芯片';
      } else {
        info['设备型号'] = '未知设备';
        info['操作系统'] = '未知系统';
        info['处理器'] = '未知处理器';
      }

      info['内存'] = '未知内存';
      info['存储'] = '未知存储';
      info['显卡'] = '未知显卡';
      info['分辨率'] = '未知分辨率';
    } catch (e) {
      info['设备型号'] = '获取失败';
      info['操作系统'] = '获取失败';
      info['处理器'] = '获取失败';
      info['内存'] = '未知内存';
      info['存储'] = '未知存储';
      info['显卡'] = '未知显卡';
      info['分辨率'] = '未知分辨率';
    }

    _cachedInfo = info;
    return info;
  }

  @override
  void clearCache() => _cachedInfo = null;
}
