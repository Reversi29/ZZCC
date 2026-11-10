// lib/core/services/device_status_service_stub.dart
//
// 兜底 stub（非常规平台）：返回未知状态。
// 定义抽象接口 DeviceStatusService 与实现 DeviceStatusServiceImpl。

import 'package:zzcc/data/models/device_status_model.dart';

/// 设备状态服务抽象接口（须与 io/web 实现一致）。
abstract class DeviceStatusService {
  /// 读取设备状态。
  Future<DeviceStatusData> getDeviceStatus();
}

/// 兜底实现。
class DeviceStatusServiceImpl implements DeviceStatusService {
  @override
  Future<DeviceStatusData> getDeviceStatus() async {
    return DeviceStatusData.unknown('当前平台不支持');
  }
}
