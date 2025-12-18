// lib/core/utils/color_utils.dart
import 'dart:ui';

class ColorUtils {
  /// 获取颜色的红色分量 (0-255)
  static int getRed(Color color) => (color.toARGB32() >> 16) & 0xFF;
  
  /// 获取颜色的绿色分量 (0-255)
  static int getGreen(Color color) => (color.toARGB32() >> 8) & 0xFF;
  
  /// 获取颜色的蓝色分量 (0-255)
  static int getBlue(Color color) => color.toARGB32() & 0xFF;
  
  /// 获取颜色的透明度分量 (0-255)
  static int getAlpha(Color color) => (color.toARGB32() >> 24) & 0xFF;
  
  /// 创建具有新透明度的颜色
  static Color withValues(Color color, double opacity) {
    return Color.fromARGB(
      (opacity * 255).round(),
      getRed(color),
      getGreen(color),
      getBlue(color),
    );
  }
  
  /// 将颜色转换为 HEX 字符串 (例如 #FF0000)
  static String toHex(Color color) {
    return '#${(color.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0').toUpperCase()}';
  }
  
  /// 将颜色转换为 RGB 字符串 (例如 "255, 0, 0")
  static String toRgb(Color color) {
    return '${getRed(color)}, ${getGreen(color)}, ${getBlue(color)}';
  }
  
  /// 将颜色转换为 RGBA 字符串 (例如 "255, 0, 0, 1.0")
  static String toRgba(Color color) {
    return '${getRed(color)}, ${getGreen(color)}, ${getBlue(color)}, ${getAlpha(color) / 255}';
  }
}