// lib/data/models/shared_file_settings_model.dart
class SharedFileSettingsModel {
  final String? defaultSavePath;
  final String maxDownloadSpeed;
  final String maxUploadSpeed;
  // 新增字段
  final String? lastUsedPath; // 上一次使用的路径
  final String? incompleteTorrentPath; // 不完整torrent保存路径
  final bool isManualMode; // 管理模式状态
  final bool useDifferentIncompletePath; // 是否勾选不完整路径
  final bool rememberLastPath; // 是否记住上次保存路径

  SharedFileSettingsModel({
    this.defaultSavePath,
    this.maxDownloadSpeed = '无限制',
    this.maxUploadSpeed = '无限制',
    this.lastUsedPath,
    this.incompleteTorrentPath,
    this.isManualMode = true, // 默认手动模式
    this.useDifferentIncompletePath = false,
    this.rememberLastPath = true,
  });

  SharedFileSettingsModel copyWith({
    String? defaultSavePath,
    String? maxDownloadSpeed,
    String? maxUploadSpeed,
    String? lastUsedPath,
    String? incompleteTorrentPath,
    bool? isManualMode,
    bool? useDifferentIncompletePath,
    bool? rememberLastPath,
  }) {
    return SharedFileSettingsModel(
      defaultSavePath: defaultSavePath ?? this.defaultSavePath,
      maxDownloadSpeed: maxDownloadSpeed ?? this.maxDownloadSpeed,
      maxUploadSpeed: maxUploadSpeed ?? this.maxUploadSpeed,
      lastUsedPath: lastUsedPath ?? this.lastUsedPath,
      incompleteTorrentPath: incompleteTorrentPath ?? this.incompleteTorrentPath,
      isManualMode: isManualMode ?? this.isManualMode,
      useDifferentIncompletePath: useDifferentIncompletePath ?? this.useDifferentIncompletePath,
      rememberLastPath: rememberLastPath ?? this.rememberLastPath,
    );
  }
}