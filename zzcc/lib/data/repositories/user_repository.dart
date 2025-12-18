import 'package:zzcc/data/models/user_model.dart';
import 'package:zzcc/data/sources/user_local_data_source.dart';
import 'package:zzcc/data/sources/user_remote_data_source.dart';

class UserRepository {
  final UserRemoteDataSource remoteDataSource;
  final UserLocalDataSource localDataSource;

  UserRepository({
    required this.remoteDataSource,
    required this.localDataSource,
  });

  Future<UserModel> login(String uid, String password) async {
    final remoteUser = await remoteDataSource.login(uid, password);
    await localDataSource.saveUser(remoteUser);
    return remoteUser;
  }

  Future<UserModel> getCurrentUser() async {
    final localUser = await localDataSource.getUser();
    if (localUser != null) {
      return localUser;
    }
    // 移除avatarFile参数
    return UserModel(
      name: '未登录用户',
      uid: '',
      userDataPath: null,
      isLoggedIn: false,
    );
  }

  Future<void> logout() async {
    await localDataSource.clearUser();
  }
}