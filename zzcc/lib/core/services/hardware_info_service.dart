// lib/core/services/hardware_info_service.dart
//
// 硬件信息读取服务（条件导入）：
//   - Native（dart.library.io）：用 device_info_plus 读取真实硬件信息。
//   - Web：用 universal_html 的 navigator 读取浏览器信息，不崩溃。
//
// 接口 HardwareInfoService 与实现 HardwareInfoServiceImpl 定义在各平台文件中，
// 条件导出确保使用对应平台的具体实现。

export 'hardware_info_service_stub.dart'
    if (dart.library.io) 'hardware_info_service_io.dart'
    if (dart.library.js_interop) 'hardware_info_service_web.dart';
