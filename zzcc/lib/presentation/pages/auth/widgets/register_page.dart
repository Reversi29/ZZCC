import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/presentation/providers/user_provider.dart';
import 'package:zzcc/core/services/config_service.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/core/services/logger_service.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/utils/color_utils.dart';
import 'package:zzcc/core/utils/encrypt_utils.dart';
import 'package:zzcc/data/repositories/chat_repository.dart';
import 'dart:io';
import 'dart:math';
import 'package:path/path.dart' as path;

class RegisterPage extends ConsumerStatefulWidget {
  const RegisterPage({super.key});

  @override
  ConsumerState<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends ConsumerState<RegisterPage> {
  late TextEditingController nameController;
  late TextEditingController accountController;
  late TextEditingController passwordController;
  late TextEditingController confirmPasswordController;
  late ConfigService configService;
  late LoggerService loggerService;
  bool _isLoading = false;
  bool _passwordsMatch = true;
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  final bool _nameError = false;
  final bool _passwordError = false;
  final bool _confirmPasswordError = false;
  
  @override
  void initState() {
    super.initState();
    nameController = TextEditingController();
    accountController = TextEditingController();
    passwordController = TextEditingController();
    confirmPasswordController = TextEditingController();
    configService = getIt<ConfigService>();
    loggerService = LoggerService();
  }
  
  @override
  void dispose() {
    nameController.dispose();
    accountController.dispose();
    passwordController.dispose();
    confirmPasswordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Color(0xFF4361EE),
                  Color(0xFF3A56D4),
                ],
              ),
            ),
            child: Center(
              child: SingleChildScrollView(
                child: Container(
                  width: MediaQuery.of(context).size.width * 0.9,
                  constraints: const BoxConstraints(maxWidth: 500),
                  padding: const EdgeInsets.all(30),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(20),
                    boxShadow: [
                      BoxShadow(
                        color: ColorUtils.withValues(Colors.black, 0.1),
                        blurRadius: 20,
                        spreadRadius: 5,
                      )
                    ],
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // APP图标
                      Image.asset('assets/icons/foreground.png', width: 80, height: 80),
                      const SizedBox(height: 20),
                      
                      // 标题
                      const Text(
                        '创建账号',
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF333333),
                        ),
                      ),
                      const SizedBox(height: 10),
                      const Text(
                        '请填写注册信息',
                        style: TextStyle(
                          fontSize: 16,
                          color: Colors.grey,
                        ),
                      ),
                      const SizedBox(height: 30),
                      
                      // 用户名输入框
                      TextField(
                        controller: nameController,
                        decoration: InputDecoration(
                          labelText: '昵称',
                          prefixIcon: const Icon(Icons.person, color: Color(0xFF4361EE)),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide.none,
                          ),
                          filled: true,
                          fillColor: Colors.grey[100],
                          errorText: _nameError ? '昵称不能为空' : null,
                          contentPadding: const EdgeInsets.symmetric(vertical: 16, horizontal: 20),
                        ),
                      ),
                      const SizedBox(height: 20),
                      
                      // 密码输入框
                      TextField(
                        controller: passwordController,
                        obscureText: _obscurePassword,
                        decoration: InputDecoration(
                          labelText: '密码',
                          prefixIcon: const Icon(Icons.lock, color: Color(0xFF4361EE)),
                          suffixIcon: IconButton(
                            icon: Icon(
                              _obscurePassword ? Icons.visibility_off : Icons.visibility,
                              color: Colors.grey,
                            ),
                            onPressed: () {
                              setState(() {
                                _obscurePassword = !_obscurePassword;
                              });
                            },
                          ),
                          errorText: _passwordError ? '密码不能为空' : null,
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide.none,
                          ),
                          filled: true,
                          fillColor: Colors.grey[100],
                          contentPadding: const EdgeInsets.symmetric(vertical: 16, horizontal: 20),
                        ),
                      ),
                      const SizedBox(height: 20),
                      
                      // 确认密码输入框
                      TextField(
                        controller: confirmPasswordController,
                        obscureText: _obscureConfirmPassword,
                        onChanged: (_) => _checkPasswords(),
                        decoration: InputDecoration(
                          labelText: '确认密码',
                          prefixIcon: const Icon(Icons.lock_outline, color: Color(0xFF4361EE)),
                          suffixIcon: IconButton(
                            icon: Icon(
                              _obscureConfirmPassword ? Icons.visibility_off : Icons.visibility,
                              color: Colors.grey,
                            ),
                            onPressed: () {
                              setState(() {
                                _obscureConfirmPassword = !_obscureConfirmPassword;
                              });
                            },
                          ),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide.none,
                          ),
                          filled: true,
                          fillColor: Colors.grey[100],
                          errorText: _confirmPasswordError ? '确认密码不能为空' : 
                                    (_passwordsMatch ? null : '两次输入的密码不一致'),
                          contentPadding: const EdgeInsets.symmetric(vertical: 16, horizontal: 20),
                        ),
                      ),
                      const SizedBox(height: 30),
                      
                      // 注册按钮
                      SizedBox(
                        width: double.infinity,
                        height: 50,
                        child: ElevatedButton(
                          onPressed: _isLoading ? null : _handleRegister,
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF4361EE),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                            elevation: 5,
                            shadowColor: ColorUtils.withValues(const Color(0xFF4361EE), 0.3),
                          ),
                          child: _isLoading
                              ? const CircularProgressIndicator(color: Colors.white)
                              : const Text(
                                  '注册',
                                  style: TextStyle(
                                    fontSize: 18,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.white,
                                  ),
                                ),
                        ),
                      ),
                      const SizedBox(height: 20),
                      
                      // 已有账号
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Text('已有账号?', style: TextStyle(color: Colors.grey)),
                          TextButton(
                            onPressed: () => Navigator.of(context).pop(),
                            child: const Text(
                              '立即登录',
                              style: TextStyle(
                                color: Color(0xFF4361EE),
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          // 返回按钮
          Positioned(
            left: 16,
            top: MediaQuery.of(context).padding.top + 16,
            child: IconButton(
              icon: const Icon(Icons.arrow_back, color: Colors.white),
              onPressed: () => Navigator.of(context).pop(),
            ),
          ),
        ],
      ),
    );
  }

  void _checkPasswords() {
    setState(() {
      _passwordsMatch = passwordController.text == confirmPasswordController.text;
    });
  }

  /// 生成 16 字节 / 128 bit 安全随机 UID，hex 编码为 32 字符
  Future<String> _generateUID() async {
    final random = Random.secure();
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));
    final uid = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    loggerService.debug('生成新UID: ${uid.substring(0, 8)}...');
    return uid;
  }

  void _handleRegister() async {
    if (nameController.text.trim().isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('请输入昵称')),
        );
      }
      return;
    }

    if (passwordController.text.trim().isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('请输入密码')),
        );
      }
      return;
    }

    if (passwordController.text.length < 8) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('密码长度不能少于8位')),
        );
      }
      return;
    }

    if (passwordController.text != confirmPasswordController.text) {
      setState(() => _passwordsMatch = false);
      return;
    }
    
    setState(() => _isLoading = true);
    
    try {
      // 1. 生成本地 UID（优先使用服务器返回的）
      final localUid = await _generateUID();
      loggerService.debug('本地生成UID: ${localUid.substring(0, 8)}...');

      // 2. 本地存储（必须先写，loginPage 登录时依赖 Hive 中的注册记录）
      final storageService = getIt<StorageService>();
      await storageService.init(configService.appDataPath);
      final ciphertext = EncryptUtils.encryptUID(localUid, passwordController.text);
      storageService.registerUser(localUid, ciphertext);

      final userDir = Directory(path.join(configService.appDataPath, ciphertext));
      if (!await userDir.exists()) {
        await userDir.create(recursive: true);
      }
      await storageService.saveUserInfo(ciphertext, {
        'name': nameController.text,
        'uid': localUid,
        'password': passwordController.text,  // 用于后续 auto-sync
        'registerTime': DateTime.now().toIso8601String(),
        'lastLoginTime': null,
      });
      loggerService.debug('本地存储完成: ${userDir.path}');

      // 3. 优先尝试服务器注册（UID 由服务器分发）
      final chatRepo = getIt<ChatRepository>();
      final serverUser = await chatRepo.register(
        uid: localUid,
        password: passwordController.text,
        displayName: nameController.text,
      );

      // 取最终 UID（服务器可能分配了新 UID）
      final finalUid = serverUser?.userId ?? localUid;
      final bool isOfflineMode = serverUser == null;
      loggerService.info('注册完成: uid=$finalUid, offlineMode=$isOfflineMode');

      // 4. 更新 UI 状态
      ref.read(userProvider.notifier).loginUser(
        name: nameController.text,
        uid: finalUid,
        userDataPath: userDir.path,
      );
      storageService.setCurrentUser(localUid);
      await configService.updateKeepLoggedIn(true);

      if (!mounted) return;

      // 5. 注册成功弹窗
      await showDialog(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          title: Text(isOfflineMode ? '注册成功（离线模式）' : '注册成功'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(isOfflineMode
                  ? '服务器暂不可用，已在本地创建账号。网络恢复后将自动同步。'
                  : '您的账号已成功创建！'),
              const SizedBox(height: 16),
              Text(isOfflineMode ? '本地 UID（待服务器确认）：' : '您的 UID 为：'),
              const SizedBox(height: 8),
              SelectableText(
                finalUid,
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 14,
                  wordSpacing: -2,
                ),
              ),
              if (isOfflineMode) ...[
                const SizedBox(height: 8),
                const Text(
                  '网络恢复后会自动重新注册',
                  style: TextStyle(fontSize: 12, color: Colors.orange),
                ),
              ] else ...[
                const SizedBox(height: 8),
                const Text(
                  '请妥善保存您的 UID，用于后续登录',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
              ],
            ],
          ),
          actions: [
            TextButton(
              onPressed: () {
                Clipboard.setData(ClipboardData(text: finalUid));
                ScaffoldMessenger.of(ctx).showSnackBar(
                  const SnackBar(content: Text('UID已复制到剪贴板')),
                );
              },
              child: const Text('复制UID'),
            ),
            TextButton(
              onPressed: () {
                Navigator.of(ctx).pop();
                Navigator.of(ctx).pop();
              },
              child: const Text('确定'),
            ),
          ],
        ),
      );
    } catch (e) {
      loggerService.error('注册失败: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('注册失败: ${e.toString()}')),
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }
}