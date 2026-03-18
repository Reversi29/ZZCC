// lib/core/services/hardware_info_service.dart
import 'dart:io';
import 'package:device_info_plus/device_info_plus.dart';

class HardwareInfoService {
  static final HardwareInfoService instance = HardwareInfoService._();
  HardwareInfoService._();

  Map<String, String>? _cachedInfo;

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
    }

    _cachedInfo = info;
    return info;
  }

  void clearCache() => _cachedInfo = null;
}