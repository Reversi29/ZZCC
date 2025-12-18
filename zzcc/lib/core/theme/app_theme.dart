import 'package:flutter/material.dart';

class AppTheme {
  static const double padding = 16.0;
  static const double radius = 12.0;
  
  static BoxDecoration cardDecoration(BuildContext context) {
    return BoxDecoration(
      color: Theme.of(context).cardColor,
      borderRadius: BorderRadius.circular(radius),
      boxShadow: const [
        BoxShadow(
          color: Colors.black12,
          blurRadius: 6,
          offset: Offset(0, 2),
        )
      ],
    );
  }
  
  static TextStyle titleStyle(BuildContext context) {
    return TextStyle(
      fontSize: 20,
      fontWeight: FontWeight.bold,
      color: Theme.of(context).primaryColor,
    );
  }
}

// 示例代码语法
/*
Container(
  decoration: AppTheme.cardDecoration(context),
  padding: const EdgeInsets.all(AppTheme.padding),
  child: Text('标题', style: AppTheme.titleStyle(context)),
)
*/