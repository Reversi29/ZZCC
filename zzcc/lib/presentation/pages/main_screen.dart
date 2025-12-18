// lib/presentation/pages/main_screen.dart
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:zzcc/data/models/theme_model.dart';
import 'package:zzcc/presentation/pages/home/home_page.dart';
import 'package:zzcc/presentation/pages/message/message_screen.dart';
import 'package:zzcc/presentation/pages/workbench/workbench_page.dart';
import 'package:zzcc/presentation/pages/shared/shared_page.dart';
import 'package:zzcc/presentation/pages/square/square_page.dart';
import 'package:zzcc/presentation/pages/settings/settings_page.dart';
import 'package:zzcc/presentation/pages/profile/profile_page.dart';
import 'package:zzcc/presentation/providers/theme_provider.dart';
import 'package:zzcc/presentation/providers/user_provider.dart';
import 'package:zzcc/presentation/widgets/resizable_panel.dart';
import 'package:zzcc/core/utils/color_utils.dart';
import 'package:zzcc/core/routes/route_names.dart';
import 'package:zzcc/presentation/providers/sidebar_provider.dart';

class MainScreen extends ConsumerWidget {
  final List<CustomTheme> presetThemes;
  final Widget child;
  
  const MainScreen({
    super.key, 
    required this.presetThemes,
    required this.child,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = ref.watch(themeProvider);
    return _MainScreenContent(presetThemes: presetThemes, theme: theme);
  }
}

class _MainScreenContent extends ConsumerStatefulWidget {
  final List<CustomTheme> presetThemes;
  final CustomTheme theme;
  
  const _MainScreenContent({
    required this.presetThemes,
    required this.theme,
  });

  @override
  ConsumerState<_MainScreenContent> createState() => _MainScreenState();
}

class _MainScreenState extends ConsumerState<_MainScreenContent> {
  int _selectedIndex = 0;
  late final CustomTheme _currentTheme = widget.theme;
  double _previousWidth = 200.0;

  @override
  void initState() {
    super.initState();
    final currentWidth = ref.read(sidebarProvider);
    if (currentWidth > 0) {
      _previousWidth = currentWidth;
    }
  }

  void _syncRouteWithIndex() {
    if (!mounted) return;
    
    final location = GoRouterState.of(context).uri.toString();
    
    final routeIndexMap = {
      '${RouteNames.root}${RouteNames.home}': 0,
      '${RouteNames.root}${RouteNames.messages}': 1,
      '${RouteNames.root}${RouteNames.workbench}': 2,
      '${RouteNames.root}${RouteNames.shared}': 3,
      '${RouteNames.root}${RouteNames.square}': 4,
      '${RouteNames.root}${RouteNames.settings}': 5,
      '${RouteNames.root}${RouteNames.profile}': 6,
    };

    for (final entry in routeIndexMap.entries) {
      if (location.startsWith(entry.key)) {
        if (_selectedIndex != entry.value) {
          setState(() => _selectedIndex = entry.value);
        }
        break;
      }
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _syncRouteWithIndex();
    
    // 确保侧边栏宽度正确
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (ref.read(sidebarProvider) == 0) {
        ref.read(sidebarProvider.notifier).updateWidth(_previousWidth);
      }
    });
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
      
      final pickedFile = await pickAndCropImage('选择头像', 1.0);
      if (pickedFile != null && mounted) {
        final newAvatarPath = await ref.read(userProvider.notifier).saveNewAvatar(pickedFile);
        if (newAvatarPath != null) {
          debugPrint('头像保存成功: $newAvatarPath');
        }
      }
    } catch (e) {
      debugPrint('头像选择失败: $e');
    }
  }

   void _handleIndexChanged(int index) {
    setState(() => _selectedIndex = index);
    final routes = [
      RouteNames.home,
      RouteNames.messages,
      RouteNames.workbench,
      RouteNames.shared,
      RouteNames.square,
      RouteNames.settings,
      RouteNames.profile,
    ];
    if (index < routes.length) {
      context.go('${RouteNames.root}${routes[index]}');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Consumer(
        builder: (context, ref, _) {
          final panelWidth = ref.watch(sidebarProvider);
          final user = ref.watch(userProvider);
          final currentAvatarPath = ref.read(userProvider.notifier).getCurrentAvatarPath();
          final avatarFile = currentAvatarPath != null ? File(currentAvatarPath) : null;
          
          return Stack(
            children: [
              if (_currentTheme.rightBackgroundImage == null)
                Positioned.fill(
                  left: panelWidth,
                  child: Container(
                    color: ColorUtils.withValues(Theme.of(context).primaryColor, 0.1),
                  ),
                ),
              
              ResizablePanel(
                avatarFile: avatarFile,
                onAvatarTap: _pickAvatar,
                selectedIndex: _selectedIndex,
                onIndexChanged: _handleIndexChanged,
                content: _buildContent(),
                isLoggedIn: user.isLoggedIn,
                onLoginPressed: () => context.go('${RouteNames.root}${RouteNames.login}'),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildContent() {
    return Container(
      constraints: const BoxConstraints(minWidth: 200.0),
      child: IndexedStack(
        index: _selectedIndex,
        children: [
          const HomePage(),
          const MessageScreen(),
          const WorkbenchPage(),
          const SharedPage(),
          const SquarePage(),
          SettingsPage(presetThemes: widget.presetThemes),
          ProfilePage(onAvatarChanged: (file) {}),
        ],
      ),
    );
  }
}