import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/presentation/providers/user_provider.dart';
import 'package:zzcc/core/services/config_service.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/utils/color_utils.dart';
import 'package:zzcc/core/utils/encrypt_utils.dart';
import 'package:zzcc/data/repositories/chat_repository.dart';
import 'package:zzcc/presentation/pages/auth/widgets/register_page.dart';
import 'package:path/path.dart' as path;
import 'package:zzcc/core/routes/route_names.dart';
import 'package:go_router/go_router.dart';

class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({super.key});

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends ConsumerState<LoginPage> {
  late TextEditingController accountController;
  late TextEditingController passwordController;
  late ConfigService configService;
  bool _isLoading = false;
  bool _obscurePassword = true;
  List<Map<String, dynamic>> _accounts = [];
  
  @override
  void initState() {
    super.initState();
    accountController = TextEditingController();
    passwordController = TextEditingController();
    configService = getIt<ConfigService>();
    _loadAccounts();
  }

  Future<void> _loadAccounts() async {
    final storageService = getIt<StorageService>();
    try {
      await storageService.init(configService.appDataPath);
      final accounts = await storageService.listAllAccounts();
      if (mounted) setState(() => _accounts = accounts);
    } catch (_) {}
  }
  
  @override
  void dispose() {
    accountController.dispose();
    passwordController.dispose();
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
                        '欢迎回来',
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF333333),
                        ),
                      ),
                      const SizedBox(height: 10),
                      const Text(
                        '请登录您的账号',
                        style: TextStyle(
                          fontSize: 16,
                          color: Colors.grey,
                        ),
                      ),

                      const SizedBox(height: 20),

                      // 账号输入框
                      TextField(
                        controller: accountController,
                        decoration: InputDecoration(
                          labelText: 'uid/手机号/证件号',
                          prefixIcon: const Icon(Icons.login, color: Color(0xFF4361EE)),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide.none,
                          ),
                          filled: true,
                          fillColor: Colors.grey[100],
                          contentPadding: const EdgeInsets.symmetric(vertical: 16, horizontal: 20),
                          suffixIcon: _accounts.isEmpty
                              ? null
                              : PopupMenuButton<String>(
                                  icon: const Icon(Icons.arrow_drop_down, color: Colors.grey),
                                  tooltip: '选择本地账号',
                                  onSelected: (uid) {
                                    setState(() {
                                      accountController.text = uid;
                                      passwordController.clear();
                                    });
                                  },
                                  itemBuilder: (context) => _accounts.map((acc) {
                                    final uid = acc['uid'] as String;
                                    final name = acc['name'] as String? ?? uid;
                                    return PopupMenuItem<String>(
                                      value: uid,
                                      child: Row(
                                        children: [
                                          const Icon(Icons.person, size: 18, color: Color(0xFF4361EE)),
                                          const SizedBox(width: 10),
                                          Expanded(
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              mainAxisSize: MainAxisSize.min,
                                              children: [
                                                Text(name, style: const TextStyle(fontWeight: FontWeight.w500)),
                                                Text(uid, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
                                              ],
                                            ),
                                          ),
                                        ],
                                      ),
                                    );
                                  }).toList(),
                                ),
                        ),
                        onSubmitted: (_) {
                          FocusScope.of(context).nextFocus();
                        },
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
                      
                      // 记住我 & 忘记密码
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          TextButton(
                            onPressed: () {},
                            child: const Text('忘记密码?', style: TextStyle(color: Color(0xFF4361EE))),
                          ),
                        ],
                      ),
                      const SizedBox(height: 30),
                      
                      // 登录按钮
                      SizedBox(
                        width: double.infinity,
                        height: 50,
                        child: ElevatedButton(
                          onPressed: _isLoading ? null : () => _handleLogin(),
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
                                  '登录',
                                  style: TextStyle(
                                    fontSize: 18,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.white,
                                  ),
                                ),
                        ),
                      ),
                      const SizedBox(height: 20),
                      
                      // 注册新账号
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Text('还没有账号?', style: TextStyle(color: Colors.grey)),
                          TextButton(
                            onPressed: () => Navigator.push(
                              context,
                              MaterialPageRoute(builder: (context) => const RegisterPage()),
                            ),
                            child: const Text(
                              '注册新账号',
                              style: TextStyle(
                                color: Color(0xFF4361EE),
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      
                      // 其他登录方式
                      const Text('或使用以下方式登录', style: TextStyle(color: Colors.grey)),
                      const SizedBox(height: 20),
                      
                      // 社交登录按钮
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          IconButton(
                            icon: Image.asset('assets/icons/google.png', width: 40),
                            onPressed: () {},
                          ),
                          const SizedBox(width: 20),
                          IconButton(
                            icon: Image.asset('assets/icons/wechat.png', width: 40),
                            onPressed: () {},
                          ),
                          const SizedBox(width: 20),
                          IconButton(
                            icon: Image.asset('assets/icons/qq.png', width: 40),
                            onPressed: () {},
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          // 返回按钮放置在Stack的左上角
          Positioned(
            left: 16,
            top: MediaQuery.of(context).padding.top + 16,
            child: IconButton(
              icon: const Icon(Icons.arrow_back, color: Colors.white),
              onPressed: () {
                final router = GoRouter.of(context);
                
                // 获取当前路由栈长度
                final stackLength = router.routerDelegate.currentConfiguration.matches.length;
                final currentLocation = router.routeInformationProvider.value.uri.toString();
                // 调试信息
                debugPrint('路由栈长度: $stackLength');
                debugPrint('当前路由: $currentLocation');
                String routeHome = '${RouteNames.root}${RouteNames.home}';
                // 安全处理：如果是最后一个页面，直接跳首页
                if (stackLength <= 1) {
                  router.go(routeHome);
                  return;
                }
                
                // 尝试通过路由索引判断（最兼容的方式）
                bool isPreviousProfile = false;
                try {
                  // 假设从个人资料页跳转到登录页时，栈长度会增加1
                  // 直接通过位置判断，不依赖具体属性
                  isPreviousProfile = true;
                  
                  // 额外验证：检查当前路由是否是从个人资料页跳转过来的
                  // 可以通过登录页的路由参数传递来源信息
                  final fromProfile = router.routeInformationProvider.value.uri.queryParameters['from'] == 'profile';
                  if (fromProfile) {
                    isPreviousProfile = true;
                  }
                } catch (e) {
                  debugPrint('判断前序路由失败: $e');
                  isPreviousProfile = false;
                }
                
                // 执行导航逻辑
                if (isPreviousProfile) {
                  router.go(routeHome);
                } else {
                  if (stackLength > 1) {
                    router.pop();
                  } else {
                    router.go(routeHome);
                  }
                }
              },
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _handleLogin() async {
    final uid = accountController.text.trim();
    final password = passwordController.text.trim();

    if (uid.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('请输入UID')),
        );
      }
      return;
    }

    if (password.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('请输入密码')),
        );
      }
      return;
    }

    setState(() => _isLoading = true);
    
    try {
      // 1. 本地 Hive 验证（必须先验证本地账号存在）
      final storageService = getIt<StorageService>();
      await storageService.init(configService.appDataPath);

      final storedCiphertext = storageService.getUserRegistry(uid);
      if (storedCiphertext == null) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('该用户不存在')),
          );
        }
        return;
      }

      final decryptedUid = EncryptUtils.decryptUID(storedCiphertext, password);
      if (decryptedUid != uid) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('密码错误')),
          );
        }
        return;
      }

      // 2. 读本地用户信息（用于 displayName 和 userDataPath）
      final userInfo = await storageService.getUserInfo(storedCiphertext);
      final displayName = userInfo?['name'] as String?;

      // 3. 优先尝试服务器登录（403 时自动 sync-account）
      final chatRepo = getIt<ChatRepository>();
      await chatRepo.login(
        username: uid,
        password: password,
        displayName: displayName,
      );

      // 4. 登录成功，更新 UI 状态并存储密码（下次 auto-login 可用于 sync）
      final userDataPath = path.join(configService.appDataPath, storedCiphertext);
      final savedUserInfo = await storageService.getUserInfo(storedCiphertext) ?? {};
      savedUserInfo['password'] = password;
      await storageService.saveUserInfo(storedCiphertext, savedUserInfo);
      ref.read(userProvider.notifier).loginUser(
        name: userInfo?['name'] ?? '用户名称',
        uid: uid,
        userDataPath: userDataPath,
      );
      storageService.setCurrentUser(uid);
      await configService.updateKeepLoggedIn(true);

      if (mounted) {
        context.go('${RouteNames.root}${RouteNames.home}');
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('登录成功')),
        );
      }
    } catch (e) {
      // 服务器返回了业务错误（账号不存在/密码错误），但本地账号存在时允许离线登录
      if (e.toString().contains('401') || e.toString().contains('incorrect') || e.toString().contains('invalid')) {
        // 尝试离线登录：直接用本地账号登录，跳过服务器
        try {
          final storageService = getIt<StorageService>();
          final storedCiphertext = storageService.getUserRegistry(uid);
          if (storedCiphertext != null) {
            final userInfo = await storageService.getUserInfo(storedCiphertext);
            final userDataPath = path.join(configService.appDataPath, storedCiphertext);
            ref.read(userProvider.notifier).loginUser(
              name: userInfo?['name'] ?? '用户名称',
              uid: uid,
              userDataPath: userDataPath,
            );
            storageService.setCurrentUser(uid);
            await configService.updateKeepLoggedIn(true);
            if (mounted) {
              context.go('${RouteNames.root}${RouteNames.home}');
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('登录成功（离线模式）')),
              );
              return;
            }
          }
        } catch (_) {}
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('登录失败: ${e.toString()}')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }
}