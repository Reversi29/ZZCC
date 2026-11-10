// lib/core/services/hardware_info_service_stub.dart
//
// 兜底 stub（非常规平台）：返回未知信息。
// 定义抽象接口 HardwareInfoService 与实现 HardwareInfoServiceImpl。

/// 硬件信息服务抽象接口（须与 io/web 实现一致）。
abstract class HardwareInfoService {
  /// 读取硬件信息（设备型号/操作系统/处理器等）。
  Future<Map<String, String>> getHardwareInfo();

  void clearCache();
}

/// 兜底实现。
class HardwareInfoServiceImpl extends HardwareInfoService {
  static final HardwareInfoServiceImpl instance = HardwareInfoServiceImpl._();
  HardwareInfoServiceImpl._();

  Map<String, String>? _cachedInfo;

  @override
  Future<Map<String, String>> getHardwareInfo() async {
    if (_cachedInfo != null) return _cachedInfo!;
    _cachedInfo = {
      '设备型号': '未知设备',
      '操作系统': '未知系统',
      '处理器': '未知处理器',
      '内存': '未知内存',
      '存储': '未知存储',
      '显卡': '未知显卡',
      '分辨率': '未知分辨率',
    };
    return _cachedInfo!;
  }

  @override
  void clearCache() => _cachedInfo = null;
}
