import 'package:flutter/material.dart';

class LocationWidget extends StatelessWidget {
  const LocationWidget({super.key});

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
                Icon(Icons.location_on, size: 30),
                SizedBox(width: 10),
                Text('位置信息', style: TextStyle(fontSize: 18)),
              ],
            ),
            const SizedBox(height: 20),
            Container(
              height: 200,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(8),
                color: Colors.grey[200],
              ),
              child: const Center(
                child: Icon(Icons.map, size: 60, color: Colors.grey),
              ),
            ),
            const SizedBox(height: 10),
            const Row(
              children: [
                Icon(Icons.location_pin, size: 16),
                SizedBox(width: 8),
                Text('上海市浦东新区张江高科技园区'),
              ],
            ),
          ],
        ),
      ),
    );
  }
}