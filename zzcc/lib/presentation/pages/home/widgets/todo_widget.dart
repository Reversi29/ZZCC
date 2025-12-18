import 'package:flutter/material.dart';

class TodoWidget extends StatelessWidget {
  const TodoWidget({super.key});

  Widget _buildTodoItem(String text, bool completed) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4.0),
      child: Row(
        children: [
          Checkbox(value: completed, onChanged: (_) {}),
          Text(text, style: TextStyle(decoration: completed ? TextDecoration.lineThrough : null)),
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
                Icon(Icons.checklist, size: 30),
                SizedBox(width: 10),
                Text('待办事宜', style: TextStyle(fontSize: 18)),
              ],
            ),
            const SizedBox(height: 10),
            _buildTodoItem('完成Flutter项目', true),
            _buildTodoItem('准备会议材料', false),
            _buildTodoItem('回复客户邮件', false),
            _buildTodoItem('团队周会', true),
          ],
        ),
      ),
    );
  }
}