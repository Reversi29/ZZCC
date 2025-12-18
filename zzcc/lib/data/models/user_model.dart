class UserModel {
  final String name;
  final String uid;
  final String? userDataPath;
  final bool isLoggedIn;

  UserModel({
    required this.name,
    required this.uid,
    this.userDataPath,
    required this.isLoggedIn,  // 添加required修饰符
  });

  UserModel copyWith({
    String? name,
    String? uid,
    String? userDataPath,
    bool? isLoggedIn,
  }) {
    return UserModel(
      name: name ?? this.name,
      uid: uid ?? this.uid,
      userDataPath: userDataPath ?? this.userDataPath,
      isLoggedIn: isLoggedIn ?? this.isLoggedIn,
    );
  }
}