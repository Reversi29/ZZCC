import 'package:flutter/material.dart';

class AutoSizeContent extends StatelessWidget {
  final String text;

  const AutoSizeContent({super.key, required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.white,
      padding: const EdgeInsets.all(20),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              text,
              style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 20),
            LayoutBuilder(
              builder: (context, constraints) {
                return Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: List.generate(15, (index) => Chip(
                    label: Text('标签 ${index + 1}'),
                    backgroundColor: Colors.blue[100],
                  )),
                );
              },
            ),
            const SizedBox(height: 20),
            Image.asset(
              'assets/icons/foreground.png',
              width: 150,
              height: 150,
              fit: BoxFit.contain,
            ),
          ],
        ),
      ),
    );
  }
}