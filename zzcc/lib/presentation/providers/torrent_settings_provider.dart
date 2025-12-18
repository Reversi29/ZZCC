import 'package:flutter_riverpod/flutter_riverpod.dart';

final settingsProvider = StateNotifierProvider<SettingsNotifier, SettingsState>((ref) {
  return SettingsNotifier();
});

class SettingsState {
  final bool neverShowAddTorrentDialog;
  
  SettingsState({
    this.neverShowAddTorrentDialog = false,
  });
  
  SettingsState copyWith({
    bool? neverShowAddTorrentDialog,
  }) {
    return SettingsState(
      neverShowAddTorrentDialog: neverShowAddTorrentDialog ?? this.neverShowAddTorrentDialog,
    );
  }
}

class SettingsNotifier extends StateNotifier<SettingsState> {
  SettingsNotifier() : super(SettingsState());
  
  Future<void> setNeverShowAddTorrentDialog(bool value) async {
    state = state.copyWith(neverShowAddTorrentDialog: value);
    // 持久化存储
    // await _storageService.saveSetting('neverShowAddTorrentDialog', value);
  }
}