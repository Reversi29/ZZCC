import 'package:flutter/material.dart';

class ActivityBarItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final int index;
  final bool isActive;
  final Function() onPressed;
  
  const ActivityBarItem({
    super.key,
    required this.icon,
    required this.label,
    required this.index,
    required this.isActive,
    required this.onPressed,
  });
  
  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: label,
      child: IconButton(
        icon: Icon(icon, color: isActive ? Colors.blue : Colors.grey),
        onPressed: onPressed,
      ),
    );
  }
}