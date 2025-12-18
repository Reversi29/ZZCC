import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/presentation/providers/user_provider.dart';
import 'package:zzcc/core/services/config_service.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/utils/color_utils.dart';
import 'package:zzcc/core/utils/encrypt_utils.dart';
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
  
  @override
  void initState() {
    super.initState();
    accountController = TextEditingController();
    passwordController = TextEditingController();
    configService = getIt<ConfigService>();
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
                      const SizedBox(height: 30),
                      
                      // 邮箱输入框
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
    // 1. 表单验证
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
      // 2. 获取存储服务中的用户注册信息
      final storageService = getIt<StorageService>();
      await storageService.init(configService.appDataPath); // 确保初始化完成

      // 3. 检查用户是否存在（从user_registry中获取存储的密文）
      final storedCiphertext = storageService.getUserRegistry(uid);
      if (storedCiphertext == null) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('该用户不存在')),
          );
        }
        return;
      }

      // 4. 解密存储的密文，验证与输入的UID是否一致
      final decryptedUid = EncryptUtils.decryptUID(storedCiphertext, password);
      if (decryptedUid != uid) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('密码错误')),
          );
        }
        return;
      }

      // 5. 登录成功：更新用户状态、获取用户信息
      final userInfo = await storageService.getUserInfo(storedCiphertext);
      
      // 获取用户数据路径（根据实际存储位置调整）
      final userDataPath = path.join(configService.appDataPath, storedCiphertext);
      
      ref.read(userProvider.notifier).loginUser(
        name: userInfo?['name'] ?? '用户名称',
        uid: uid,
        userDataPath: userDataPath,
      );

      storageService.setCurrentUser(uid);
      await configService.updateKeepLoggedIn(true);

      if (mounted) {
        // 替换导航方式
        context.go('${RouteNames.root}${RouteNames.home}'); // 使用GoRouter导航到首页
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('登录成功')),
        );
      }
    } catch (e) {
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