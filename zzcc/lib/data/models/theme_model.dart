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

  /// 序列化为 JSON map（不含 File/背景图路径）。
  Map<String, dynamic> toJson() => {
        'primaryColor': primaryColor.toARGB32(),
        'leftSidebarColor': leftSidebarColor?.toARGB32(),
        'rightPanelColor': rightPanelColor?.toARGB32(),
        'name': name,
      };

  /// 从 JSON map 反序列化。
  factory CustomTheme.fromJson(Map<String, dynamic> json) {
    Color? tryColor(dynamic v) =>
        v is int ? Color(v) : null;

    return CustomTheme(
      primaryColor: tryColor(json['primaryColor']) ?? Colors.blue,
      leftSidebarColor: tryColor(json['leftSidebarColor']),
      rightPanelColor: tryColor(json['rightPanelColor']),
      name: json['name']?.toString() ?? '未命名主题',
    );
  }

  /// 默认浅色主题。
  static const CustomTheme defaultLight = CustomTheme(
    primaryColor: Color(0xFF4361EE),
    leftSidebarColor: Color(0xFFF5F5F5),
    rightPanelColor: Color(0xFFFAFAFA),
    name: '默认浅色',
  );
}
