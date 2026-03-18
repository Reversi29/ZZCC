// lib/presentation/pages/home/widgets/hardware_details_widget.dart
import 'package:flutter/material.dart';
import 'package:zzcc/core/services/hardware_info_service.dart';

class HardwareDetailsWidget extends StatefulWidget {
  const HardwareDetailsWidget({super.key});

  @override
  State<HardwareDetailsWidget> createState() => _HardwareDetailsWidgetState();
}

class _HardwareDetailsWidgetState extends State<HardwareDetailsWidget> {
  final HardwareInfoService service = HardwareInfoService.instance;
  late Future<Map<String, String>> _info;

  @override
  void initState() {
    super.initState();
    _info = service.getHardwareInfo();
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.all(16),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.computer, color: Colors.blueAccent),
                SizedBox(width: 8),
                Text(
                  "设备硬件信息",
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const Divider(height: 24),

            FutureBuilder<Map<String, String>>(
              future: _info,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (!snapshot.hasData) {
                  return const Text("获取信息失败");
                }

                final data = snapshot.data!;
                return Column(
                  children: [
                    _item("设备型号", data['设备型号']!),
                    _item("操作系统", data['操作系统']!),
                    _item("处理器", data['处理器']!),
                    _item("内存", data['内存']!),
                    _item("存储", data['存储']!),
                    _item("显卡", data['显卡']!),
                    _item("分辨率", data['分辨率']!),
                  ],
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _item(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Text("$label: ", style: const TextStyle(fontWeight: FontWeight.w500)),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}