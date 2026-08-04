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

  // Pointer tracking
  Offset _pointerLocal = Offset.zero; // always current
  _ResizeHandle? _hoveredHandle; // shown when not dragging
  _ResizeHandle? _activeHandle; // shown when dragging (never null after drag begins)

  // Drag state
  Offset? _dragStart;
  bool _isDragging = false;

  static const double _kDotSize = 12.0;
  static const double _kTouchSize = 40.0;
  static const double _kHalfTouch = _kTouchSize / 2;

  @override
  void initState() {
    super.initState();
    _size = widget.size;
    _position = widget.position;
  }

  @override
  void didUpdateWidget(covariant ResizableWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.position != widget.position) _position = widget.position;
    if (oldWidget.size != widget.size) _size = widget.size;
  }

  Rect? _stashBoxScreenRect() {
    final stashRender =
        widget.stashBoxKey.currentContext?.findRenderObject();
    if (stashRender is! RenderBox) return null;
    final globalOffset = stashRender.localToGlobal(Offset.zero);
    return globalOffset & stashRender.size;
  }

  bool _isOverStashBox = false;

  void _checkStashBoxHover(Offset globalCursor) {
    if (!widget.isStashBoxExpanded) return;
    final rect = _stashBoxScreenRect();
    if (rect == null) return;
    if (rect.contains(globalCursor) != _isOverStashBox) {
      _isOverStashBox = !_isOverStashBox;
      widget.onStashBoxHoverChanged?.call(_isOverStashBox);
    }
  }

  // ─── Hit testing ────────────────────────────────────────────────────────

  Rect _handleRect(_ResizeHandle h) {
    final w = _size.width;
    final h2 = _size.height;
    final t = _kHalfTouch;
    switch (h) {
      case _ResizeHandle.topLeft:
        return Rect.fromLTWH(-t, -t, _kTouchSize, _kTouchSize);
      case _ResizeHandle.topCenter:
        return Rect.fromLTWH(w / 2 - t, -t, _kTouchSize, _kTouchSize);
      case _ResizeHandle.topRight:
        return Rect.fromLTWH(w - t, -t, _kTouchSize, _kTouchSize);
      case _ResizeHandle.middleRight:
        return Rect.fromLTWH(w - t, h2 / 2 - t, _kTouchSize, _kTouchSize);
      case _ResizeHandle.bottomRight:
        return Rect.fromLTWH(w - t, h2 - t, _kTouchSize, _kTouchSize);
      case _ResizeHandle.bottomCenter:
        return Rect.fromLTWH(w / 2 - t, h2 - t, _kTouchSize, _kTouchSize);
      case _ResizeHandle.bottomLeft:
        return Rect.fromLTWH(-t, h2 - t, _kTouchSize, _kTouchSize);
      case _ResizeHandle.middleLeft:
        return Rect.fromLTWH(-t, h2 / 2 - t, _kTouchSize, _kTouchSize);
    }
  }

  _ResizeHandle? _hitTest(Offset local) {
    for (final h in [
      _ResizeHandle.topLeft,
      _ResizeHandle.topRight,
      _ResizeHandle.bottomLeft,
      _ResizeHandle.bottomRight,
      _ResizeHandle.topCenter,
      _ResizeHandle.bottomCenter,
      _ResizeHandle.middleLeft,
      _ResizeHandle.middleRight,
    ]) {
      if (_handleRect(h).contains(local)) return h;
    }
    return null;
  }

  MouseCursor _cursorFor(_ResizeHandle h) {
    switch (h) {
      case _ResizeHandle.topLeft:
      case _ResizeHandle.bottomRight:
        return SystemMouseCursors.resizeUpLeftDownRight;
      case _ResizeHandle.topRight:
      case _ResizeHandle.bottomLeft:
        return SystemMouseCursors.resizeUpRightDownLeft;
      case _ResizeHandle.topCenter:
      case _ResizeHandle.bottomCenter:
        return SystemMouseCursors.resizeUpDown;
      case _ResizeHandle.middleLeft:
      case _ResizeHandle.middleRight:
        return SystemMouseCursors.resizeLeftRight;
    }
  }

  MouseCursor get _effectiveCursor {
    // During drag: always show the handle cursor
    if (_isDragging && _activeHandle != null) return _cursorFor(_activeHandle!);
    // Idle: show hovered handle cursor
    if (_hoveredHandle != null) return _cursorFor(_hoveredHandle!);
    // No handle: show move or grab
    if (!widget.isEditMode) return SystemMouseCursors.basic;
    return widget.isSelected ? SystemMouseCursors.move : SystemMouseCursors.grab;
  }

  void _refreshHover() {
    if (!widget.isSelected) {
      if (_hoveredHandle != null) {
        _hoveredHandle = null;
        setState(() {});
      }
      return;
    }
    final h = _hitTest(_pointerLocal);
    if (h != _hoveredHandle) {
      _hoveredHandle = h;
      setState(() {});
    }
  }

  // ─── Gesture handlers ───────────────────────────────────────────────────

  void _onTap() {
    final ctrl = HardwareKeyboard.instance.isControlPressed;
    final shift = HardwareKeyboard.instance.isShiftPressed;
    if (shift) {
      widget.onDeselect?.call();
    } else if (ctrl) {
      if (widget.isSelected) {
        widget.onDeselect?.call();
      } else {
        widget.onSelect?.call(true);
      }
    } else if (widget.isSelected) {
      // already selected
    } else {
      widget.onSelect?.call(false);
    }
  }

  void _onPanStart(DragStartDetails details) {
    _isDragging = true;
    _dragStart = details.globalPosition - _position;
    widget.onBringToFront?.call();
    if (widget.isSelected) widget.onMultiDragStart?.call();
  }

  void _onPanUpdate(DragUpdateDetails details) {
    final globalPos = details.globalPosition;

    // Use the always-current _pointerLocal (updated by Listener.onPointerMove).
    if (_activeHandle != null) {
      // Currently resizing: if pointer moved out of this handle → stop resizing.
      // Otherwise keep resizing.
      _applyResize(_activeHandle!, details.delta);
    } else {
      // Check if the pointer is over a handle right now.
      final h = _hitTest(_pointerLocal);
      if (h != null) {
        // Switch to resize mode.
        _activeHandle = h;
        _applyResize(h, details.delta);
      } else {
        // Normal move.
        final newPos = globalPos - _dragStart!;
        setState(() => _position = newPos);
        widget.onPositionChanged?.call(_position);
        if (widget.isSelected) {
          widget.onMultiDragUpdate?.call(details.delta);
        }
      }
    }

    _checkStashBoxHover(globalPos);
  }

  void _onPanEnd(DragEndDetails details) {
    _isDragging = false;
    _activeHandle = null;
    _refreshHover(); // restore idle cursor
    setState(() {});

    if (_isOverStashBox) {
      _isOverStashBox = false;
      widget.onStashBoxHoverChanged?.call(false);
      widget.onStash?.call();
    } else {
      widget.onStashBoxHoverChanged?.call(false);
    }
  }

  void _applyResize(_ResizeHandle handle, Offset delta) {
    final dx = delta.dx;
    final dy = delta.dy;

    double newLeft = _position.dx;
    double newTop = _position.dy;
    double newWidth = _size.width;
    double newHeight = _size.height;

    switch (handle) {
      case _ResizeHandle.topLeft:
        newLeft += dx;
        newTop += dy;
        newWidth -= dx;
        newHeight -= dy;
        break;
      case _ResizeHandle.topCenter:
        newTop += dy;
        newHeight -= dy;
        break;
      case _ResizeHandle.topRight:
        newTop += dy;
        newWidth += dx;
        newHeight -= dy;
        break;
      case _ResizeHandle.middleRight:
        newWidth += dx;
        break;
      case _ResizeHandle.bottomRight:
        newWidth += dx;
        newHeight += dy;
        break;
      case _ResizeHandle.bottomCenter:
        newHeight += dy;
        break;
      case _ResizeHandle.bottomLeft:
        newLeft += dx;
        newWidth -= dx;
        newHeight += dy;
        break;
      case _ResizeHandle.middleLeft:
        newLeft += dx;
        newWidth -= dx;
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

  // ─── Build handle visual ────────────────────────────────────────────────

  Widget _buildHandle(_ResizeHandle h) {
    final r = _handleRect(h);
    return Positioned(
      left: r.left,
      top: r.top,
      width: _kTouchSize,
      height: _kTouchSize,
      child: Center(
        child: Container(
          width: _kDotSize,
          height: _kDotSize,
          decoration: BoxDecoration(
            color: Colors.blue,
            shape: BoxShape.circle,
            border: Border.all(color: Colors.white, width: 1.5),
          ),
        ),
      ),
    );
  }

  // ─── Build ──────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    if (!widget.isEditMode) {
      return Positioned(
        left: _position.dx,
        top: _position.dy,
        width: _size.width,
        height: _size.height,
        child: widget.child,
      );
    }

    return Positioned(
      left: _position.dx,
      top: _position.dy,
      width: _size.width,
      height: _size.height,
      child: MouseRegion(
        cursor: _effectiveCursor,
        onHover: (event) => _refreshHover(),
        onExit: (_) {
          _hoveredHandle = null;
          setState(() {});
        },
        child: Listener(
          onPointerMove: (event) {
            _pointerLocal = event.localPosition;
            _refreshHover();
          },
          child: GestureDetector(
            onTap: _onTap,
            onPanStart: _onPanStart,
            onPanUpdate: _onPanUpdate,
            onPanEnd: _onPanEnd,
            behavior: HitTestBehavior.opaque,
            child: Container(
              decoration: BoxDecoration(
                border: widget.isSelected
                    ? Border.all(color: Colors.blue, width: 2)
                    : null,
              ),
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  // Content
                  widget.child,
                  // Drag indicator
                  if (!_isDragging && !widget.isSelected)
                    Positioned.fill(
                      child: IgnorePointer(
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
                    Positioned.fill(
                      child: IgnorePointer(
                        child: Container(
                          color: const Color.fromARGB(25, 0, 0, 0),
                          child: Center(
                            child: Icon(
                              Icons.pan_tool_alt,
                              size: 40,
                              color: Colors.grey[600],
                            ),
                          ),
                        ),
                      ),
                    ),
                  // 8 resize handles (pure visuals — all events via outer Listener)
                  if (widget.isSelected)
                    for (final h in _ResizeHandle.values) _buildHandle(h),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
