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
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:ntp/ntp.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:path/path.dart' as path;
// import 'package:crypto/crypto.dart';
// import 'dart:typed_data';

// const String _customBaseChars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789·~!@#%^&()_+-=[]{};,.';
const String _customBaseChars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
const int _customBase = _customBaseChars.length;

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

  Future<String> _getDeviceIdentifier() async {
    final DeviceInfoPlugin deviceInfo = DeviceInfoPlugin();
    
    try {
      if (Platform.isAndroid) {
        final androidInfo = await deviceInfo.androidInfo;
        return androidInfo.id; // Android ID
      } else if (Platform.isIOS) {
        final iosInfo = await deviceInfo.iosInfo;
        return iosInfo.identifierForVendor ?? 'ios_unknown';
      } else if (Platform.isWindows) {
        final windowsInfo = await deviceInfo.windowsInfo;
        return windowsInfo.deviceId; // Windows 设备ID
      } else if (Platform.isMacOS) {
        final macInfo = await deviceInfo.macOsInfo;
        return macInfo.computerName; // macOS 计算机名
      } else if (Platform.isLinux) {
        final linuxInfo = await deviceInfo.linuxInfo;
        return linuxInfo.name; // Linux 主机名（正确字段名）
      }
    } catch (e) {
      loggerService.error('获取设备信息失败', e.toString());
    }
    
    // 其他未知平台使用混合标识符
    return '${Platform.operatingSystem}_${DateTime.now().millisecondsSinceEpoch}_${Random().nextInt(1<<16)}';
  }

  Future<Map<String, dynamic>> _generateUID() async {
    DateTime trustedTime;
    
    try {
      // 使用SNTP
      trustedTime = await _getSNTPTime();
      loggerService.debug('使用SNTP时间: $trustedTime');
    } catch (apiError) {
      try {
        // 尝试多个免费授时API
        trustedTime = await _getTimeFromAPIs();
        loggerService.debug('使用授时API时间: $trustedTime');
      } catch (sntpError) {
        loggerService.error('所有时间源均失败');
        throw Exception('无法获取可信时间源');
      }
    }
    
    final deviceId = await _getDeviceIdentifier();
    final random = Random().nextInt(1 << 8);
    final input = '$trustedTime$deviceId$random'.replaceAll(RegExp(r'[^a-fA-F0-9]'), '');
    loggerService.debug(input);
    final inputBytes = _hexStringToBytes(input);
    
    // 返回base64编码的压缩数据
    return {
      'uid': _customBaseEncode(inputBytes),
      'trustedTime': trustedTime
    };
  }

  List<int> _hexStringToBytes(String hexString) {
    if (hexString.isEmpty) return [];
    
    // 确保长度为偶数
    if (hexString.length % 2 != 0) {
      hexString = '0$hexString';
    }
    
    final bytes = <int>[];
    for (int i = 0; i < hexString.length; i += 2) {
      final hex = hexString.substring(i, i + 2);
      bytes.add(int.parse(hex, radix: 16));
    }
    return bytes;
  }

  String _customBaseEncode(List<int> bytes) {
    if (bytes.isEmpty) return '';

    // 将字节数组转换为大整数
    BigInt big = BigInt.zero;
    for (var byte in bytes) {
      big = (big << 8) | BigInt.from(byte);
    }

    // 处理特殊情况：输入为0
    if (big == BigInt.zero) {
      return _customBaseChars[0];
    }

    // 使用BigInt进行base83转换
    final base = BigInt.from(_customBase);
    final buffer = StringBuffer();
    
    while (big > BigInt.zero) {
      final result = big ~/ base;
      final remainder = big.remainder(base);
      buffer.write(_customBaseChars[remainder.toInt()]);
      big = result;
    }
    
    // 反转字符串得到正确顺序
    return buffer.toString().split('').reversed.join();
  }

  Future<DateTime> _getSNTPTime() async {
    final sntpServers = [
      'time.cloudflare.com',
      'time.google.com',
      'time.windows.com',
      'time.apple.com',
      'pool.ntp.org',
    ];
    
    for (final server in sntpServers) {
      try {
        final sntpResponse = await NTP.now(
          lookUpAddress: server,
          timeout: const Duration(seconds: 2),
        );
        return sntpResponse;
      } catch (e) {
        loggerService.debug('SNTP服务器($server)失败: ${e.toString()}');
      }
    }
    
    throw Exception('所有SNTP服务器请求失败');
  }

  Future<DateTime> _getTimeFromAPIs() async {
    final apis = [
      {
        'url': 'http://worldtimeapi.org/api/ip',
        'parser': (data) => DateTime.parse(data['utc_datetime'] as String)
      },
      {
        'url': 'https://time.akamai.com/',
        'parser': (response) => DateTime.parse((response as HttpClientResponse).headers.value('date')!)
      },
      {
        'url': 'https://time.cloudflare.com/',
        'parser': (response) => DateTime.parse((response as HttpClientResponse).headers.value('date')!)
      },
      {
        'url': 'http://api.timezonedb.com/v2/get-time-zone?key=YOUR_KEY&format=json&by=zone&zone=UTC',
        'parser': (data) => DateTime.parse(data['formatted'] as String)
      },
      {
        'url': 'https://www.timeapi.io/api/Time/current/zone?timeZone=UTC',
        'parser': (data) => DateTime.parse(data['dateTime'] as String)
      },
      {
        'url': 'https://timeapi.io/api/Time/current/ip',
        'parser': (data) => DateTime.parse(data['dateTime'] as String)
      },
      {
        'url': 'http://worldclockapi.com/api/json/utc/now',
        'parser': (data) => DateTime.parse(data['currentDateTime'] as String)
      }
    ];
    
    apis.shuffle();
    
    for (final api in apis) {
      final url = api['url'] as String;
      final parser = api['parser'] as Function;
      
      try {
        final response = await HttpClient().getUrl(Uri.parse(url))
          .timeout(const Duration(seconds: 1))
          .then((request) => request.close());
        
        if (response.statusCode != 200) continue;
        
        final String contentType = response.headers.value('content-type') ?? '';
        
        if (contentType.contains('application/json')) {
          final json = await response.transform(utf8.decoder).join();
          final data = jsonDecode(json) as Map<String, dynamic>;
          return parser(data);
        } 
        else {
          return parser(response);
        }
      } catch (e) {
        loggerService.debug('授时API失败($url): ${e.toString()}');
      }
    }
    
    throw Exception('所有授时API请求失败');
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

    if (passwordController.text.length < 6) { // 可选：添加密码长度验证
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('密码长度不能少于6位')),
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
      loggerService.info('用户注册流程开始');
      
      // 生成并加密UID
      final uidResult = await _generateUID();
      final uid = uidResult['uid'] as String;
      final trustedTime = uidResult['trustedTime'] as DateTime;
      loggerService.debug(uid);
      loggerService.debug('生成用户UID: ${uid.substring(0, 12)}...');
      
      final ciphertext = EncryptUtils.encryptUID(uid, passwordController.text);
      loggerService.debug('UID加密完成: ${ciphertext.substring(0, 16)}...');
      
      // 获取存储服务
      final storageService = getIt<StorageService>();
      await storageService.init(configService.appDataPath);
      
      // 存储到user_registry
      storageService.registerUser(uid, ciphertext);
      loggerService.info('用户注册信息已存储');
      
      // 创建用户文件夹
      final userDir = Directory(path.join(configService.appDataPath, ciphertext));
      if (!await userDir.exists()) {
        await userDir.create(recursive: true);
        loggerService.debug('用户目录创建成功: ${userDir.path}');
      }

      // 保存用户信息到对应目录的Hive存储
      await storageService.saveUserInfo(
        ciphertext,
        {
          'name': nameController.text,
          'uid': uid,
          'registerTime': trustedTime.toIso8601String(),
          'lastLoginTime': null
        },
      );
      loggerService.debug('用户信息已存储到: ${path.join(configService.appDataPath, ciphertext)}');
      
      // 调用用户提供者注册方法
      ref.read(userProvider.notifier).loginUser(
        name: nameController.text,
        uid: uid,
        userDataPath: userDir.path, // 传入用户目录路径
      );
      loggerService.info('用户提供者注册调用完成');
      
      if (mounted) {
        // 注册成功后显示UID提示弹窗
        showDialog(
          context: context,
          barrierDismissible: false,
          builder: (context) => AlertDialog(
            title: const Text('注册成功'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('您的账号已成功创建！'),
                const SizedBox(height: 16),
                const Text('系统分配的UID为：'),
                const SizedBox(height: 8),
                // 显示UID，添加复制功能
                SelectableText(
                  uid,
                  style: const TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 14,
                    wordSpacing: -2,
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  '请妥善保存您的UID，用于后续登录',
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.grey,
                  ),
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () {
                  // 复制UID到剪贴板
                  Clipboard.setData(ClipboardData(text: uid));
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('UID已复制到剪贴板')),
                  );
                },
                child: const Text('复制UID'),
              ),
              TextButton(
                onPressed: () {
                  Navigator.of(context).pop(); // 关闭弹窗
                  Navigator.of(context).pop(); // 返回登录页
                },
                child: const Text('确定'),
              ),
            ],
          ),
        );
        
        loggerService.info('注册成功，显示UID提示');
      }
    } on Exception catch (e) {
      loggerService.error('注册失败: ${e.toString()}');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('无法获取可信时间源，请检查网络')),
        );
      }
    } catch (e) {
      loggerService.error('用户注册失败', e.toString());
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