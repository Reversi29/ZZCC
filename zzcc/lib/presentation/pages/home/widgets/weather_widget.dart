import 'package:flutter/material.dart';

class WeatherWidget extends StatelessWidget {
  const WeatherWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return const Card(
      child: Padding(
        padding: EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.cloud, size: 30),
                SizedBox(width: 10),
                Text('天气预报', style: TextStyle(fontSize: 18)),
              ],
            ),
            SizedBox(height: 10),
            Text('上海: 晴 25°C', style: TextStyle(fontSize: 16)),
            SizedBox(height: 5),
            Text('北京: 多云 22°C', style: TextStyle(fontSize: 16)),
            SizedBox(height: 5),
            Text('广州: 小雨 28°C', style: TextStyle(fontSize: 16)),
          ],
        ),
      ),
    );
  }
}