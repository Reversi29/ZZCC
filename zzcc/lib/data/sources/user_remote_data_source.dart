import 'package:zzcc/data/models/user_model.dart';

abstract class UserRemoteDataSource {
  Future<UserModel> login(String uid, String password);
  Future<UserModel> register(String name, String uid, String password);
}

class UserRemoteDataSourceImpl implements UserRemoteDataSource {
  @override
  Future<UserModel> login(String uid, String password) async {
    // 登录逻辑实现
    await Future.delayed(const Duration(milliseconds: 500));
    return UserModel(
      name: "用户",
      uid: uid,
      userDataPath: null, // 移除avatarFile参数
      isLoggedIn: true,
    );
  }

  @override
  Future<UserModel> register(String name, String uid, String password) async {
    // 注册逻辑实现
    await Future.delayed(const Duration(milliseconds: 500));
    return UserModel(
      name: name,
      uid: uid,
      userDataPath: null, // 移除avatarFile参数
      isLoggedIn: false,
    );
  }
}
    