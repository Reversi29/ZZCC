import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
// import 'package:zzcc/core/utils/storage_manager.dart';
import 'package:zzcc/presentation/providers/user_provider.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:path/path.dart' as path;
import 'package:zzcc/core/routes/route_names.dart';
import 'package:go_router/go_router.dart';
import 'package:zzcc/data/repositories/chat_repository.dart';

class ProfilePage extends ConsumerStatefulWidget {
  final Function(File?) onAvatarChanged;
  final File? initialAvatar;

  const ProfilePage({
    super.key,
    required this.onAvatarChanged,
    this.initialAvatar,
  });

  @override
  ConsumerState<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends ConsumerState<ProfilePage> {
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _bioController = TextEditingController();
  bool _isEditing = false;

  @override
  void initState() {
    super.initState();
    _loadUserData();
  }

  Future<void> _loadUserData() async {
    final user = ref.read(userProvider);
    String? bio;

    // 优先从user_data.hive获取bio
    if (user.isLoggedIn && user.userDataPath != null) {
      try {
        final storageService = getIt<StorageService>();
        // userDataPath是包含ciphertext的完整路径，需要提取ciphertext部分
        // 假设userDataPath格式为"{appDataPath}/{ciphertext}"
        final ciphertext = path.basename(user.userDataPath!);
        bio = await storageService.getUserInfoByKey(ciphertext, 'bio') as String?;
      } catch (e) {
        debugPrint('从Hive读取bio失败: $e');
      }
    }

    if (mounted) {
      setState(() {
        _nameController.text = user.name;
        _bioController.text = bio ?? '';
      });
    }
  }

  Future<File?> pickAndCropImage(String title, double aspectRatio) async {
    final picker = ImagePicker();
    final pickedFile = await picker.pickImage(source: ImageSource.gallery);
    if (pickedFile != null) {
      return File(pickedFile.path);
    }
    return null;
  }

  Future<void> _pickAvatar() async {
    try {
      final user = ref.read(userProvider);
      if (!user.isLoggedIn) return;
      
      final picker = ImagePicker();
      final picked = await picker.pickImage(source: ImageSource.gallery);
      
      if (picked != null && mounted) {
        final newAvatarFile = File(picked.path);
        // 保存新头像并获取路径
        final newAvatarPath = await ref.read(userProvider.notifier)
            .saveNewAvatar(newAvatarFile);
        
        // 关键：刷新UI显示新头像
        if (newAvatarPath != null) {
          // 方法1：通过setState强制刷新（适用于Consumer外的UI）
          // setState(() {});
          
          // 方法2：如果使用了Consumer监听，可通过更新provider状态触发重建
          ref.read(userProvider.notifier).updateAvatarTimestamp();
        }
      }
    } catch (e) {
      debugPrint('头像选择失败: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('头像更新失败: $e')),
        );
      }
    }
  }

  void _saveProfile() async {
    if (!_isEditing) return;

    final newName = _nameController.text.trim();
    final newBio = _bioController.text.trim();
    final user = ref.read(userProvider);

    if (newName.isEmpty || !user.isLoggedIn) return;

    try {
      // 1. 更新userProvider中的昵称（实时同步到UI）
      ref.read(userProvider.notifier).updateUserName(newName);

      // 2. 同步到user_data.hive
      final storageService = getIt<StorageService>();
      // 读取现有用户信息
      final currentInfo = await storageService.getUserInfo(user.userDataPath!) ?? {};
      // 合并新信息
      final updatedInfo = {
        ...currentInfo,
        'name': newName,
        'bio': newBio,
        'updatedAt': DateTime.now().toIso8601String(), // 记录更新时间
      };
      // 写入Hive
      await storageService.updateUserInfo(user.userDataPath!, updatedInfo);

      // 3. 切换到查看模式
      if (mounted) { // 添加mounted检查
        setState(() => _isEditing = false);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('信息保存成功')),
        );
      }
    } catch (e) {
      if (mounted) { // 添加mounted检查
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('保存失败: ${e.toString()}')),
        );
      }
    }
  }

  Widget _buildUserAvatar() {
    // 使用Consumer包裹头像组件，确保状态变化时重建
    return Consumer(
      builder: (context, ref, _) {
        // 监听头像更新时间戳，确保变化时重建
        ref.watch(userProvider.select((state) => ref.read(userProvider.notifier).avatarUpdateTime));
        
        // 每次重建时获取最新的头像路径
        final currentAvatarPath = ref.read(userProvider.notifier).getCurrentAvatarPath();
        final avatarFile = currentAvatarPath != null ? File(currentAvatarPath) : null;

        return Center(
          child: Column(
            children: [
              GestureDetector(
                onTap: _pickAvatar,
                child: CircleAvatar(
                  radius: 60,
                  backgroundColor: Colors.grey[200],
                  // 直接使用最新的头像文件
                  backgroundImage: avatarFile != null ? FileImage(avatarFile) : null,
                  child: avatarFile == null
                      ? const Icon(Icons.person, size: 60, color: Colors.grey)
                      : null,
                ),
              ),
              const SizedBox(height: 15),
              TextButton(
                onPressed: _pickAvatar,
                child: const Text('更换头像'),
              ),
            ],
          ),
        );
      },
    );
  }

  void _handleLogout() async {
    showDialog(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('确认退出'),
        content: const Text('确定要退出当前账号吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () async {
              ref.read(userProvider.notifier).logoutUser();
              final storageService = getIt<StorageService>();
              storageService.clearCurrentUser();
              Navigator.pop(dialogContext);
              
              if (mounted) {
                // 关键修改：确保路径格式正确
                GoRouter.of(context).go('${RouteNames.root}${RouteNames.login}');
                
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('已成功退出登录')),
                );
              }
            },
            child: const Text('退出'),
          ),
        ],
      ),
    );
  }

  void _handleDeleteAccount() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('注销账号'),
        content: const Text(
          '注销后你的账号将从服务器永久删除，所有聊天记录和好友关系将无法恢复。\n\n'
          '此操作不可撤销，请三思。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('取消'),
          ),
          TextButton(
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('确认注销'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    // 二次确认
    final messenger = ScaffoldMessenger.of(context);
    final router = GoRouter.of(context);
    final doubleConfirmed = await showDialog<bool>(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        title: const Text('再次确认'),
        content: const Text('确定要永久删除你的账号吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx, false),
            child: const Text('取消'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.red,
              foregroundColor: Colors.white,
            ),
            onPressed: () => Navigator.pop(dialogCtx, true),
            child: const Text('永久删除'),
          ),
        ],
      ),
    );

    if (doubleConfirmed != true) return;

    // 执行注销
    if (!mounted) return;
    final chatRepo = getIt<ChatRepository>();
    final storageService = getIt<StorageService>();

    try {
      await chatRepo.deleteAccount(erase: true);
    } catch (e) {
      if (!mounted) return;
      messenger.showSnackBar(
        SnackBar(content: Text('注销失败: $e')),
      );
      return;
    }

    // 清除本地数据
    storageService.clearCurrentUser();
    ref.read(userProvider.notifier).logoutUser();

    if (!mounted) return;
    router.go('${RouteNames.root}${RouteNames.login}');
    messenger.showSnackBar(
      const SnackBar(content: Text('账号已注销')),
    );
  }

  @override
  Widget build(BuildContext context) {
    // final user = ref.watch(userProvider);
    return Container(
      color: Colors.white,
      padding: const EdgeInsets.all(20),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '个人资料',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 30),
            _buildUserAvatar(),
            const SizedBox(height: 30),
            _buildInfoForm(),
            const SizedBox(height: 30),
            _buildAccountSection(),
            const SizedBox(height: 30),
            _buildSocialSection(),
            const SizedBox(height: 30),
            _buildSecuritySection(),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoForm() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '基本信息',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 15),
        TextField(
          controller: _nameController,
          decoration: const InputDecoration(
            labelText: '用户名',
            border: OutlineInputBorder(),
            prefixIcon: Icon(Icons.person),
          ),
          enabled: _isEditing,
        ),
        const SizedBox(height: 15),
        TextField(
          controller: _bioController,
          decoration: const InputDecoration(
            labelText: '个人简介',
            border: OutlineInputBorder(),
            prefixIcon: Icon(Icons.info),
          ),
          maxLines: 3,
          enabled: _isEditing,
        ),
        const SizedBox(height: 20),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            if (!_isEditing)
              ElevatedButton(
                onPressed: () => setState(() => _isEditing = true),
                child: const Text('编辑信息'),
              ),
            if (_isEditing) ...[
              TextButton(
                onPressed: () => setState(() => _isEditing = false),
                child: const Text('取消'),
              ),
              const SizedBox(width: 10),
              ElevatedButton(
                onPressed: _saveProfile,
                child: const Text('保存'),
              ),
            ]
          ],
        ),
      ],
    );
  }


  Widget _buildAccountSection() {
    final user = ref.watch(userProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '账号信息',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: Colors.grey[100],
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            children: [
              const Icon(Icons.fingerprint, color: Colors.grey),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('UID', style: TextStyle(fontSize: 12, color: Colors.grey)),
                    Text(
                      user.uid.isNotEmpty ? user.uid : '未登录',
                      style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500),
                    ),
                  ],
                ),
              ),
              if (user.uid.isNotEmpty)
                IconButton(
                  icon: const Icon(Icons.copy, size: 20),
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: user.uid));
                    if (mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('UID 已复制')),
                      );
                    }
                  },
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSocialSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '社交账号',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 15),
        _buildSocialItem(Icons.email, '邮箱', 'user@example.com'),
        _buildSocialItem(Icons.phone, '手机', '+86 138 **** 1234'),
        _buildSocialItem(Icons.link, '个人网站', 'https://example.com'),
        _buildSocialItem(Icons.work, '职业', '软件工程师'),
        _buildSocialItem(Icons.location_on, '所在地', '上海市'),
      ],
    );
  }

  Widget _buildSocialItem(IconData icon, String label, String value) {
    return ListTile(
      leading: Icon(icon, color: Theme.of(context).primaryColor),
      title: Text(label),
      subtitle: Text(value),
      trailing: _isEditing 
          ? IconButton(
              icon: const Icon(Icons.edit, size: 20),
              onPressed: () {},
            )
          : null,
    );
  }

  Widget _buildSecuritySection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '账号安全',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 15),
        ListTile(
          title: const Text('修改密码'),
          leading: const Icon(Icons.lock),
          trailing: const Icon(Icons.arrow_forward_ios, size: 16),
          onTap: () {
            // 可以添加修改密码的导航
          },
        ),
        const Divider(height: 1),
        ListTile(
          title: const Text('注销账号'),
          leading: const Icon(Icons.dangerous, color: Colors.red),
          textColor: Colors.red,
          onTap: _handleDeleteAccount,
        ),
        const Divider(height: 1),
        ListTile(
          title: const Text('退出登录'),
          leading: const Icon(Icons.logout, color: Colors.red),
          textColor: Colors.red,
          onTap: _handleLogout, // 绑定退出登录方法
        ),
      ],
    );
  }

  // Widget _buildSecurityItem(String title, String subtitle) {
  //   return ListTile(
  //     title: Text(title),
  //     subtitle: Text(subtitle),
  //     trailing: IconButton(
  //       icon: const Icon(Icons.arrow_forward, size: 20),
  //       onPressed: () {},
  //     ),
  //   );
  // }
}