import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class ResizableWidget extends StatefulWidget {
  final Widget child;
  final Size minSize;
  final Size size;
  final Offset position;
  final bool isEditMode;
  final VoidCallback? onStash;
  final VoidCallback? onBringToFront;
  final GlobalKey stashBoxKey;
  final bool isStashBoxExpanded;
  final ValueChanged<Offset>? onPositionChanged;
  final ValueChanged<Size>? onSizeChanged;
  final bool isSelected;
  final ValueChanged<bool>? onSelect;
  final VoidCallback? onDeselect;
  final VoidCallback? onMultiDragStart;
  final ValueChanged<Offset>? onMultiDragUpdate;
  final ValueChanged<bool>? onStashBoxHoverChanged;

  const ResizableWidget({
    super.key,
    required this.position,
    required this.size,
    required this.minSize,
    required this.child,
    required this.stashBoxKey,
    required this.isStashBoxExpanded,
    this.isEditMode = true,
    this.onStash,
    this.onBringToFront,
    this.onPositionChanged,
    this.onSizeChanged,
    this.isSelected = false,
    this.onSelect,
    this.onDeselect,
    this.onMultiDragStart,
    this.onMultiDragUpdate,
    this.onStashBoxHoverChanged,
  });

  @override
  State<ResizableWidget> createState() => _ResizableWidgetState();
}

enum _ResizeHandle {
  topLeft,
  topCenter,
  topRight,
  middleRight,
  bottomRight,
  bottomCenter,
  bottomLeft,
  middleLeft,
}

class _ResizableWidgetState extends State<ResizableWidget> {
  late Size _size;
  late Offset _position;
  Offset? _dragStart;
  bool _isDragging = false;
  static const double _handleHitSize = 10.0; // visual size of handle dot
  static const double _handleTouchSize = 28.0; // touch target for handle

  @override
  void initState() {
    super.initState();
    _size = widget.size;
    _position = widget.position;
  }

  @override
  void didUpdateWidget(covariant ResizableWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Keep internal state in sync if parent updates position/size.
    if (oldWidget.position != widget.position) {
      _position = widget.position;
    }
    if (oldWidget.size != widget.size) {
      _size = widget.size;
    }
  }

  /// Compute this widget's screen-space rect via localToGlobal (accounts for InteractiveViewer transform).
  /// Compute the stash box's screen-space rect.
  Rect? _stashBoxScreenRect() {
    final stashBoxRenderObject = widget.stashBoxKey.currentContext?.findRenderObject();
    if (stashBoxRenderObject is! RenderBox) return null;
    final offset = stashBoxRenderObject.localToGlobal(Offset.zero);
    return offset & stashBoxRenderObject.size;
  }

  bool _isOverStashBox = false;

  void _checkStashBoxHover(Offset cursorPosition) {
    if (!widget.isStashBoxExpanded) return;
    final stashRect = _stashBoxScreenRect();
    final over = stashRect != null && stashRect.contains(cursorPosition);
    if (over != _isOverStashBox) {
      _isOverStashBox = over;
      widget.onStashBoxHoverChanged?.call(over);
    }
  }

  @override
  Widget build(BuildContext context) {
    // View mode: no edit controls, just display child
    if (!widget.isEditMode) {
      return Positioned(
        left: _position.dx,
        top: _position.dy,
        width: _size.width,
        height: _size.height,
        child: widget.child,
      );
    }

    // Edit mode: drag moves component, resize handles only when selected
    final canResize = widget.isSelected;

    return Positioned(
      left: _position.dx,
      top: _position.dy,
      width: _size.width,
      height: _size.height,
      child: GestureDetector(
        onTap: _handleTap,
        onPanStart: _handleDragStart,
        onPanUpdate: _handleDragUpdate,
        onPanEnd: _handleDragEnd,
        child: Container(
          decoration: BoxDecoration(
            border: widget.isSelected
                ? Border.all(color: Colors.blue, width: 2)
                : null,
          ),
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              // Child content
              widget.child,
              // Drag indicator (not dragging, not selected)
              if (!_isDragging && !widget.isSelected)
                Positioned.fill(
                  child: Container(
                    color: Colors.transparent,
                    child: Center(
                      child: Icon(
                        Icons.drag_indicator,
                        color: Colors.grey.withValues(alpha: 0.3),
                        size: 28,
                      ),
                    ),
                  ),
                ),
              // Dragging overlay
              if (_isDragging)
                Container(
                  color: const Color.fromARGB(25, 0, 0, 0),
                  child: Center(
                    child: Icon(
                      Icons.pan_tool_alt,
                      size: 40,
                      color: Colors.grey[600],
                    ),
                  ),
                ),
              // 8 resize handles (only when selected in edit mode)
              if (canResize) ..._buildResizeHandles(),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _buildResizeHandles() {
    final handleColor = Colors.blue;
    return [
      _buildHandle(
        handle: _ResizeHandle.topLeft,
        position: const Offset(-1, -1),
        cursor: SystemMouseCursors.resizeUpLeftDownRight,
        color: handleColor,
      ),
      _buildHandle(
        handle: _ResizeHandle.topCenter,
        position: const Offset(0, -1),
        cursor: SystemMouseCursors.resizeUpDown,
        color: handleColor,
      ),
      _buildHandle(
        handle: _ResizeHandle.topRight,
        position: const Offset(1, -1),
        cursor: SystemMouseCursors.resizeUpRightDownLeft,
        color: handleColor,
      ),
      _buildHandle(
        handle: _ResizeHandle.middleRight,
        position: const Offset(1, 0),
        cursor: SystemMouseCursors.resizeLeftRight,
        color: handleColor,
      ),
      _buildHandle(
        handle: _ResizeHandle.bottomRight,
        position: const Offset(1, 1),
        cursor: SystemMouseCursors.resizeDownRight,
        color: handleColor,
      ),
      _buildHandle(
        handle: _ResizeHandle.bottomCenter,
        position: const Offset(0, 1),
        cursor: SystemMouseCursors.resizeUpDown,
        color: handleColor,
      ),
      _buildHandle(
        handle: _ResizeHandle.bottomLeft,
        position: const Offset(-1, 1),
        cursor: SystemMouseCursors.resizeUpRightDownLeft,
        color: handleColor,
      ),
      _buildHandle(
        handle: _ResizeHandle.middleLeft,
        position: const Offset(-1, 0),
        cursor: SystemMouseCursors.resizeLeftRight,
        color: handleColor,
      ),
    ];
  }

  Widget _buildHandle({
    required _ResizeHandle handle,
    required Offset position,
    required MouseCursor cursor,
    required Color color,
  }) {
    // position: (-1,-1) = topLeft, (0,1) = bottomCenter, etc.
    double? left, right, top, bottom;
    double? centerX, centerY;

    // Horizontal positioning
    if (position.dx < 0) {
      left = -_handleHitSize / 2;
    } else if (position.dx > 0) {
      right = -_handleHitSize / 2;
    } else {
      centerX = 0; // will use Center positioning
    }

    // Vertical positioning
    if (position.dy < 0) {
      top = -_handleHitSize / 2;
    } else if (position.dy > 0) {
      bottom = -_handleHitSize / 2;
    } else {
      centerY = 0;
    }

    final Widget dot = Container(
      width: _handleHitSize,
      height: _handleHitSize,
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 1.5),
      ),
    );

    final Widget touchTarget = SizedBox(
      width: _handleTouchSize,
      height: _handleTouchSize,
      child: Center(child: dot),
    );

    Widget positioned;
    if (centerX != null && centerY != null) {
      positioned = Center(child: touchTarget);
    } else if (centerX != null) {
      positioned = Positioned(
        top: top,
        bottom: bottom,
        left: 0,
        right: 0,
        child: Center(child: touchTarget),
      );
    } else if (centerY != null) {
      positioned = Positioned(
        left: left,
        right: right,
        top: 0,
        bottom: 0,
        child: Center(child: touchTarget),
      );
    } else {
      positioned = Positioned(
        left: left,
        right: right,
        top: top,
        bottom: bottom,
        child: touchTarget,
      );
    }

    return GestureDetector(
      onPanStart: (_) => _handleResizeStart(handle),
      onPanUpdate: (details) => _handleResizeUpdate(handle, details),
      child: MouseRegion(
        cursor: cursor,
        child: positioned,
      ),
    );
  }

  void _handleTap() {
    final isCtrlPressed = HardwareKeyboard.instance.isControlPressed;
    final isShiftPressed = HardwareKeyboard.instance.isShiftPressed;

    if (isShiftPressed) {
      // Shift+click to remove from selection
      widget.onDeselect?.call();
    } else if (isCtrlPressed) {
      // Ctrl+click to add to selection (or toggle)
      if (widget.isSelected) {
        widget.onDeselect?.call();
      } else {
        widget.onSelect?.call(true);
      }
    } else if (widget.isSelected) {
      // Click on already selected widget - keep selection (do nothing)
      return;
    } else {
      // Normal click to select only this (clear others)
      widget.onSelect?.call(false);
    }
  }

  void _handleDragStart(DragStartDetails details) {
    setState(() => _isDragging = true);
    _isOverStashBox = false;
    _dragStart = details.globalPosition - _position;
    widget.onBringToFront?.call();

    // Multi-drag if this widget is selected
    if (widget.isSelected) {
      widget.onMultiDragStart?.call();
    }
  }

  void _handleDragUpdate(DragUpdateDetails details) {
    final newPosition = details.globalPosition - _dragStart!;
    setState(() {
      _position = newPosition;
    });
    widget.onPositionChanged?.call(_position);
    if (widget.isSelected) {
      widget.onMultiDragUpdate?.call(details.delta);
    }
    _checkStashBoxHover(details.globalPosition);
  }

  void _handleDragEnd(DragEndDetails details) {
    setState(() => _isDragging = false);

    if (_isOverStashBox) {
      _isOverStashBox = false;
      widget.onStashBoxHoverChanged?.call(false);
      widget.onStash?.call();
    } else {
      // Ensure hover state is cleared even if not over stash box at release
      widget.onStashBoxHoverChanged?.call(false);
    }
  }

  void _handleResizeStart(_ResizeHandle handle) {
    widget.onBringToFront?.call();
  }

  void _handleResizeUpdate(_ResizeHandle handle, DragUpdateDetails details) {
    final dx = details.delta.dx;
    final dy = details.delta.dy;

    double newLeft = _position.dx;
    double newTop = _position.dy;
    double newWidth = _size.width;
    double newHeight = _size.height;

    // Horizontal
    switch (handle) {
      case _ResizeHandle.topLeft:
      case _ResizeHandle.middleLeft:
      case _ResizeHandle.bottomLeft:
        newLeft += dx;
        newWidth -= dx;
      case _ResizeHandle.topRight:
      case _ResizeHandle.middleRight:
      case _ResizeHandle.bottomRight:
        newWidth += dx;
      case _ResizeHandle.topCenter:
      case _ResizeHandle.bottomCenter:
        // No horizontal change
        break;
    }

    // Vertical
    switch (handle) {
      case _ResizeHandle.topLeft:
      case _ResizeHandle.topCenter:
      case _ResizeHandle.topRight:
        newTop += dy;
        newHeight -= dy;
      case _ResizeHandle.bottomLeft:
      case _ResizeHandle.bottomCenter:
      case _ResizeHandle.bottomRight:
        newHeight += dy;
      case _ResizeHandle.middleLeft:
      case _ResizeHandle.middleRight:
        // No vertical change
        break;
    }

    // Enforce minimum size
    if (newWidth < widget.minSize.width) {
      if (handle == _ResizeHandle.topLeft ||
          handle == _ResizeHandle.middleLeft ||
          handle == _ResizeHandle.bottomLeft) {
        newLeft -= widget.minSize.width - newWidth;
      }
      newWidth = widget.minSize.width;
    }
    if (newHeight < widget.minSize.height) {
      if (handle == _ResizeHandle.topLeft ||
          handle == _ResizeHandle.topCenter ||
          handle == _ResizeHandle.topRight) {
        newTop -= widget.minSize.height - newHeight;
      }
      newHeight = widget.minSize.height;
    }

    setState(() {
      _position = Offset(newLeft, newTop);
      _size = Size(newWidth, newHeight);
    });
    widget.onPositionChanged?.call(_position);
    widget.onSizeChanged?.call(_size);
  }
}