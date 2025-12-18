import 'package:zzcc/data/models/user_model.dart';

abstract class UserLocalDataSource {
  Future<void> saveUser(UserModel user);
  Future<UserModel?> getUser();
  Future<void> clearUser();
}

class UserLocalDataSourceImpl implements UserLocalDataSource {
  @override
  Future<void> saveUser(UserModel user) async {
    // 实现本地存储逻辑（保存name, uid, userDataPath, isLoggedIn）
    // 示例：使用SharedPreferences
    // final prefs = await SharedPreferences.getInstance();
    // await prefs.setString('name', user.name);
    // await prefs.setString('uid', user.uid);
    // await prefs.setString('userDataPath', user.userDataPath ?? '');
    // await prefs.setBool('isLoggedIn', user.isLoggedIn);
  }

  @override
  Future<UserModel?> getUser() async {
    // 从本地读取用户信息
    // 示例：
    // final prefs = await SharedPreferences.getInstance();
    // final name = prefs.getString('name') ?? '';
    // final uid = prefs.getString('uid') ?? '';
    // final userDataPath = prefs.getString('userDataPath');
    // final isLoggedIn = prefs.getBool('isLoggedIn') ?? false;
    // return UserModel(name: name, uid: uid, userDataPath: userDataPath, isLoggedIn: isLoggedIn);
    return null;
  }

  @override
  Future<void> clearUser() async {
    // 清除本地用户信息
  }
}