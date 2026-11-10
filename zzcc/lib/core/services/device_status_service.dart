// lib/core/services/device_status_service.dart
//
// 设备状态读取服务（条件导入）：
//   - Native（dart.library.io）：用 system_info2 读取真实 CPU/内存信息。
//   - Web：用 universal_html 的 navigator（hardwareConcurrency / deviceMemory）。
//
// 接口 DeviceStatusService 与实现 DeviceStatusServiceImpl 定义在各平台文件中，
// 条件导出确保使用对应平台的具体实现。

export 'device_status_service_stub.dart'
    if (dart.library.io) 'device_status_service_io.dart'
    if (dart.library.js_interop) 'device_status_service_web.dart';
