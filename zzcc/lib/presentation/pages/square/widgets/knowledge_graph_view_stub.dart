import 'package:flutter/material.dart';

class KnowledgeGraphView extends StatelessWidget {
  const KnowledgeGraphView({super.key});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              '知识图谱 3D 暂不支持 Web 端',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            const Text(
              '请用手机、iOS、macOS 或 Windows 端查看 3D 图谱。',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }
}
