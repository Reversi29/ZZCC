import 'package:flutter/material.dart';

class HardwareDetailsWidget extends StatelessWidget {
  const HardwareDetailsWidget({super.key});

  TableRow _buildTableRow(String title1, String value1, String title2, String value2) {
    return TableRow(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Text(title1, style: const TextStyle(fontWeight: FontWeight.bold)),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Text(value1),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Text(title2, style: const TextStyle(fontWeight: FontWeight.bold)),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Text(value2),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.info, size: 30),
                SizedBox(width: 10),
                Text('硬件详细信息', style: TextStyle(fontSize: 18)),
              ],
            ),
            const SizedBox(height: 20),
            Table(
              columnWidths: const {
                0: FlexColumnWidth(1.5),
                1: FlexColumnWidth(2),
                2: FlexColumnWidth(1.5),
                3: FlexColumnWidth(2),
              },
              children: [
                _buildTableRow('设备型号', 'Dell XPS 15 9520', '操作系统', 'Windows 11 Pro'),
                _buildTableRow('处理器', 'Intel Core i7-12700H', '显卡', 'NVIDIA RTX 3050 Ti'),
                _buildTableRow('内存', '32GB DDR5 4800MHz', '存储', '1TB NVMe SSD'),
                _buildTableRow('网络', 'WiFi 6E', '蓝牙', '5.2'),
                _buildTableRow('分辨率', '3840×2400', '刷新率', '60Hz'),
              ],
            ),
          ],
        ),
      ),
    );
  }
}