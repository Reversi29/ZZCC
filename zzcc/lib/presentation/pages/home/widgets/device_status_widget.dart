import 'package:flutter/material.dart';

class DeviceStatusWidget extends StatelessWidget {
  const DeviceStatusWidget({super.key});

  Widget _buildUsageIndicator(String label, double value, Color color) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label),
          const SizedBox(height: 6),
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
                widthFactor: value,
                child: Container(
                  height: 8,
                  decoration: BoxDecoration(
                    color: color,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text('${(value * 100).toStringAsFixed(1)}%', style: const TextStyle(fontSize: 12),),
        ],
      ),
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
                Icon(Icons.device_thermostat, size: 30),
                SizedBox(width: 10),
                Text('设备状态', style: TextStyle(fontSize: 18)),
              ],
            ),
            const SizedBox(height: 20),
            _buildUsageIndicator('CPU', 0.65, Colors.blue),
            _buildUsageIndicator('GPU', 0.42, Colors.green),
            _buildUsageIndicator('内存', 0.78, Colors.orange),
            _buildUsageIndicator('硬盘', 0.35, Colors.purple),
          ],
        ),
      ),
    );
  }
}