// lib/data/models/device_status_model.dart
//
// 设备状态数据模型。
// 数据来源：Native 用 system_info2 读取真实系统信息；
//          Web 用浏览器 navigator 信息（hardwareConcurrency / deviceMemory）。

/// 单条资源使用率展示项。
class DeviceUsage {
  final String label;
  final double value; // 0.0 - 1.0
  final String detail; // 展示文本，如 "8 核 / 16 线程"、"12.5 GB / 16 GB"
  final String colorKey; // 用于 UI 颜色映射

  const DeviceUsage({
    required this.label,
    required this.value,
    required this.detail,
    this.colorKey = 'blue',
  });
}

/// 设备状态聚合数据。
class DeviceStatusData {
  final String osName;
  final String osVersion;
  final String machine;
  final String platformLabel;
  final bool isWeb;
  final List<DeviceUsage> usages;

  const DeviceStatusData({
    required this.osName,
    required this.osVersion,
    required this.machine,
    required this.platformLabel,
    required this.isWeb,
    required this.usages,
  });

  /// 模拟占位（当无法读取时使用）。
  static DeviceStatusData unknown(String reason) {
    return DeviceStatusData(
      osName: '未知系统',
      osVersion: reason,
      machine: '未知设备',
      platformLabel: '未知',
      isWeb: false,
      usages: const [],
    );
  }
}
