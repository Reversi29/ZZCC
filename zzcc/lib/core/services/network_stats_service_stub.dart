// lib/core/services/network_stats_service_stub.dart
//
// 兜底 stub（非常规平台）：返回未知统计，探测失败。
// 定义抽象接口 NetworkStatsService 与实现 NetworkStatsServiceImpl。

/// 网络接口统计（字节计数，用于计算吞吐量）。
class NetworkStats {
  final int receivedBytes;
  final int sentBytes;

  const NetworkStats({this.receivedBytes = 0, this.sentBytes = 0});
}

/// 网络统计服务抽象接口（须与 io/web 实现一致）。
abstract class NetworkStatsService {
  /// 读取当前网络接口累计收发字节。失败返回 null。
  Future<NetworkStats?> getNetworkStats();

  /// 探测是否有真实互联网连接。失败返回 false。
  Future<bool> checkInternet();
}

/// 兜底实现。
class NetworkStatsServiceImpl implements NetworkStatsService {
  @override
  Future<NetworkStats?> getNetworkStats() async => null;

  @override
  Future<bool> checkInternet() async => false;
}
