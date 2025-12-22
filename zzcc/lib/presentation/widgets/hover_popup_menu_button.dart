import 'package:flutter/material.dart';

class HoverPopupMenuButton<T> extends StatefulWidget {
  final PopupMenuButton<T> childButton;
  // 新增：允许自定义菜单宽度（解决文字堆叠）
  final double? menuWidth;

  const HoverPopupMenuButton({
    super.key,
    required this.childButton,
    this.menuWidth,
  });

  @override
  State<HoverPopupMenuButton<T>> createState() => _HoverPopupMenuButtonState<T>();
}

class _HoverPopupMenuButtonState<T> extends State<HoverPopupMenuButton<T>> {
  final GlobalKey _menuKey = GlobalKey();
  OverlayEntry? _overlayEntry;
  bool _isMenuShowing = false;
  // 新增：标记鼠标是否在菜单区域内
  bool _isMouseInMenu = false;

  // 创建菜单Overlay
  void _showMenu() {
    if (_isMenuShowing) return;

    final RenderBox buttonBox = 
        _menuKey.currentContext!.findRenderObject() as RenderBox;
    final Offset buttonPosition = buttonBox.localToGlobal(Offset.zero);
    final Size buttonSize = buttonBox.size;

    // 修复关键行：用括号明确优先级，确保返回正确的double值
    final double menuWidth = widget.menuWidth ?? (buttonSize.width > 0 ? buttonSize.width : 150);

    _overlayEntry = OverlayEntry(
      builder: (context) => Positioned(
        top: buttonPosition.dy + buttonSize.height,
        left: buttonPosition.dx,
        // 修复1：设置合理的菜单宽度（解决文字堆叠）
        width: menuWidth,
        child: MouseRegion(
          // 新增：监听菜单区域的鼠标进入/离开
          onEnter: (_) {
            setState(() => _isMouseInMenu = true);
          },
          onExit: (_) {
            setState(() => _isMouseInMenu = false);
            // 仅当鼠标离开菜单区域时才关闭
            _hideMenuIfNeeded();
          },
          child: Card(
            elevation: 4,
            // 修复2：用Column替代ListView，避免宽度挤压；加Padding保证内边距
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch, // 子组件占满宽度
                children: widget.childButton.itemBuilder(context)
                    .map((entry) => _buildMenuEntry(entry))
                    .toList(),
              ),
            ),
          ),
        ),
      ),
    );

    Overlay.of(context).insert(_overlayEntry!);
    setState(() => _isMenuShowing = true);
  }

  void _hideMenuIfNeeded() {
    if (!_isMenuShowing) return;
    
    // 延迟检查：确保鼠标完全离开按钮+菜单区域
    Future.delayed(const Duration(milliseconds: 100), () {
      if (mounted && _isMenuShowing && !_isMouseInMenu) {
        _hideMenu();
      }
    });
  }

  void _hideMenu() {
    if (!_isMenuShowing) return;
    
    _overlayEntry?.remove();
    setState(() {
      _isMenuShowing = false;
      _isMouseInMenu = false; // 重置标记
      _overlayEntry = null;
    });
  }

  Widget _buildMenuEntry(PopupMenuEntry<T> entry) {
    // 只处理PopupMenuItem，其他类型（如分割线）直接返回
    if (entry is PopupMenuItem<T>) {
      return InkWell(
        onTap: () {
          if (entry.onTap != null) entry.onTap!();
          widget.childButton.onSelected?.call(entry.value as T);
          _hideMenu();
        },
        // 修复3：设置菜单项内边距+占满宽度，文字不堆叠
        child: Container(
          width: double.infinity, // 占满菜单宽度
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: entry.child,
        ),
      );
    }
    // 非PopupMenuItem类型（如分割线）适配宽度
    return SizedBox(
      width: double.infinity,
      child: entry,
    );
  }

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      key: _menuKey,
      cursor: SystemMouseCursors.click,
      onEnter: (_) {
        // 鼠标进入按钮：展开菜单
        _showMenu();
      },
      onExit: (_) {
        // 鼠标离开按钮：仅当不在菜单内时才关闭
        _hideMenuIfNeeded();
      },
      child: widget.childButton,
    );
  }

  @override
  void dispose() {
    _hideMenu();
    super.dispose();
  }
}