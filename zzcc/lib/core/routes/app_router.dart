// 文档3: lib/core/routes/app_router.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:zzcc/presentation/pages/main_screen.dart';
import 'package:zzcc/presentation/pages/auth/login_page.dart';
import 'package:zzcc/core/routes/route_names.dart';
import 'package:zzcc/presentation/providers/sidebar_provider.dart';

final appRouter = GoRouter(
  initialLocation: '${RouteNames.root}${RouteNames.home}',
  routes: [
    GoRoute(
      path: '${RouteNames.root}${RouteNames.login}',
      name: RouteNames.login,
      pageBuilder: (context, state) => MaterialPage(
        key: state.pageKey,
        child: const LoginPage(),
      ),
    ),
    ShellRoute(
      builder: (context, state, child) {
        return ProviderScope(
          overrides: [
            sidebarProvider.overrideWith((ref) => SidebarNotifier())
          ],
          child: MainScreen(
            presetThemes: const [],
            child: child,
          ),
        );
      },
      routes: [
        GoRoute(
          path: '${RouteNames.root}${RouteNames.home}',
          name: RouteNames.home,
          pageBuilder: (context, state) => const NoTransitionPage(
            child: SizedBox.shrink(),
          ),
        ),
        GoRoute(
          path: '${RouteNames.root}${RouteNames.messages}',
          name: RouteNames.messages,
          pageBuilder: (context, state) => const NoTransitionPage(
            child: SizedBox.shrink(),
          ),
        ),
        GoRoute(
          path: '${RouteNames.root}${RouteNames.workbench}',
          name: RouteNames.workbench,
          pageBuilder: (context, state) => const NoTransitionPage(
            child: SizedBox.shrink(),
          ),
        ),
        GoRoute(
          path: '${RouteNames.root}${RouteNames.shared}',
          name: RouteNames.shared,
          pageBuilder: (context, state) => const NoTransitionPage(
            child: SizedBox.shrink(),
          ),
        ),
        GoRoute(
          path: '${RouteNames.root}${RouteNames.square}',
          name: RouteNames.square,
          pageBuilder: (context, state) => const NoTransitionPage(
            child: SizedBox.shrink(),
          ),
        ),
        GoRoute(
          path: '${RouteNames.root}${RouteNames.settings}',
          name: RouteNames.settings,
          pageBuilder: (context, state) => const NoTransitionPage(
            child: SizedBox.shrink(),
          ),
        ),
        GoRoute(
          path: '${RouteNames.root}${RouteNames.profile}',
          name: RouteNames.profile,
          pageBuilder: (context, state) => const NoTransitionPage(
            child: SizedBox.shrink(),
          ),
        ),
      ],
    ),
  ],
  errorPageBuilder: (context, state) => MaterialPage(
    key: state.pageKey,
    child: Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text('404 - 页面不存在', style: TextStyle(fontSize: 24)),
            ElevatedButton(
              onPressed: () => context.go('${RouteNames.root}${RouteNames.home}'),
              child: const Text('返回首页'),
            ),
          ],
        ),
      ),
    ),
  ),
);

class NoTransitionPage extends Page {
  final Widget child;
  
  const NoTransitionPage({
    super.key,
    required this.child,
  });
  
  @override
  Route createRoute(BuildContext context) {
    return PageRouteBuilder(
      settings: this,
      pageBuilder: (context, animation, secondaryAnimation) => child,
      transitionDuration: Duration.zero,
      reverseTransitionDuration: Duration.zero,
    );
  }
}