import 'dart:io';
import 'package:flutter/material.dart';

class CustomTheme {
  final Color primaryColor;
  final Color? leftSidebarColor;
  final Color? rightPanelColor;
  final File? leftBackgroundImage;
  final File? rightBackgroundImage;
  final String name;

  const CustomTheme({
    required this.primaryColor,
    this.leftSidebarColor,
    this.rightPanelColor,
    this.leftBackgroundImage,
    this.rightBackgroundImage,
    this.name = "未命名主题",
  });

  ThemeData toThemeData() {
    return ThemeData(
      primaryColor: primaryColor,
      scaffoldBackgroundColor: Colors.transparent,
      colorScheme: ColorScheme.fromSeed(seedColor: primaryColor),
    );
  }

  CustomTheme copyWith({
    Color? primaryColor,
    Color? leftSidebarColor,
    Color? rightPanelColor,
    File? leftBackgroundImage,
    File? rightBackgroundImage,
    String? name,
  }) {
    return CustomTheme(
      primaryColor: primaryColor ?? this.primaryColor,
      leftSidebarColor: leftSidebarColor ?? this.leftSidebarColor,
      rightPanelColor: rightPanelColor ?? this.rightPanelColor,
      leftBackgroundImage: leftBackgroundImage ?? this.leftBackgroundImage,
      rightBackgroundImage: rightBackgroundImage ?? this.rightBackgroundImage,
      name: name ?? this.name,
    );
  }
}