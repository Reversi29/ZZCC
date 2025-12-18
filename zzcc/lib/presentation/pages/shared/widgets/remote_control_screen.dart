import 'package:flutter/material.dart';
import 'package:get_it/get_it.dart';
import 'package:zzcc/core/services/net_service.dart';
import 'package:zzcc/data/models/network_model.dart';

class RemoteControlScreen extends StatefulWidget {
  const RemoteControlScreen({super.key});

  @override
  State<RemoteControlScreen> createState() => _RemoteControlScreenState();
}

class _RemoteControlScreenState extends State<RemoteControlScreen> {
  final ApiService _apiService = GetIt.I<ApiService>();
  NetworkInfo? _networkInfo;
  List<NetworkDevice> _devices = [];
  
  @override
  void initState() {
    super.initState();
    _loadNetworkInfo();
    _scanDevices();
  }
  
  Future<void> _loadNetworkInfo() async {
    final response = await _apiService.getNetworkInfo();
    if (response.code == 200 && response.data != null) {
      if (mounted) {
        setState(() => _networkInfo = response.data);
      }
    }
  }
  
  Future<void> _scanDevices() async {
    final response = await _apiService.scanNetworkDevices();
    if (response.code == 200 && response.data != null && mounted) {
      setState(() => _devices = response.data!);
    }
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('远程控制')),
      body: Column(
        children: [
          if (_networkInfo != null) _buildNetworkInfoCard(),
          const SizedBox(height: 20),
          Expanded(
            child: ListView.builder(
              itemCount: _devices.length,
              itemBuilder: (context, index) => _buildDeviceCard(_devices[index]),
            ),
          ),
        ],
      ),
    );
  }
  
  Widget _buildNetworkInfoCard() {
    final info = _networkInfo!;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('网络状态: ${info.connectionType}', style: const TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            Text('IP地址: ${info.ipAddress}'),
            Text('子网掩码: ${info.subnetMask}'),
            Text('网关: ${info.gateway}'),
            Text('DNS: ${info.dnsServers.join(", ")}'),
            Text('信号强度: ${info.signalStrength}%'),
            Text('上传速度: ${info.uploadSpeed.toStringAsFixed(1)} Mbps'),
            Text('下载速度: ${info.downloadSpeed.toStringAsFixed(1)} Mbps'),
          ],
        ),
      ),
    );
  }
  
  Widget _buildDeviceCard(NetworkDevice device) {
    return ListTile(
      leading: Icon(_getDeviceIcon(device.deviceType), size: 40),
      title: Text(device.name),
      subtitle: Text('${device.ipAddress} • ${_getDeviceTypeName(device.deviceType)}'),
      trailing: Icon(device.isOnline ? Icons.wifi : Icons.wifi_off, color: device.isOnline ? Colors.green : Colors.grey),
      onTap: () => _connectToDevice(device.id),
    );
  }
  
  Future<void> _connectToDevice(String deviceId) async {
    final response = await _apiService.connectToDevice(deviceId);
    if (mounted) {
      if (response.data == true) {
        // 导航到设备控制页面
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('设备连接成功')),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('连接失败: ${response.message}')),
        );
      }
    }
  }
  
  // 根据设备类型获取图标
  IconData _getDeviceIcon(DeviceType type) {
    switch (type) {
      case DeviceType.desktop:
        return Icons.desktop_windows;
      case DeviceType.laptop:
        return Icons.laptop;
      case DeviceType.mobile:
        return Icons.smartphone;
      case DeviceType.tablet:
        return Icons.tablet;
      case DeviceType.tv:
        return Icons.tv;
      case DeviceType.nas:
        return Icons.storage;
      case DeviceType.printer:
        return Icons.print;
      default:
        return Icons.device_unknown;
    }
  }
  
  // 根据设备类型获取可读名称
  String _getDeviceTypeName(DeviceType type) {
    switch (type) {
      case DeviceType.desktop:
        return '台式电脑';
      case DeviceType.laptop:
        return '笔记本电脑';
      case DeviceType.mobile:
        return '手机';
      case DeviceType.tablet:
        return '平板电脑';
      case DeviceType.tv:
        return '智能电视';
      case DeviceType.nas:
        return '网络存储';
      case DeviceType.printer:
        return '打印机';
      default:
        return '其他设备';
    }
  }
}