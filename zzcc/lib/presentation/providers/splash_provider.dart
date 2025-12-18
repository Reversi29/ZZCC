import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/services/storage_service.dart';

class SplashAnimationNotifier extends StateNotifier<bool> {
  SplashAnimationNotifier() : super(true) {
    _init();
  }

  Future<void> _init() async {
    // 从存储加载启动动画状态
    final savedStatus = await getIt<StorageService>().getSplashAnimationStatus();
    state = savedStatus;
  }

  Future<void> updateSplashAnimation(bool enable) async {
    // 保存到存储
    await getIt<StorageService>().saveSplashAnimationStatus(enable);
    // 更新状态
    state = enable;
  }
}

// 用于状态管理的Provider
final splashAnimationProvider = StateNotifierProvider<SplashAnimationNotifier, bool>(
  (ref) => SplashAnimationNotifier(),
);