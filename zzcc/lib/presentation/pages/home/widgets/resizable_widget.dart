import 'package:flutter/material.dart';

class ResizableWidget extends StatefulWidget {
  final Widget child;
  final Size minSize;
  final Size size;
  final Offset position;
  final VoidCallback? onStash;
  final VoidCallback? onBringToFront;
  final GlobalKey stashBoxKey;
  final bool isStashBoxExpanded;
  final ValueChanged<Offset>? onPositionChanged;
  final ValueChanged<Size>? onSizeChanged;

  const ResizableWidget({
    super.key,
    required this.position,
    required this.size,
    required this.minSize,
    required this.child,
    required this.stashBoxKey,
    required this.isStashBoxExpanded,
    this.onStash,
    this.onBringToFront,
    this.onPositionChanged,
    this.onSizeChanged,
  });

  @override
  State<ResizableWidget> createState() => _ResizableWidgetState();
}

class _ResizableWidgetState extends State<ResizableWidget> {
  late Size _size;
  late Offset _position;
  Offset? _dragStart;
  bool _isDragging = false;

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

  bool _checkRectIntersection(Rect rect1, Rect rect2) {
    return rect1.overlaps(rect2);
  }

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: _position.dx,
      top: _position.dy,
      width: _size.width,
      height: _size.height,
      child: GestureDetector(
        onPanStart: _handleDragStart,
        onPanUpdate: _handleDragUpdate,
        onPanEnd: (details) {
          setState(() => _isDragging = false);
          
          if (!widget.isStashBoxExpanded) {
            return;
          }
          
          final RenderBox renderBox = context.findRenderObject() as RenderBox;
          final widgetOffset = renderBox.localToGlobal(Offset.zero);
          final widgetRect = Rect.fromLTWH(
            widgetOffset.dx, 
            widgetOffset.dy, 
            _size.width, 
            _size.height
          );
          
          final stashBoxRenderObject = widget.stashBoxKey.currentContext?.findRenderObject();
          if (stashBoxRenderObject is RenderBox) {
            final stashBoxOffset = stashBoxRenderObject.localToGlobal(Offset.zero);
            final stashBoxSize = stashBoxRenderObject.size;
            final stashBoxRect = Rect.fromLTWH(
              stashBoxOffset.dx, 
              stashBoxOffset.dy, 
              stashBoxSize.width, 
              stashBoxSize.height
            );
            
            if (_checkRectIntersection(widgetRect, stashBoxRect)) {
              widget.onStash?.call();
            }
          }
        },
        child: Stack(
          children: [
            widget.child,
            Positioned(
              bottom: 0, // 从top改为bottom
              right: 0,
              child: GestureDetector(
                onPanStart: _handleResizeStart,
                onPanUpdate: _handleResizeUpdate,
                child: MouseRegion(
                  cursor: SystemMouseCursors.resizeDownRight,
                  child: Container(
                    width: 20,
                    height: 20,
                    decoration: BoxDecoration(
                      color: Colors.blue,
                      borderRadius: BorderRadius.circular(10),
                    ),
                  ),
                ),
              ),
            ),
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
          ],
        ),
      ),
    );
  }

  void _handleDragStart(DragStartDetails details) {
    setState(() => _isDragging = true);
    _dragStart = details.globalPosition - _position;
    widget.onBringToFront?.call();
  }

  void _handleDragUpdate(DragUpdateDetails details) {
    setState(() {
      _position = details.globalPosition - _dragStart!;
    });
    widget.onPositionChanged?.call(_position);
  }

  void _handleResizeStart(DragStartDetails details) {
    _dragStart = details.globalPosition;
    widget.onBringToFront?.call();
  }

  void _handleResizeUpdate(DragUpdateDetails details) {
    final newWidth = _size.width + (details.globalPosition.dx - _dragStart!.dx);
    final newHeight = _size.height + (details.globalPosition.dy - _dragStart!.dy);
    
    setState(() {
      _size = Size(
        newWidth.clamp(widget.minSize.width, double.infinity),
        newHeight.clamp(widget.minSize.height, double.infinity),
      );
      _dragStart = details.globalPosition;
    });
    widget.onSizeChanged?.call(_size);
  }
}