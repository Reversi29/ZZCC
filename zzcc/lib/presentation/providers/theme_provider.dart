import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/data/models/theme_model.dart';
import 'package:flutter/material.dart';

final themeProvider = StateNotifierProvider<ThemeNotifier, CustomTheme>(
  (ref) => ThemeNotifier(),
);

class ThemeNotifier extends StateNotifier<CustomTheme> {
  ThemeNotifier() : super(const CustomTheme(primaryColor: Colors.blue));

  void changeTheme(CustomTheme newTheme) {
    // 添加主题切换动画
    TweenAnimationBuilder<Color?>(
      duration: const Duration(milliseconds: 300),
      tween: ColorTween(
        begin: state.primaryColor,
        end: newTheme.primaryColor,
      ),
      builder: (context, value, child) {
        state = newTheme.copyWith(primaryColor: value);
        return child!;
      },
      child: const SizedBox(),
    );
  }
  
  void toggleDarkMode() {
    state = CustomTheme(
      primaryColor: state.primaryColor,
      leftSidebarColor: state.leftSidebarColor,
      rightPanelColor: state.rightPanelColor,
      leftBackgroundImage: state.leftBackgroundImage,
      rightBackgroundImage: state.rightBackgroundImage,
      name: state.name,
    );
  }
}