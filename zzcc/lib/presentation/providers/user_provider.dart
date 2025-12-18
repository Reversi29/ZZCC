import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:io';
import 'package:path/path.dart' as path;
import 'package:intl/intl.dart';
import 'package:zzcc/core/services/logger_service.dart'; // 引入logger_service
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/data/models/user_model.dart';

// 提供用户状态
final userProvider = StateNotifierProvider<UserNotifier, UserModel>((ref) {
  return UserNotifier();
});

// 用户状态管理
class UserNotifier extends StateNotifier<UserModel> {
  UserNotifier() : super(UserModel(name: '', uid: '', isLoggedIn: false));  // 添加初始登录状态
  DateTime _avatarUpdateTime = DateTime.now();
    
  // 获取头像更新时间戳（供UI监听）
  DateTime get avatarUpdateTime => _avatarUpdateTime;

  // 添加更新用户名的方法（供ProfilePage调用）
  void updateUserName(String newName) {
    if (newName.isNotEmpty) {
      state = state.copyWith(name: newName);
    }
  }

  // 登录用户
  void loginUser({
    required String name,
    required String uid,
    required String userDataPath,
  }) {
    state = UserModel(
      name: name,
      uid: uid,
      userDataPath: userDataPath,
      isLoggedIn: true,
    );
  }

  // 登出用户
  void logoutUser() {
    state = UserModel(
      name: state.name,
      uid: state.uid,
      isLoggedIn: false,  // 显式设置登录状态
    );
  }

  // 更新用户数据路径
  void updateUserDataPath(String newPath) {
    state = state.copyWith(userDataPath: newPath);
  }

  // 获取当前头像路径
  String? getCurrentAvatarPath() {
    if (state.userDataPath == null) return null;

    final avatarsDir = Directory(path.join(state.userDataPath!, 'avatars'));
    if (!avatarsDir.existsSync()) return null;

    final currentAvatarPattern = RegExp(r'^\d{4}_\d{2}_\d{2}T\d{2}_\d{2}_\d{2}-\.[a-zA-Z0-9]+$');
    final files = avatarsDir.listSync().whereType<File>();

    for (final file in files) {
      final fileName = path.basename(file.path);
      if (currentAvatarPattern.hasMatch(fileName)) {
        return file.path;
      }
    }

    return null;
  }

  // 保存新头像
  Future<String?> saveNewAvatar(File imageFile) async {
    if (state.userDataPath == null) return null;

    try {
      final avatarsDir = Directory(path.join(state.userDataPath!, 'avatars'));
      if (!avatarsDir.existsSync()) {
        await avatarsDir.create(recursive: true);
      }

      // 处理旧头像
      final currentAvatarPath = getCurrentAvatarPath();
      if (currentAvatarPath != null) {
        final oldFile = File(currentAvatarPath);
        final oldFileName = path.basename(oldFile.path);
        final createDate = oldFileName.split('-').first;
        final extension = path.extension(oldFileName);
        final updateDate = DateFormat('yyyy_MM_ddTHH_mm_ss').format(DateTime.now());
        final newOldFileName = '$createDate-$updateDate$extension';
        await oldFile.rename(path.join(avatarsDir.path, newOldFileName));
      }

      // 保存新头像
      final createDate = DateFormat('yyyy_MM_ddTHH_mm_ss').format(DateTime.now());
      final extension = path.extension(imageFile.path);
      final newFileName = '$createDate-.${extension.replaceFirst('.', '')}';
      final newFile = await imageFile.copy(path.join(avatarsDir.path, newFileName));

      if (newFile.path.isNotEmpty) {
        _avatarUpdateTime = DateTime.now();
        return newFile.path;
      }
      return null;
    } catch (e) {
      getIt<LoggerService>().error('保存头像失败: $e');
      return null;
    }
  }

  // 添加这个方法用于主动更新时间戳，触发UI刷新
  void updateAvatarTimestamp() {
    _avatarUpdateTime = DateTime.now();
    // 这行代码会通知所有监听者状态已更新
    state = state.copyWith();
  }

  // 获取历史头像列表
  List<String> getHistoryAvatars() {
    if (state.userDataPath == null) return [];

    final avatarsDir = Directory(path.join(state.userDataPath!, 'avatars'));
    if (!avatarsDir.existsSync()) return [];

    final files = avatarsDir.listSync().whereType<File>().toList();
    final historyAvatars = <String>[];

    final historyPattern = RegExp(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*$');

    for (final file in files) {
      final fileName = path.basename(file.path);
      if (historyPattern.hasMatch(fileName)) {
        historyAvatars.add(file.path);
      }
    }

    historyAvatars.sort((a, b) {
      final aUpdateDate = path.basename(a).split('-').elementAt(1);
      final bUpdateDate = path.basename(b).split('-').elementAt(1);
      return bUpdateDate.compareTo(aUpdateDate);
    });

    return historyAvatars;
  }
}