// lib/core/services/network_stats_service.dart
//
// 网络统计与互联网探测服务（条件导入）：
//   - Native（dart.library.io）：用 Process/InternetAddress 读取真实接口统计与连通性。
//   - Web：用 universal_html 的 navigator.connection 探测，不崩溃。
//
// 接口 NetworkStatsService 与实现 NetworkStatsServiceImpl 定义在各平台文件中，
// 条件导出确保使用对应平台的具体实现。

export 'network_stats_service_stub.dart'
    if (dart.library.io) 'network_stats_service_io.dart'
    if (dart.library.js_interop) 'network_stats_service_web.dart';
