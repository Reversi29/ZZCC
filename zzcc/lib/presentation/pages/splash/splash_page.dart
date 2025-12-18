import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/presentation/providers/app_loaded_provider.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/core/di/service_locator.dart';

class SplashPage extends ConsumerStatefulWidget {
  const SplashPage({super.key});

  @override
  ConsumerState<SplashPage> createState() => _SplashPageState();
}

class _SplashPageState extends ConsumerState<SplashPage> with SingleTickerProviderStateMixin {
  bool _appInitialized = false;
  bool _gifFinished = false;
  Timer? _gifTimer;
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    
    // 先初始化基础动画控制器和动画，避免未初始化错误
    _fadeController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 500),
    );
    
    _fadeAnimation = Tween<double>(begin: 1.0, end: 0.0).animate(
      CurvedAnimation(
        parent: _fadeController,
        curve: Curves.easeOut,
      ),
    );

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _initAnimationSettings();
    });
  }

  // 新增异步初始化方法
  Future<void> _initAnimationSettings() async {
    // 直接从StorageService获取状态（最可靠的方式）
    final enableAnimation = await getIt<StorageService>().getSplashAnimationStatus();

    if (!enableAnimation) {
      // 不启用动画时，立即完成动画
      _fadeController.value = 1.0;
    }

    // 根据是否启用动画调整初始化时间
    int delay = enableAnimation ? 3000 : 1000;
    
    Future.delayed(Duration(milliseconds: delay), () {
      if (mounted) {
        setState(() {
          _appInitialized = true;
        });
        _checkTransition();
      }
    });
    
    if (enableAnimation) {
      // 设置GIF动画播放时间
      _gifTimer = Timer(const Duration(seconds: 4), () {
        if (mounted) {
          setState(() {
            _gifFinished = true;
          });
          _checkTransition();
        }
      });
      
      // 淡出动画
      Timer(const Duration(milliseconds: 3500), () {
        if (mounted) {
          _fadeController.forward();
        }
      });
    } else {
      // 不启用动画时直接完成
      _gifFinished = true;
    }
  }

  @override
  void dispose() {
    _gifTimer?.cancel();
    _fadeController.dispose();
    super.dispose();
  }

  void _checkTransition() {
    if (_appInitialized && _gifFinished) {
      ref.read(appLoadedProvider.notifier).state = true;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Scaffold(
        backgroundColor: Colors.black,
        body: FadeTransition(
          opacity: _fadeAnimation,
          child: Image.asset(
            'assets/animations/splash.gif',
            fit: BoxFit.cover,
            width: double.infinity,
            height: double.infinity,
          ),
        ),
      ),
    );
  }
}