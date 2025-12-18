// lib/core/providers/font_provider.dart

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/core/di/service_locator.dart';

class FontNotifier extends StateNotifier<String?> {
  FontNotifier() : super(null) {
    _init();
  }

  Future<void> _init() async {
    // 从Hive加载保存的字体
    final savedFont = await getIt<StorageService>().getSavedFont();
    state = savedFont;
  }

  Future<void> updateFont(String font) async {
    // 保存到Hive
    await getIt<StorageService>().savePreferredFont(font);
    // 更新状态
    state = font;
  }
}

final fontFamilyProvider = StateNotifierProvider<FontNotifier, String?>(
  (ref) => FontNotifier(),
);