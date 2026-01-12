import 'package:flutter/material.dart';

class TestPage extends StatelessWidget {
  const TestPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const _TestScaffold();
  }
}

class _TestScaffold extends StatelessWidget {
  const _TestScaffold();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: const [
            Icon(Icons.bug_report, size: 64, color: Colors.orange),
            SizedBox(height: 16),
            Text('Test Mode', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            SizedBox(height: 8),
            Text('Placeholder test page (debug only).'),
          ],
        ),
      ),
    );
  }
}
