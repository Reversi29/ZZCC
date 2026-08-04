// lib/presentation/widgets/resizable_panel.dart
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/presentation/providers/user_provider.dart';
import 'package:zzcc/core/utils/color_utils.dart';
import 'package:zzcc/presentation/providers/sidebar_provider.dart';
import 'package:zzcc/presentation/providers/theme_provider.dart';
import 'package:zzcc/l10n/generated/app_localizations.dart';

class ResizablePanel extends ConsumerStatefulWidget {
  static const double collapseThreshold = 150.0;
  static const double minWidth = 70.0;
  static const double maxWidth = 400.0;

  final File? avatarFile;
  final VoidCallback onAvatarTap;
  final int selectedIndex;
  final ValueChanged<int> onIndexChanged;
  final Widget content;
  final bool isLoggedIn;
  final bool isOnline;
  final VoidCallback onLoginPressed;

  const ResizablePanel({
    super.key,
    required this.avatarFile,
    required this.onAvatarTap,
    required this.selectedIndex,
    required this.onIndexChanged,
    required this.content,
    required this.isLoggedIn,
    this.isOnline = true,
    required this.onLoginPressed,
  });

  @override
  ConsumerState<ResizablePanel> createState() => ResizablePanelState();
}

class ResizablePanelState extends ConsumerState<ResizablePanel> {
  bool _isLocked = false;
  bool _showControls = false;
  static const Color buttonHoverColor = Color(0xFF3A56D4);

  double get _panelWidth => ref.watch(sidebarProvider);

  void _handleDragUpdate(DragUpdateDetails details) {
    if (_isLocked) return;

    // 允许自由拖动到最小宽度
    final newWidth = (_panelWidth + details.delta.dx)
        .clamp(ResizablePanel.minWidth, ResizablePanel.maxWidth);

    ref.read(sidebarProvider.notifier).updateWidth(newWidth);
  }

  void _handleDragEnd(DragEndDetails details) {
    if (_isLocked) return;

    // 拖动结束时，如果宽度在最小宽度和阈值之间，设置为最小宽度
    if (_panelWidth < ResizablePanel.collapseThreshold &&
        _panelWidth > ResizablePanel.minWidth) {
      ref.read(sidebarProvider.notifier).updateWidth(ResizablePanel.minWidth);
    }
  }

  void togglePanel() {
    final notifier = ref.read(sidebarProvider.notifier);
    if (_panelWidth > 0) {
      // 折叠时保存当前宽度并完全隐藏
      notifier.toggle();
    } else {
      // 展开时恢复之前保存的宽度
      notifier.toggle();
    }
  }

  Widget _buildUserAvatar() {
    final isExpanded = _panelWidth >= ResizablePanel.collapseThreshold;

    return Consumer(
      builder: (context, ref, _) {
        final user = ref.watch(userProvider);
        final currentAvatarPath =
            ref.read(userProvider.notifier).getCurrentAvatarPath();
        final avatarFile =
            currentAvatarPath != null ? File(currentAvatarPath) : null;

        return Container(
          padding: const EdgeInsets.symmetric(vertical: 20),
          child: Column(
            children: [
              GestureDetector(
                onTap: widget.isLoggedIn
                    ? () => widget.onIndexChanged(0)
                    : widget.onLoginPressed,
                child: MouseRegion(
                  cursor: SystemMouseCursors.click,
                  child: Stack(
                    clipBehavior: Clip.none,
                    children: [
                      CircleAvatar(
                        radius: isExpanded ? 36 : 24,
                        backgroundColor: widget.isLoggedIn
                            ? _sidebarBg
                            : ColorUtils.withValues(_primaryColor, 0.15),
                        backgroundImage: widget.isLoggedIn && avatarFile != null
                            ? FileImage(avatarFile)
                            : null,
                        child: widget.isLoggedIn
                            ? (avatarFile == null
                                ? Icon(Icons.person,
                                    size: isExpanded ? 30 : 20,
                                    color: Colors.grey[600])
                                : null)
                            : isExpanded
                                ? Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 12, vertical: 10),
                                    child: const Text('未登录',
                                        style: TextStyle(
                                            fontSize: 14,
                                            fontWeight: FontWeight.bold,
                                            color: Colors.white,
                                            letterSpacing: 0.5)),
                                  )
                                : Container(
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      gradient: LinearGradient(
                                        colors: [_primaryColor, buttonHoverColor],
                                        begin: Alignment.topLeft,
                                        end: Alignment.bottomRight,
                                      ),
                                      boxShadow: [
                                        BoxShadow(
                                          color: ColorUtils.withValues(
                                              _primaryColor, 0.3),
                                          blurRadius: 4,
                                          offset: const Offset(0, 2),
                                        )
                                      ],
                                    ),
                                    child: const Icon(
                                      Icons.person_add_alt_1,
                                      size: 20,
                                      color: Colors.white,
                                    ),
                                  ),
                      ),
                      // 在线/离线状态指示器
                      if (widget.isLoggedIn)
                        Positioned(
                          right: isExpanded ? 0 : -2,
                          bottom: isExpanded ? 0 : -2,
                          child: Container(
                            width: isExpanded ? 16 : 12,
                            height: isExpanded ? 16 : 12,
                            decoration: BoxDecoration(
                              color: widget.isOnline ? Colors.green : Colors.grey,
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: Colors.white,
                                width: 2,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              if (isExpanded && widget.isLoggedIn) ...[
                const SizedBox(height: 12),
                Text(
                  user.name,
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                    color: Colors.grey[800],
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  Widget _buildMenuButton(int index, IconData icon, String text) {
    final bool isExpanded = _panelWidth >= ResizablePanel.collapseThreshold;
    final bool isSelected = widget.selectedIndex == index;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: isSelected ? ColorUtils.withValues(_primaryColor, 0.2) : null,
        borderRadius: BorderRadius.circular(8),
      ),
      child: SizedBox(
        height: 48,
        child: Tooltip(
          message: text,
          child: MouseRegion(
            cursor: SystemMouseCursors.click,
            child: InkWell(
              borderRadius: BorderRadius.circular(8),
              onTap: () => widget.onIndexChanged(index),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                constraints: BoxConstraints(
                  minWidth: isExpanded ? 0 : 48,
                  maxWidth: isExpanded ? _panelWidth : 48,
                ),
                child: isExpanded
                    ? Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            icon,
                            size: 20,
                            color: isSelected ? _primaryColor : _contrastColor(_sidebarBg),
                          ),
                          const SizedBox(width: 8),
                          Flexible(
                            child: Text(
                              text,
                              style: TextStyle(
                                fontSize: 14,
                                color:
                                    isSelected ? _primaryColor : _contrastColor(_sidebarBg),
                                fontWeight: isSelected
                                    ? FontWeight.bold
                                    : FontWeight.normal,
                              ),
                              overflow: TextOverflow.ellipsis,
                              maxLines: 1,
                            ),
                          ),
                        ],
                      )
                    : Center(
                        child: Icon(
                          icon,
                          size: 20,
                          color: isSelected ? _primaryColor : _contrastColor(_sidebarBg),
                        ),
                      ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTestButton(AppLocalizations appLocalizations) {
    final bool isExpanded = _panelWidth >= ResizablePanel.collapseThreshold;
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: ColorUtils.withValues(_primaryColor, 0.08),
        borderRadius: BorderRadius.circular(8),
      ),
      child: SizedBox(
        height: 48,
        child: Tooltip(
          message: appLocalizations.testMenuItem,
          child: MouseRegion(
            cursor: SystemMouseCursors.click,
            child: InkWell(
              borderRadius: BorderRadius.circular(8),
              onTap: () {
                widget.onIndexChanged(7);
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                constraints: BoxConstraints(
                  minWidth: isExpanded ? 0 : 48,
                  maxWidth: isExpanded ? _panelWidth : 48,
                ),
                child: isExpanded
                    ? Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.bug_report,
                              size: 20, color: _primaryColor),
                          const SizedBox(width: 8),
                          Flexible(
                            child: Text(
                              appLocalizations.testMenuItem,
                              style: TextStyle(
                                fontSize: 14,
                                color: _primaryColor,
                                fontWeight: FontWeight.bold,
                              ),
                              overflow: TextOverflow.ellipsis,
                              maxLines: 1,
                            ),
                          ),
                        ],
                      )
                    : Center(
                        child: Icon(
                          Icons.bug_report,
                          size: 20,
                          color: _primaryColor,
                        ),
                      ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildControlButton({
    required IconData icon,
    required VoidCallback onPressed,
    double width = 24,
  }) {
    return SizedBox(
      width: width,
      height: 30,
      child: IconButton(
        icon: Icon(icon, size: 16),
        color: _primaryColor,
        padding: EdgeInsets.zero,
        alignment: Alignment.center,
        onPressed: onPressed,
      ),
    );
  }

  Color get _primaryColor => ref.watch(themeProvider).primaryColor;

  Color get _sidebarBg =>
      ref.watch(themeProvider).leftSidebarColor ?? Colors.grey[200]!;

  Color _contrastColor(Color bg) {
    final luminance = bg.computeLuminance();
    return luminance > 0.5 ? Colors.black87 : Colors.white;
  }

  Widget _buildControlButtons() {
    return Center(
      child: Material(
        color: Colors.transparent,
        child: Container(
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(6),
            boxShadow: [
              BoxShadow(
                color: ColorUtils.withValues(Colors.black, 0.1),
                blurRadius: 6,
              )
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _buildControlButton(
                icon:
                    _panelWidth > 0 ? Icons.chevron_left : Icons.chevron_right,
                onPressed: togglePanel,
                width: 14,
              ),
              _buildControlButton(
                icon: _isLocked ? Icons.lock : Icons.lock_open,
                onPressed: () => setState(() => _isLocked = !_isLocked),
                width: 14,
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final double panelWidth = ref.watch(sidebarProvider);
    final sidebarBg = _sidebarBg;
    final appLocalizations = AppLocalizations.of(context)!;
    return LayoutBuilder(
      builder: (context, constraints) {
        // 确保侧边栏不会导致内容区域溢出
        final double maxAllowedWidth = constraints.maxWidth - 16 - 200;
        final double effectivePanelWidth = panelWidth > 0
            ? panelWidth.clamp(
                ResizablePanel.minWidth,
                maxAllowedWidth.isFinite
                    ? maxAllowedWidth
                    : ResizablePanel.maxWidth,
              )
            : 0;

        return Row(
          children: [
            // 侧边栏 - 当宽度为0时完全隐藏
            if (effectivePanelWidth > 0) ...[
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                curve: Curves.easeInOut,
                width: effectivePanelWidth,
                child: Container(
                  decoration: BoxDecoration(
                    color: sidebarBg,
                    boxShadow: [
                      BoxShadow(
                        color: ColorUtils.withValues(Colors.black, 0.1),
                        blurRadius: 8,
                        spreadRadius: 2,
                      )
                    ],
                  ),
                  child: ListView(
                    children: [
                      _buildUserAvatar(),
                      const SizedBox(height: 20),
                      _buildMenuButton(
                          1, Icons.home, appLocalizations.homeMenuItem),
                      _buildMenuButton(
                          2, Icons.message, appLocalizations.messagesMenuItem),
                      _buildMenuButton(
                          3, Icons.work, appLocalizations.workbenchMenuItem),
                      _buildMenuButton(
                          4, Icons.cloud, appLocalizations.sharedMenuItem),
                      _buildMenuButton(
                          5, Icons.public, appLocalizations.squareMenuItem),
                      const Divider(height: 20, thickness: 1),
                      _buildMenuButton(
                          6, Icons.settings, appLocalizations.settingsMenuItem),
                      if (kDebugMode) _buildTestButton(appLocalizations),
                    ],
                  ),
                ),
              ),
            ],
            // 拖拽条 - 始终显示
            MouseRegion(
              cursor: panelWidth > 0
                  ? SystemMouseCursors.resizeLeftRight
                  : SystemMouseCursors.basic,
              onEnter: (_) => setState(() => _showControls = true),
              onExit: (_) => setState(() => _showControls = false),
              child: GestureDetector(
                behavior: HitTestBehavior.translucent,
                onHorizontalDragUpdate:
                    panelWidth > 0 ? _handleDragUpdate : null,
                onHorizontalDragEnd: panelWidth > 0 ? _handleDragEnd : null,
                child: Container(
                  width: 16.0,
                  decoration: BoxDecoration(
                    gradient: panelWidth > 0
                        ? LinearGradient(
                            colors: [
                              sidebarBg,
                              ColorUtils.withValues(_contrastColor(_sidebarBg), 0.1),
                              _contrastColor(_sidebarBg)
                            ],
                            stops: const [0.0, 0.5, 1.0],
                            begin: Alignment.centerLeft,
                            end: Alignment.centerRight,
                          )
                        : const LinearGradient(
                            colors: [
                              Colors.white,
                              Colors.white,
                            ],
                            stops: [0.0, 1.0],
                          ),
                  ),
                  child: _showControls ? _buildControlButtons() : null,
                ),
              ),
            ),

            // 内容区域 - 使用Expanded填充剩余空间
            Expanded(
              child: Container(
                constraints: const BoxConstraints(
                  minWidth: 200.0,
                ),
                child: widget.content,
              ),
            ),
          ],
        );
      },
    );
  }
}
