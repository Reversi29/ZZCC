// lib/core/services/device_status_service_io.dart
//
// Native 实现：用 system_info2 的 SysInfo 读取真实系统信息。
// 定义抽象接口 DeviceStatusService 与实现 DeviceStatusServiceImpl。

import 'dart:io';
import 'package:system_info2/system_info2.dart';
import 'package:zzcc/data/models/device_status_model.dart';

/// 设备状态服务抽象接口（须与 stub/web 实现一致）。
abstract class DeviceStatusService {
  /// 读取设备状态。
  Future<DeviceStatusData> getDeviceStatus();
}

/// Native 实现。
class DeviceStatusServiceImpl implements DeviceStatusService {
  @override
  Future<DeviceStatusData> getDeviceStatus() async {
    try {
      final cores = SysInfo.cores;
      final totalMem = SysInfo.getTotalPhysicalMemory();
      final availMem = SysInfo.getAvailablePhysicalMemory();

      final coreCount = cores.isNotEmpty ? cores.length : 1;
      final cpuName = cores.isNotEmpty ? cores.first.name : '未知 CPU';

      // 内存使用率 = (总量 - 可用) / 总量。
      final usedMem = totalMem > 0 ? (totalMem - availMem) : 0;
      final memPct = totalMem > 0 ? (usedMem / totalMem) : 0.0;

      final osName = SysInfo.operatingSystemName.isNotEmpty
          ? SysInfo.operatingSystemName
          : Platform.operatingSystem;
      final osVersion = SysInfo.operatingSystemVersion;

      return DeviceStatusData(
        osName: osName,
        osVersion: osVersion,
        machine: _machineName(),
        platformLabel: _platformLabel(),
        isWeb: false,
        usages: [
          DeviceUsage(
            label: 'CPU',
            value: 0.0,
            detail: '$coreCount 核 · $cpuName',
            colorKey: 'blue',
          ),
          DeviceUsage(
            label: '内存',
            value: memPct.clamp(0.0, 1.0),
            detail: '${_gb(availMem)} / ${_gb(totalMem)} 可用',
            colorKey: 'orange',
          ),
          DeviceUsage(
            label: '系统',
            value: 0.0,
            detail: '$osName $osVersion',
            colorKey: 'green',
          ),
        ],
      );
    } catch (e) {
      return DeviceStatusData.unknown('读取失败: $e');
    }
  }

  String _machineName() {
    try {
      final name = SysInfo.userName;
      return name.isNotEmpty ? name : '本机';
    } catch (_) {
      return '本机';
    }
  }

  String _platformLabel() {
    if (Platform.isMacOS) return 'macOS';
    if (Platform.isWindows) return 'Windows';
    if (Platform.isLinux) return 'Linux';
    return Platform.operatingSystem;
  }

  static String _gb(int bytes) {
    if (bytes <= 0) return '未知';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }
}
