import 'package:flutter/material.dart';

class ShortcutSettingsScreen extends StatefulWidget {
  const ShortcutSettingsScreen({super.key});

  @override
  ShortcutSettingsScreenState createState() => ShortcutSettingsScreenState();
}

class ShortcutSettingsScreenState extends State<ShortcutSettingsScreen> {
  final Map<String, String> shortcuts = {
    '新建窗口': 'Ctrl+N',
    '保存': 'Ctrl+S',
    '刷新': 'F5',
    '全屏': 'F11',
  };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('快捷键设置')),
      body: ListView.builder(
        itemCount: shortcuts.length,
        itemBuilder: (context, index) {
          final key = shortcuts.keys.elementAt(index);
          return ListTile(
            title: Text(key),
            trailing: Text(shortcuts[key]!),
            onTap: () => _editShortcut(key),
          );
        },
      ),
    );
  }

  void _editShortcut(String command) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('设置 $command 快捷键'),
        content: TextField(
          decoration: const InputDecoration(
            hintText: '输入新的快捷键',
            border: OutlineInputBorder(),
          ),
          onChanged: (value) {
            setState(() {
              shortcuts[command] = value;
            });
          },
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('保存'),
          ),
        ],
      ),
    );
  }
}