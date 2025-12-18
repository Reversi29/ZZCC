// lib/presentation/providers/sidebar_provider.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/presentation/widgets/resizable_panel.dart';

final sidebarProvider = StateNotifierProvider<SidebarNotifier, double>((ref) {
  return SidebarNotifier();
});

class SidebarNotifier extends StateNotifier<double> {
  SidebarNotifier() : super(200.0);
  
  double _previousWidth = 200.0;

  void updateWidth(double newWidth) {
    final clampedWidth = newWidth.clamp(ResizablePanel.minWidth, ResizablePanel.maxWidth);
    
    // 允许自由设置宽度
    state = clampedWidth;
    
    // 更新记忆宽度
    if (clampedWidth > 0) {
      _previousWidth = clampedWidth;
    }
  }
  
  void toggle() {
    if (state > 0) {
      _previousWidth = state;
      state = 0;
    } else {
      // 恢复时确保宽度至少为最小宽度
      state = _previousWidth < ResizablePanel.minWidth 
          ? ResizablePanel.minWidth 
          : _previousWidth;
    }
  }
}