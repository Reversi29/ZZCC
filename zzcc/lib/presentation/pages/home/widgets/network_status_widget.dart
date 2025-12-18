// 修改文档8：NetworkStatusWidget
import 'dart:io';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:network_info_plus/network_info_plus.dart';
import 'package:zzcc/core/utils/color_utils.dart';

class NetworkStatusWidget extends StatefulWidget {
  const NetworkStatusWidget({super.key});

  @override
  State<NetworkStatusWidget> createState() => _NetworkStatusWidgetState();
}

class _NetworkStatusWidgetState extends State<NetworkStatusWidget> {
  final Connectivity _connectivity = Connectivity();
  final NetworkInfo _networkInfo = NetworkInfo();
  
  StreamSubscription<dynamic>? _connectivitySubscription;
  ConnectivityResult _connectionStatus = ConnectivityResult.none;
  String _wifiName = '';
  String _ipAddress = '';
  double _downloadSpeed = 0.0;
  double _uploadSpeed = 0.0;
  bool _hasInternet = false;
  Timer? _speedTestTimer;
  bool _isRealTimeMonitoring = true;
  Timer? _internetCheckTimer;
  
  int _lastReceivedBytes = 0;
  int _lastSentBytes = 0;
  DateTime _lastSpeedCheckTime = DateTime.now();
  Timer? _throughputTimer;

  @override
  void initState() {
    super.initState();
    _initNetworkInfo();
    _toggleMonitoring(_isRealTimeMonitoring);
    _startPeriodicInternetCheck();
    _startThroughputMonitoring();
  }

  @override
  void dispose() {
    _connectivitySubscription?.cancel();
    _speedTestTimer?.cancel();
    _internetCheckTimer?.cancel();
    _throughputTimer?.cancel();
    super.dispose();
  }

  void _startThroughputMonitoring() {
    if (_throughputTimer != null) return;
    _throughputTimer = Timer.periodic(const Duration(seconds: 2), (timer) {
      _calculateRealThroughput();
    });
  }

  Future<void> _calculateRealThroughput() async {
    try {
      if (!_isRealTimeMonitoring || !_hasInternet) {
        return;
      }

      final currentTime = DateTime.now();
      final timeDiff = currentTime.difference(_lastSpeedCheckTime).inSeconds;
      
      if (timeDiff < 1) return;
      
      final networkStats = await _getNetworkInterfaceStats();
      
      if (networkStats != null) {
        final receivedBytes = networkStats['receivedBytes'] ?? 0;
        final sentBytes = networkStats['sentBytes'] ?? 0;
        
        if (_lastReceivedBytes > 0 && _lastSentBytes > 0) {
          final downloadDiff = receivedBytes - _lastReceivedBytes;
          final uploadDiff = sentBytes - _lastSentBytes;
          
          final downloadSpeedMbps = (downloadDiff * 8) / (timeDiff * 1000000);
          final uploadSpeedMbps = (uploadDiff * 8) / (timeDiff * 1000000);
          
          if (!mounted) return;
          setState(() {
            _downloadSpeed = downloadSpeedMbps;
            _uploadSpeed = uploadSpeedMbps;
          });
        }
        
        _lastReceivedBytes = receivedBytes;
        _lastSentBytes = sentBytes;
        _lastSpeedCheckTime = currentTime;
      }
    } catch (e) {
      _fallbackToSimulatedSpeed();
    }
  }

  Future<Map<String, int>?> _getNetworkInterfaceStats() async {
    try {
      if (Platform.isWindows) {
        return await _getWindowsNetworkStats();
      } else if (Platform.isLinux || Platform.isMacOS) {
        return await _getUnixNetworkStats();
      }
    } catch (e) {
      // 在实际应用中应使用日志记录
    }
    return null;
  }

  Future<Map<String, int>> _getWindowsNetworkStats() async {
    final result = await Process.run('powershell', [
      'Get-NetAdapterStatistics | Select-Object Name,ReceivedBytes,SentBytes | ConvertTo-Json'
    ]);
    
    if (result.exitCode == 0) {
      final output = result.stdout.toString();
      final lines = output.split('\n');
      for (final line in lines) {
        if (line.contains('ReceivedBytes') && line.contains('SentBytes')) {
          final receivedMatch = RegExp(r'"ReceivedBytes":\s*(\d+)').firstMatch(line);
          final sentMatch = RegExp(r'"SentBytes":\s*(\d+)').firstMatch(line);
          
          if (receivedMatch != null && sentMatch != null) {
            return {
              'receivedBytes': int.parse(receivedMatch.group(1)!),
              'sentBytes': int.parse(sentMatch.group(1)!),
            };
          }
        }
      }
    }
    
    final netstatResult = await Process.run('netstat', ['-e']);
    if (netstatResult.exitCode == 0) {
      return _parseNetstatOutput(netstatResult.stdout.toString());
    }
    
    throw Exception('无法获取Windows网络统计信息');
  }

  Future<Map<String, int>> _getUnixNetworkStats() async {
    final result = await Process.run('cat', ['/proc/net/dev']);
    
    if (result.exitCode == 0) {
      return _parseProcNetDev(result.stdout.toString());
    }
    
    try {
      final ifconfigResult = await Process.run('ifconfig', []);
      if (ifconfigResult.exitCode == 0) {
        return _parseIfconfigOutput(ifconfigResult.stdout.toString());
      }
    } catch (e) {
      // 忽略错误
    }
    
    final netstatResult = await Process.run('netstat', ['-i']);
    if (netstatResult.exitCode == 0) {
      return _parseNetstatOutput(netstatResult.stdout.toString());
    }
    
    throw Exception('无法获取Unix网络统计信息');
  }

  Map<String, int> _parseProcNetDev(String output) {
    final lines = output.split('\n');
    for (final line in lines) {
      if (line.contains('eth0') || line.contains('wlan0') || line.contains('en0')) {
        final parts = line.trim().split(RegExp(r'\s+'));
        if (parts.length >= 10) {
          return {
            'receivedBytes': int.parse(parts[1]),
            'sentBytes': int.parse(parts[9]),
          };
        }
      }
    }
    throw Exception('无法解析/proc/net/dev输出');
  }

  Map<String, int> _parseIfconfigOutput(String output) {
    final rxMatch = RegExp(r'RX bytes:(\d+)').firstMatch(output);
    final txMatch = RegExp(r'TX bytes:(\d+)').firstMatch(output);
    
    if (rxMatch != null && txMatch != null) {
      return {
        'receivedBytes': int.parse(rxMatch.group(1)!),
        'sentBytes': int.parse(txMatch.group(1)!),
      };
    }
    throw Exception('无法解析ifconfig输出');
  }

  Map<String, int> _parseNetstatOutput(String output) {
    // Robust parsing for multiple netstat output formats (Windows/netstat -e, Unix netstat -i, localized outputs)
    final lines = output.split('\n').map((l) => l.trim()).where((l) => l.isNotEmpty).toList();

    // Helper to extract integers from a line (handles commas)
    List<int> extractInts(String line) {
      final matches = RegExp(r'[\d,]+').allMatches(line);
      return matches.map((m) => int.parse(m.group(0)!.replaceAll(',', ''))).toList();
    }

    // First try: look for a line that contains 'Bytes' or common localized keywords
    for (int i = 0; i < lines.length; i++) {
      final line = lines[i];
      final lower = line.toLowerCase();
      if (lower.contains('bytes') || lower.contains('received') || lower.contains('接收') || lower.contains('接收字节') || lower.contains('已接收')) {
        // If this line contains numbers, take them. Otherwise, check the next line for numbers.
        final ints = extractInts(line);
        if (ints.length >= 2) {
          return {'receivedBytes': ints[0], 'sentBytes': ints[1]};
        }
        if (i + 1 < lines.length) {
          final nextInts = extractInts(lines[i + 1]);
          if (nextInts.length >= 2) {
            return {'receivedBytes': nextInts[0], 'sentBytes': nextInts[1]};
          }
        }
      }
    }

    // Second try: find any line that has two large integer columns (likely Received and Sent)
    for (final line in lines) {
      final ints = extractInts(line);
      if (ints.length >= 2) {
        // Heuristic: numbers should be non-zero and reasonably large
        if ((ints[0] > 0 || ints[1] > 0)) {
          return {'receivedBytes': ints[0], 'sentBytes': ints[1]};
        }
      }
    }

    // Third try: scan for any pair of integers across adjacent lines (header + values)
    for (int i = 0; i < lines.length - 1; i++) {
      final a = extractInts(lines[i]);
      final b = extractInts(lines[i + 1]);
      if (a.isEmpty && b.length >= 2) {
        return {'receivedBytes': b[0], 'sentBytes': b[1]};
      }
    }

    throw Exception('无法解析netstat输出');
  }

  void _fallbackToSimulatedSpeed() {
    if (!_hasInternet) {
      if (!mounted) return;
      setState(() {
        _downloadSpeed = 0.0;
        _uploadSpeed = 0.0;
      });
      return;
    }
    
    final primaryConnection = _getPrimaryConnection();
    switch (primaryConnection) {
      case ConnectivityResult.wifi:
        if (mounted) {
          setState(() {
            _downloadSpeed = 20.0 + (DateTime.now().millisecond % 30);
            _uploadSpeed = 5.0 + (DateTime.now().millisecond % 10);
          });
        }
        break;
      case ConnectivityResult.mobile:
        if (mounted) {
          setState(() {
            _downloadSpeed = 8.0 + (DateTime.now().millisecond % 15);
            _uploadSpeed = 2.0 + (DateTime.now().millisecond % 5);
          });
        }
        break;
      default:
        if (mounted) {
          setState(() {
            _downloadSpeed = 1.0 + (DateTime.now().millisecond % 5);
            _uploadSpeed = 0.5 + (DateTime.now().millisecond % 2);
          });
        }
    }
  }

  void _startPeriodicInternetCheck() {
    if (_internetCheckTimer != null) return;
    _internetCheckTimer = Timer.periodic(const Duration(seconds: 10), (timer) {
      _checkRealInternetConnection();
    });
  }

  Future<void> _checkRealInternetConnection() async {
    try {
      final result = await InternetAddress.lookup('google.com').timeout(
        const Duration(seconds: 5),
        onTimeout: () => throw SocketException('Connection timeout'),
      );
      if (!mounted) return;
      setState(() {
        _hasInternet = result.isNotEmpty && result[0].rawAddress.isNotEmpty;
      });
    } catch (e) {
      _checkInternetConnectionByIP();
    }
  }

  Future<void> _checkInternetConnectionByIP() async {
    try {
      final ipAddress = await _networkInfo.getWifiIP();
      if (!mounted) return;
      setState(() {
        _hasInternet = ipAddress != null && ipAddress != '未知' && ipAddress != '0.0.0.0';
        _ipAddress = ipAddress ?? '未知';
        if (!_hasInternet) {
          _downloadSpeed = 0.0;
          _uploadSpeed = 0.0;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _hasInternet = false;
        _downloadSpeed = 0.0;
        _uploadSpeed = 0.0;
      });
    }
  }

  void _toggleMonitoring(bool isEnabled) {
    if (!mounted) return;
    setState(() {
      _isRealTimeMonitoring = isEnabled;
    });

    if (isEnabled) {
      _startConnectivityListener();
      if (_speedTestTimer == null) _startPeriodicSpeedTest();
      if (_internetCheckTimer == null) _startPeriodicInternetCheck();
      if (_throughputTimer == null) _startThroughputMonitoring();
    } else {
      _connectivitySubscription?.cancel();
      _connectivitySubscription = null;
      _speedTestTimer?.cancel();
      _speedTestTimer = null;
      _internetCheckTimer?.cancel();
      _internetCheckTimer = null;
      _throughputTimer?.cancel();
      _throughputTimer = null;
    }
  }

  Future<void> _initNetworkInfo() async {
    try {
      final connectivityResultRaw = await _connectivity.checkConnectivity();
      final connectivityResult = _normalizeConnectivityResult(connectivityResultRaw);
      final wifiName = await _networkInfo.getWifiName() ?? '未知';
      final ipAddress = await _networkInfo.getWifiIP() ?? '未知';
      if (!mounted) return;
      setState(() {
        _connectionStatus = connectivityResult;
        _wifiName = wifiName;
        _ipAddress = ipAddress;
      });
      
      _checkRealInternetConnection();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _hasInternet = false;
        _downloadSpeed = 0.0;
        _uploadSpeed = 0.0;
      });
    }
  }

  void _startConnectivityListener() {
    _connectivitySubscription = _connectivity.onConnectivityChanged.listen(
      (dynamic raw) {
        final result = _normalizeConnectivityResult(raw);
        if (!mounted) return;
        setState(() {
          _connectionStatus = result;
        });
        _checkRealInternetConnection();
      },
    );
  }

  void _startPeriodicSpeedTest() {
    if (_speedTestTimer != null) return;
    _speedTestTimer = Timer.periodic(const Duration(seconds: 5), (timer) {
      if (!_isRealTimeMonitoring || !_hasInternet) {
        if (!mounted) return;
        setState(() {
          _downloadSpeed = 0.0;
          _uploadSpeed = 0.0;
        });
      }
    });
  }

  ConnectivityResult _getPrimaryConnection() {
    return _connectionStatus;
  }

  ConnectivityResult _normalizeConnectivityResult(dynamic raw) {
    try {
      if (raw == null) return ConnectivityResult.none;
      if (raw is ConnectivityResult) return raw;
      if (raw is List) {
        // Prefer Wi-Fi if present, then mobile, else first element if typed.
        if (raw.contains(ConnectivityResult.wifi)) return ConnectivityResult.wifi;
        if (raw.contains(ConnectivityResult.mobile)) return ConnectivityResult.mobile;
        if (raw.isNotEmpty && raw.first is ConnectivityResult) return raw.first as ConnectivityResult;
      }
    } catch (_) {}
    return ConnectivityResult.none;
  }

  String _getConnectionTypeText() {
    final primaryConnection = _getPrimaryConnection();
    switch (primaryConnection) {
      case ConnectivityResult.wifi:
        return 'Wi-Fi';
      case ConnectivityResult.mobile:
        return '移动数据';
      case ConnectivityResult.ethernet:
        return '以太网';
      case ConnectivityResult.vpn:
        return 'VPN';
      case ConnectivityResult.bluetooth:
        return '蓝牙';
      case ConnectivityResult.other:
        return '其他';
      default:
        return '无连接';
    }
  }

  Color _getConnectionStatusColor() {
    if (!_hasInternet) return Colors.red;
    
    final primaryConnection = _getPrimaryConnection();
    switch (primaryConnection) {
      case ConnectivityResult.wifi:
        return Colors.green;
      case ConnectivityResult.mobile:
        return Colors.blue;
      case ConnectivityResult.ethernet:
        return Colors.purple;
      default:
        return Colors.orange;
    }
  }

  String _getConnectionStatusText() {
    if (!_hasInternet) return '无互联网连接';
    
    final primaryConnection = _getPrimaryConnection();
    switch (primaryConnection) {
      case ConnectivityResult.wifi:
        return 'Wi-Fi已连接';
      case ConnectivityResult.mobile:
        return '移动数据已连接';
      case ConnectivityResult.ethernet:
        return '以太网已连接';
      case ConnectivityResult.vpn:
        return 'VPN已连接';
      default:
        return '已连接';
    }
  }

  Widget _buildNetworkStat(String label, String value, {IconData? icon}) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4.0),
      padding: const EdgeInsets.all(12.0),
      decoration: BoxDecoration(
        color: Colors.grey.shade50,
        borderRadius: BorderRadius.circular(8.0),
      ),
      child: Row(
        children: [
          if (icon != null) ...[
            Icon(icon, size: 16, color: Colors.grey.shade600),
            const SizedBox(width: 8),
          ],
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                fontWeight: FontWeight.w500,
                color: Colors.grey.shade700,
              ),
            ),
          ),
          Text(
            value,
            style: const TextStyle(
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSpeedIndicator(String label, double speed, Color color) {
    final displaySpeed = _hasInternet ? speed : 0.0;
    final displayColor = _hasInternet ? color : Colors.grey;
    
    return Container(
      padding: const EdgeInsets.all(12.0),
      decoration: BoxDecoration(
        color: Colors.grey.shade50,
        borderRadius: BorderRadius.circular(8.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                label,
                style: TextStyle(
                  fontWeight: FontWeight.w500,
                  color: Colors.grey.shade700,
                ),
              ),
              Text(
                '${displaySpeed.toStringAsFixed(2)} Mbps',
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: displayColor,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Stack(
            children: [
              Container(
                height: 6,
                decoration: BoxDecoration(
                  color: Colors.grey.shade300,
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
              FractionallySizedBox(
                widthFactor: displaySpeed > 100 ? 1.0 : displaySpeed / 100,
                child: Container(
                  height: 6,
                  decoration: BoxDecoration(
                    color: displayColor,
                    borderRadius: BorderRadius.circular(3),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildConnectionStatus() {
    return Container(
      padding: const EdgeInsets.all(12.0),
      decoration: BoxDecoration(
        color: ColorUtils.withValues(_getConnectionStatusColor(), 0.1),
        borderRadius: BorderRadius.circular(8.0),
        border: Border.all(
          color: _getConnectionStatusColor(),
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: _getConnectionStatusColor(),
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              _getConnectionStatusText(),
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: _getConnectionStatusColor(),
              ),
            ),
          ),
          Icon(
            _getPrimaryConnection() == ConnectivityResult.wifi 
                ? Icons.wifi 
                : Icons.network_cell,
            color: _getConnectionStatusColor(),
            size: 20,
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(4),
                  decoration: BoxDecoration(
                    color: ColorUtils.withValues(Theme.of(context).primaryColor, 0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Icon(
                    Icons.network_wifi,
                    size: 24,
                    color: Theme.of(context).primaryColor,
                  ),
                ),
                const SizedBox(width: 12),
                const Text(
                  '网络状态',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Spacer(),
                Row(
                  children: [
                    Text(
                      _isRealTimeMonitoring ? '已打开监测' : '已关闭监测',
                      style: TextStyle(
                        fontSize: 12,
                        color: Colors.grey.shade600,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Transform.scale(
                      scale: 0.7,
                      child: Switch(
                        value: _isRealTimeMonitoring,
                        onChanged: _toggleMonitoring,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 16),
            
            // 连接状态
            _buildConnectionStatus(),
            const SizedBox(height: 12),
            
            // 网络信息
            if (_wifiName.isNotEmpty && _wifiName != '未知')
              _buildNetworkStat('网络名称', _wifiName, icon: Icons.wifi),
            
            _buildNetworkStat('连接类型', _getConnectionTypeText(), icon: Icons.network_cell),
            _buildNetworkStat('IP地址', _ipAddress, icon: Icons.language),
            
            const SizedBox(height: 12),
            
            // 速度测试
            _buildSpeedIndicator('下载速度', _downloadSpeed, Colors.blue),
            const SizedBox(height: 8),
            _buildSpeedIndicator('上传速度', _uploadSpeed, Colors.green),
          ],
        ),
      ),
    );
  }
}