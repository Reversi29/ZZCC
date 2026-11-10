// lib/presentation/pages/home/widgets/device_status_widget.dart
//
// 设备状态组件（真实数据）。
// Native：用 system_info2 读取真实 CPU 核心数 / 内存总量与可用量。
// Web：用浏览器 navigator（hardwareConcurrency / deviceMemory）。
// 定时刷新（5 秒）以反映内存变化。

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/services/device_status_service.dart';
import 'package:zzcc/data/models/device_status_model.dart';

class DeviceStatusWidget extends StatefulWidget {
  const DeviceStatusWidget({super.key});

  @override
  State<DeviceStatusWidget> createState() => _DeviceStatusWidgetState();
}

class _DeviceStatusWidgetState extends State<DeviceStatusWidget> {
  DeviceStatusService get _service => getIt<DeviceStatusService>();
  DeviceStatusData? _data;
  bool _loading = true;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _refresh();
    // 每 5 秒刷新一次（内存等指标动态变化）。
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final data = await _service.getDeviceStatus();
      if (!mounted) return;
      setState(() {
        _data = data;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  Color _colorFor(String key) {
    switch (key) {
      case 'orange':
        return Colors.orange;
      case 'green':
        return Colors.green;
      case 'purple':
        return Colors.purple;
      case 'blue':
      default:
        return Colors.blue;
    }
  }

  Widget _buildUsageIndicator(DeviceUsage usage) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(usage.label,
                  style: const TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w500)),
              const Spacer(),
              Text(usage.detail,
                  style: TextStyle(fontSize: 11, color: Colors.grey[600])),
            ],
          ),
          const SizedBox(height: 4),
          Stack(
            children: [
              Container(
                height: 8,
                decoration: BoxDecoration(
                  color: Colors.grey[200],
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
              FractionallySizedBox(
                widthFactor: usage.value.clamp(0.0, 1.0),
                child: Container(
                  height: 8,
                  decoration: BoxDecoration(
                    color: _colorFor(usage.colorKey),
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 3),
          Text(
            usage.value > 0
                ? '${(usage.value * 100).toStringAsFixed(1)}%'
                : '—',
            style: const TextStyle(fontSize: 11),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.monitor_heart_outlined, size: 22, color: Colors.indigo),
                const SizedBox(width: 8),
                const Text('设备状态',
                    style:
                        TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.refresh, size: 16),
                  tooltip: '刷新',
                  onPressed: _refresh,
                ),
              ],
            ),
            const SizedBox(height: 6),
            if (_loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 16),
                child: Center(
                    child: SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2))),
              )
            else if (_data == null || _data!.usages.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Text('无法读取设备状态',
                    style: TextStyle(fontSize: 12, color: Colors.grey[600])),
              )
            else ...[
              // 系统信息行
              Row(
                children: [
                  Icon(Icons.computer, size: 14, color: Colors.grey[600]),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      '${_data!.osName} ${_data!.osVersion}',
                      style:
                          TextStyle(fontSize: 12, color: Colors.grey[700]),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (_data!.isWeb)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 5, vertical: 1),
                      decoration: BoxDecoration(
                        color: Colors.teal.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: const Text('浏览器',
                          style: TextStyle(fontSize: 10, color: Colors.teal)),
                    ),
                ],
              ),
              const SizedBox(height: 8),
              ..._data!.usages.map(_buildUsageIndicator),
            ],
          ],
        ),
      ),
    );
  }
}
