import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:zzcc/presentation/pages/home/widgets/resizable_widget.dart';
import 'package:zzcc/presentation/pages/home/widgets/weather_widget.dart';
import 'package:zzcc/presentation/pages/home/widgets/todo_widget.dart';
import 'package:zzcc/presentation/pages/home/widgets/network_status_widget.dart';
import 'package:zzcc/presentation/pages/home/widgets/device_status_widget.dart';
import 'package:zzcc/presentation/pages/home/widgets/location_widget.dart';
import 'package:zzcc/presentation/pages/home/widgets/calendar_widget.dart';
import 'package:zzcc/presentation/pages/home/widgets/hardware_details_widget.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  late final List<WidgetItem> _widgets = _initWidgets();
  final List<WidgetItem> _stashBox = [];

  // Backup for cancel/restore functionality
  List<WidgetItem>? _backupWidgets;
  List<WidgetItem>? _backupStashBox;

  // Edit mode toggle (default: false = view mode)
  bool _isEditMode = false;

  // Stash box only visible in edit mode
  bool get _showStashBox => _isEditMode;
  final GlobalKey _stashBoxKey = GlobalKey();
  bool _isDraggingOverStashBox = false;
  // Transformation controller for infinite canvas panning
  final TransformationController _transformationController = TransformationController();
  // Minimap: cache last known viewport rect
  Rect? _lastViewportRect;
  bool _minimapLoopActive = true;

  // View mode (default): pan/zoom only, click widget triggers function
  // Edit mode: drag widgets, resize, box select, stash box visible

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _updateMinimapViewport());
  }


  void _updateMinimapViewport() {
    if (!_minimapLoopActive) return;
    try {
      final size = MediaQuery.of(context).size;
      final matrix = _transformationController.value;
      final scale = matrix.getMaxScaleOnAxis();
      final tx = matrix.getTranslation().x;
      final ty = matrix.getTranslation().y;
      if (_lastViewportRect != null) {
        final v = _lastViewportRect!;
        final same = (v.left.abs() - (-tx/scale).abs()) < 0.5 &&
                     (v.top.abs()  - (-ty/scale).abs()) < 0.5 &&
                     (v.width  - (size.width/scale)).abs() < 1.0 &&
                     (v.height - (size.height/scale)).abs() < 1.0;
        if (same) { WidgetsBinding.instance.addPostFrameCallback((_) => _updateMinimapViewport()); return; }
      }
      _lastViewportRect = Rect.fromLTWH(-tx/scale, -ty/scale, size.width/scale, size.height/scale);
      if (mounted) setState(() {});
    } catch (_) { /* context may be unavailable during hot reload */ }
    WidgetsBinding.instance.addPostFrameCallback((_) => _updateMinimapViewport());
  }

  // Multi-selection state
  final Set<Key> _selectedWidgetKeys = {};
  bool _isSelecting = false;
  Offset? _selectionStart;
  Offset? _selectionEnd;

  // Multi-drag state
  final Map<Key, Offset> _dragStartPositions = {};

  // Pointer state for Listener (edit mode)
  Offset? _pointerDownPos;
  bool _isPointerDragging = false;
  bool _pointerDownOnWidget = false; // Track if initial click was on a widget

  // Minimap state
  final GlobalKey _canvasKey = GlobalKey();

  // Compute bounding box of all widgets
  Rect _computeWidgetsBounds() {
    if (_widgets.isEmpty) return Rect.zero;
    
    double minX = double.infinity;
    double minY = double.infinity;
    double maxX = double.negativeInfinity;
    double maxY = double.negativeInfinity;
    
    for (final widget in _widgets) {
      minX = minX < widget.position.dx ? minX : widget.position.dx;
      minY = minY < widget.position.dy ? minY : widget.position.dy;
      final right = widget.position.dx + widget.size.width;
      final bottom = widget.position.dy + widget.size.height;
      maxX = maxX > right ? maxX : right;
      maxY = maxY > bottom ? maxY : bottom;
    }
    
    return Rect.fromLTRB(minX, minY, maxX, maxY);
  }

  Rect? _computeViewportRect() {
    final size = MediaQuery.of(context).size;
    final matrix = _transformationController.value;
    final translation = matrix.getTranslation();
    final scale = matrix.getMaxScaleOnAxis();
    final rect = Rect.fromLTWH(
      -translation.x / scale, -translation.y / scale,
      size.width / scale, size.height / scale,
    );
    debugPrint('[Minimap] viewport: left=${rect.left} top=${rect.top} w=${rect.width} h=${rect.height} scale=$scale');
    return rect;
  }



  List<WidgetItem> _initWidgets() {
    return [
      WidgetItem(
        key: GlobalKey(),
        type: WidgetType.weather,
        position: const Offset(0, 0),
        size: const Size(300, 200),
        minSize: const Size(300, 200),
      ),
      WidgetItem(
        key: GlobalKey(),
        type: WidgetType.todo,
        position: const Offset(0, 200),
        size: const Size(300, 300),
        minSize: const Size(300, 300),
      ),
      WidgetItem(
        key: GlobalKey(),
        type: WidgetType.network,
        position: const Offset(0, 500),
        size: const Size(300, 420),
        minSize: const Size(300, 420),
      ),
      WidgetItem(
        key: GlobalKey(),
        type: WidgetType.deviceStatus,
        position: const Offset(0, 920),
        size: const Size(300, 420),
        minSize: const Size(300, 420),
      ),
      WidgetItem(
        key: GlobalKey(),
        type: WidgetType.location,
        position: const Offset(300, 0),
        size: const Size(400, 400),
        minSize: const Size(400, 400),
      ),
      WidgetItem(
        key: GlobalKey(),
        type: WidgetType.calendar,
        position: const Offset(300, 400),
        size: const Size(600, 600),
        minSize: const Size(600, 600),
      ),
      WidgetItem(
        key: GlobalKey(),
        type: WidgetType.hardwareDetails,
        position: const Offset(700, 0),
        size: const Size(700, 400),
        minSize: const Size(700, 400),
      ),
    ];
  }

  Widget _buildWidgetByType(WidgetType type) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(10),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(10),
        child: switch (type) {
          WidgetType.weather => const WeatherWidget(),
          WidgetType.todo => const TodoWidget(),
          WidgetType.network => const NetworkStatusWidget(),
          WidgetType.deviceStatus => const DeviceStatusWidget(),
          WidgetType.location => const LocationWidget(),
          WidgetType.calendar => const CalendarWidget(),
          WidgetType.hardwareDetails => const HardwareDetailsWidget(),
        },
      ),
    );
  }

  void _handleStashWidget(WidgetItem widget) {
    setState(() {
      final renderBox = widget.key.currentContext?.findRenderObject() as RenderBox?;
      if (renderBox != null) {
        final updatedWidget = WidgetItem(
          key: widget.key,
          type: widget.type,
          position: widget.position,
          size: Size(renderBox.size.width, renderBox.size.height),
          minSize: widget.minSize,
        );
        
        _widgets.removeWhere((item) => item.key == widget.key);
        _stashBox.add(updatedWidget);
      } else {
        _widgets.remove(widget);
        _stashBox.add(widget);
      }
    });
  }

  void _handleRestoreWidget(WidgetType type, Offset position) {
    setState(() {
      final index = _stashBox.indexWhere((item) => item.type == type);
      if (index != -1) {
        final stashItem = _stashBox[index];
        _stashBox.removeAt(index);
        _widgets.add(WidgetItem(
          key: GlobalKey(),
          type: type,
          position: position,
          size: stashItem.size,
          minSize: stashItem.minSize,
        ));
      }
    });
  }

  void _bringToFront(WidgetItem widget) {
    setState(() {
      _widgets.remove(widget);
      _widgets.add(widget);
    });
  }

  void _updateWidgetPosition(GlobalKey key, Offset newPos) {
    final idx = _widgets.indexWhere((w) => w.key == key);
    if (idx != -1) {
      setState(() {
        final w = _widgets[idx];
        _widgets[idx] = w.copyWith(position: newPos);
      });
    }
  }

  void _updateWidgetSize(GlobalKey key, Size newSize) {
    final idx = _widgets.indexWhere((w) => w.key == key);
    if (idx != -1) {
      setState(() {
        final w = _widgets[idx];
        _widgets[idx] = w.copyWith(size: newSize);
      });
    }
  }

  Size _computeCanvasSize(BuildContext context) {
    const canvasExtent = 10000.0; // large fixed canvas size for infinite feel
    return const Size(canvasExtent, canvasExtent);
  }

  @override
  void dispose() {
    _minimapLoopActive = false;
    _transformationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: _buildToolbar(),
      body: Row(
        children: [
          Expanded(
            child: MouseRegion(
              child: DragTarget<WidgetType>(
                onAcceptWithDetails: (details) {
                  final renderBox = context.findRenderObject() as RenderBox;
                  final localPosition = renderBox.globalToLocal(details.offset);
                  _handleRestoreWidget(details.data, localPosition);
                },
                builder: (context, candidateData, rejectedData) {
                  final canvasSize = _computeCanvasSize(context);
                  final canvasContent = SizedBox(
                    width: canvasSize.width,
                    height: canvasSize.height,
                    child: Stack(
                      key: _canvasKey,
                      clipBehavior: Clip.none,
                      children: [
                        // Widgets
                        ..._widgets.map((item) {
                          return ResizableWidget(
                            key: item.key,
                            isEditMode: _isEditMode,
                            position: item.position,
                            size: item.size,
                            minSize: item.minSize,
                            onStash: () => _handleStashWidget(item),
                            onBringToFront: () => _bringToFront(item),
                            stashBoxKey: _stashBoxKey,
                            isStashBoxExpanded: _showStashBox,
                            onPositionChanged: (pos) => _updateWidgetPosition(item.key, pos),
                            onSizeChanged: (sz) => _updateWidgetSize(item.key, sz),
                            isSelected: _selectedWidgetKeys.contains(item.key),
                            onSelect: (addToSelection) => _handleWidgetSelect(item, addToSelection),
                            onDeselect: () => _handleWidgetDeselect(item),
                            onMultiDragStart: () => _handleMultiDragStart(item),
                            onMultiDragUpdate: (delta) => _handleMultiDragUpdate(delta),
                            onStashBoxHoverChanged: (isOver) => setState(() => _isDraggingOverStashBox = isOver),
                            child: _buildWidgetByType(item.type),
                          );
                        }),
                        // Minimap overlay - inside canvas Stack, bottom-left
                        Positioned(
                          left: 16,
                          bottom: 16,
                          child: _buildMinimap(),
                        ),
                      ],
                    ),
                  );

                  // In edit mode, wrap with GestureDetector at viewport level
                  // so it covers areas outside the canvas bounds when translated
                  final viewer = InteractiveViewer(
                    transformationController: _transformationController,
                    boundaryMargin: const EdgeInsets.all(double.infinity),
                    minScale: 0.1,
                    maxScale: 4.0,
                    constrained: false,
                    panEnabled: !_isEditMode, // View mode: built-in pan; Edit mode: manual via Listener
                    scaleEnabled: true, // Scale works with Listener - they don't conflict
                    child: canvasContent,
                  );

                  return Stack(
                    children: [
                      Positioned.fill(
                        child: _isEditMode
                            ? Listener(
                                behavior: HitTestBehavior.translucent,
                                onPointerDown: _handlePointerDown,
                                onPointerMove: _handlePointerMove,
                                onPointerUp: _handlePointerUp,
                                child: viewer,
                              )
                            : viewer,
                      ),
                      // Selection rectangle - drawn at viewport level
                      if (_isEditMode && _isSelecting && _selectionStart != null && _selectionEnd != null)
                        Positioned.fromRect(
                          rect: Rect.fromPoints(_selectionStart!, _selectionEnd!),
                          child: Container(
                            decoration: BoxDecoration(
                              color: Colors.blue.withValues(alpha: 0.2),
                              border: Border.all(color: Colors.blue, width: 1),
                            ),
                          ),
                        ),
                    ],
                  );
                },
              ),
            ),
          ),
          // Stash box - only shown in edit mode
          if (_showStashBox)
            AnimatedContainer(
              key: _stashBoxKey,
              duration: const Duration(milliseconds: 300),
              width: 120,
              decoration: BoxDecoration(
                color: _isDraggingOverStashBox ? Colors.lightBlue[100] : Colors.grey[200],
                border: Border(left: BorderSide(
                  color: _isDraggingOverStashBox ? Colors.lightBlue : Colors.grey.shade300,
                  width: _isDraggingOverStashBox ? 2 : 1,
                )),
              ),
              child: Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.all(8.0),
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        // When collapsing/animating the stash box, width can be < 24px.
                        // In that case render icon-only to avoid flex overflow.
                        if (constraints.maxWidth < 24) {
                          return const SizedBox(
                            width: 20,
                            height: 20,
                            child: Icon(Icons.inbox, size: 16),
                          );
                        }

                        final showText = constraints.maxWidth > 60;
                        return Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const SizedBox(
                              width: 20,
                              height: 20,
                              child: Icon(Icons.inbox, size: 16),
                            ),
                            if (showText) ...[
                              const SizedBox(width: 4),
                              Expanded(
                                child: Text(
                                  '收纳盒',
                                  overflow: TextOverflow.ellipsis,
                                  maxLines: 1,
                                  softWrap: false,
                                  style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    color: Colors.grey[700],
                                  ),
                                ),
                              ),
                            ],
                          ],
                        );
                      },
                    ),
                  ),
                  const Divider(height: 1),
                  Expanded(
                    child: _stashBox.isEmpty
                        ? Center(
                            child: Text(
                              _isDraggingOverStashBox ? '松开即可收纳' : '拖拽组件到这里收纳',
                              style: TextStyle(
                                color: Colors.grey[500],
                                fontSize: 12,
                              ),
                              textAlign: TextAlign.center,
                            ),
                          )
                        : ListView(
                            children: _stashBox.map((widget) => Draggable<WidgetType>(
                              data: widget.type,
                              feedback: Container(
                                width: 100,
                                height: 60,
                                decoration: BoxDecoration(
                                  color: Colors.blue.withAlpha(204),
                                  borderRadius: BorderRadius.circular(8),
                                  boxShadow: [
                                    BoxShadow(
                                      color: Colors.black.withAlpha(51),
                                      blurRadius: 4,
                                      offset: const Offset(0, 2),
                                    ),
                                  ],
                                ),
                                child: Center(
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Icon(_getWidgetIcon(widget.type), size: 20, color: Colors.white),
                                      const SizedBox(height: 4),
                                      Text(
                                        _getWidgetName(widget.type),
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontSize: 12,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                              childWhenDragging: Container(),
                              child: Container(
                                margin: const EdgeInsets.all(4),
                                padding: const EdgeInsets.all(8),
                                decoration: BoxDecoration(
                                  color: Colors.blue,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Center(
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Icon(_getWidgetIcon(widget.type), size: 20, color: Colors.white),
                                      const SizedBox(height: 4),
                                      Text(
                                        _getWidgetName(widget.type),
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontSize: 12,
                                        ),
                                        textAlign: TextAlign.center,
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            )).toList(),
                          ),
                  ),
                ],
              ),
          ),
        ],
      ),
    );
  }

  // Minimap widget
  Widget _buildMinimap() {
    final bounds = _computeWidgetsBounds();
    final viewportRect = _computeViewportRect();

    debugPrint('[Minimap] bounds=${bounds.left},${bounds.top},${bounds.width},${bounds.height} viewport=$viewportRect');

    if (bounds.isEmpty || viewportRect == null) {
      debugPrint('[Minimap] -> empty (bounds.isEmpty=${bounds.isEmpty} viewportRect=null)');
      return const SizedBox.shrink();
    }

    // Check if viewport contains all widgets
    final containsAll = viewportRect.contains(bounds.topLeft) && viewportRect.contains(bounds.bottomRight);
    debugPrint('[Minimap] containsAll=$containsAll (viewport ${viewportRect.left},${viewportRect.top} ${viewportRect.width}x${viewportRect.height} vs bounds ${bounds.width}x${bounds.height})');
    if (containsAll) {
      debugPrint('[Minimap] -> shrink (viewport contains all widgets)');
      return const SizedBox.shrink();
    }
    
    const minimapSize = 150.0;
    const padding = 20.0;
    
    // Compute scale to fit bounds + padding in minimap
    final contentWidth = bounds.width + padding * 2;
    final contentHeight = bounds.height + padding * 2;
    final scaleX = minimapSize / contentWidth;
    final scaleY = minimapSize / contentHeight;
    final scale = scaleX < scaleY ? scaleX : scaleY;
    
    // Minimap origin (top-left of content area in minimap coords)
    final originX = padding * scale - bounds.left * scale;
    final originY = padding * scale - bounds.top * scale;
    
    return Container(
      width: minimapSize,
      height: minimapSize,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(8),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.2),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: CustomPaint(
          size: const Size(minimapSize, minimapSize),
          painter: MinimapPainter(
            widgets: _widgets,
            viewportRect: viewportRect,
            scale: scale,
            origin: Offset(originX, originY),
          ),
        ),
      ),
    );
  }

  // Toolbar
  PreferredSizeWidget _buildToolbar() {
    return AppBar(
      title: const Text('工作台'),
      backgroundColor: Colors.white,
      foregroundColor: Colors.black,
      elevation: 1,
      actions: _isEditMode
          ? [
              // Save button (edit mode): save layout + exit edit mode
              TextButton.icon(
                onPressed: _saveLayout,
                icon: const Icon(Icons.save),
                label: const Text('保存'),
                style: TextButton.styleFrom(
                  foregroundColor: Colors.blue,
                ),
              ),
              // Exit button (edit mode): restore backup + exit edit mode
              TextButton.icon(
                onPressed: _cancelEdit,
                icon: const Icon(Icons.close),
                label: const Text('退出'),
                style: TextButton.styleFrom(
                  foregroundColor: Colors.grey,
                ),
              ),
              const SizedBox(width: 8),
            ]
          : [
              // Edit button (view mode): backup current state + enter edit mode
              TextButton.icon(
                onPressed: () {
                  setState(() {
                    // Backup current state before entering edit mode
                    _backupWidgets = _widgets.map((w) => WidgetItem(
                      key: w.key,
                      type: w.type,
                      position: w.position,
                      size: w.size,
                      minSize: w.minSize,
                    )).toList();
                    _backupStashBox = _stashBox.map((w) => WidgetItem(
                      key: w.key,
                      type: w.type,
                      position: w.position,
                      size: w.size,
                      minSize: w.minSize,
                    )).toList();
                    _isEditMode = true;
                  });
                },
                icon: const Icon(Icons.edit),
                label: const Text('编辑'),
                style: TextButton.styleFrom(
                  foregroundColor: Colors.blue,
                ),
              ),
              const SizedBox(width: 16),
            ],
    );
  }

  // Selection handlers
  void _handleWidgetSelect(WidgetItem item, bool addToSelection) {
    setState(() {
      if (addToSelection) {
        _selectedWidgetKeys.add(item.key);
      } else {
        _selectedWidgetKeys.clear();
        _selectedWidgetKeys.add(item.key);
      }
    });
  }

  void _handleWidgetDeselect(WidgetItem item) {
    setState(() {
      _selectedWidgetKeys.remove(item.key);
    });
  }

  void _saveLayout() {
    // Clear backup since we're saving
    _backupWidgets = null;
    _backupStashBox = null;
    
    // Exit edit mode
    setState(() {
      _isEditMode = false;
      _selectedWidgetKeys.clear();
    });
    
    // TODO: Implement actual persistence
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('布局已保存')),
    );
  }

  void _cancelEdit() {
    // Restore backup if available
    if (_backupWidgets != null) {
      _widgets.clear();
      for (final w in _backupWidgets!) {
        _widgets.add(WidgetItem(
          key: w.key,
          type: w.type,
          position: w.position,
          size: w.size,
          minSize: w.minSize,
        ));
      }
    }
    if (_backupStashBox != null) {
      _stashBox.clear();
      for (final w in _backupStashBox!) {
        _stashBox.add(WidgetItem(
          key: w.key,
          type: w.type,
          position: w.position,
          size: w.size,
          minSize: w.minSize,
        ));
      }
    }
    
    // Clear backup
    _backupWidgets = null;
    _backupStashBox = null;
    
    // Exit edit mode
    setState(() {
      _isEditMode = false;
      _selectedWidgetKeys.clear();
    });
  }

  // Canvas gesture handlers
  // Left-click drag: pan canvas
  // Ctrl + drag: box select (add to selection)
  // Shift + drag: box deselect (remove from selection)

  // Canvas gesture handlers (Listener - raw pointer events)
  // Listener receives events BEFORE gesture detection, and events propagate to children automatically.

  void _handlePointerDown(PointerDownEvent event) {
    if (!_isEditMode) return;
    _pointerDownPos = event.localPosition;
    _isPointerDragging = false;
    
    // Convert viewport position to canvas position
    final matrix = _transformationController.value;
    final inverseMatrix = Matrix4.inverted(matrix);
    final canvasPos = MatrixUtils.transformPoint(inverseMatrix, event.localPosition);
    
    // Check if pointer is on a widget
    _pointerDownOnWidget = false;
    for (final item in _widgets) {
      final widgetRect = Rect.fromLTWH(
        item.position.dx,
        item.position.dy,
        item.size.width,
        item.size.height,
      );
      if (widgetRect.contains(canvasPos)) {
        _pointerDownOnWidget = true;
        debugPrint('[PointerDown] On widget: ${item.key}');
        break;
      }
    }
    debugPrint('[PointerDown] viewportPos=${event.localPosition}, canvasPos=$canvasPos, onWidget=$_pointerDownOnWidget');
  }

  void _handlePointerMove(PointerEvent event) {
    if (!_isEditMode || _pointerDownPos == null) return;
    
    // If pointer started on a widget, let ResizableWidget handle it entirely
    if (_pointerDownOnWidget) {
      return;
    }

    // Check if this is a drag (moved more than threshold)
    if (!_isPointerDragging) {
      final delta = event.localPosition - _pointerDownPos!;
      if (delta.distance > 5) {
        _isPointerDragging = true;
        debugPrint('[PointerMove] Canvas drag started');
      }
    }
    
    if (!_isPointerDragging) return;

    // Handle canvas pan (not on any widget)
    final isCtrlPressed = HardwareKeyboard.instance.isControlPressed;
    final isShiftPressed = HardwareKeyboard.instance.isShiftPressed;

    if (_isSelecting) {
      setState(() {
        _selectionEnd = event.localPosition;
      });
    } else if (isCtrlPressed || isShiftPressed) {
      // Start selection
      setState(() {
        _isSelecting = true;
        _selectionStart = _pointerDownPos;
        _selectionEnd = event.localPosition;
      });
    } else {
      // Pan canvas using delta
      final matrix = _transformationController.value.clone();
      final translation = matrix.getTranslation();
      matrix.setTranslationRaw(
        translation.x + event.delta.dx,
        translation.y + event.delta.dy,
        translation.z,
      );
      _transformationController.value = matrix;
    }
  }

  void _handlePointerUp(PointerEvent event) {
    if (!_isEditMode) return;
    
    debugPrint('[PointerUp] pos=${event.localPosition}, isDragging=$_isPointerDragging, pointerDownPos=$_pointerDownPos');
    
    // If this was a tap (not drag) on empty space, deselect all
    if (!_isPointerDragging && _pointerDownPos != null) {
      final matrix = _transformationController.value;
      final inverseMatrix = Matrix4.inverted(matrix);
      final canvasPos = MatrixUtils.transformPoint(inverseMatrix, _pointerDownPos!);
      
      bool clickedOnWidget = false;
      for (final item in _widgets) {
        final widgetRect = Rect.fromLTWH(
          item.position.dx,
          item.position.dy,
          item.size.width,
          item.size.height,
        );
        if (widgetRect.contains(canvasPos)) {
          clickedOnWidget = true;
          debugPrint('[PointerUp] Click was on widget: ${item.key}');
          break;
        }
      }
      
      if (!clickedOnWidget) {
        debugPrint('[PointerUp] Click on empty space - deselecting all');
        setState(() {
          _selectedWidgetKeys.clear();
        });
      }
    }

    // Handle selection end
    if (_isSelecting && _selectionStart != null && _selectionEnd != null) {
      final matrix = _transformationController.value;
      final inverseMatrix = Matrix4.inverted(matrix);
      final canvasStart = MatrixUtils.transformPoint(inverseMatrix, _selectionStart!);
      final canvasEnd = MatrixUtils.transformPoint(inverseMatrix, _selectionEnd!);
      final selectionRect = Rect.fromPoints(canvasStart, canvasEnd);
      final isShiftPressed = HardwareKeyboard.instance.isShiftPressed;

      setState(() {
        for (final widget in _widgets) {
          final widgetRect = Rect.fromLTWH(
            widget.position.dx,
            widget.position.dy,
            widget.size.width,
            widget.size.height,
          );
          if (selectionRect.overlaps(widgetRect)) {
            if (isShiftPressed) {
              _selectedWidgetKeys.remove(widget.key);
            } else {
              _selectedWidgetKeys.add(widget.key);
            }
          }
        }
        _isSelecting = false;
        _selectionStart = null;
        _selectionEnd = null;
      });
    }

    _pointerDownPos = null;
    _isPointerDragging = false;
    _pointerDownOnWidget = false;
  }

  // Multi-drag handlers
  void _handleMultiDragStart(WidgetItem draggedItem) {
    _dragStartPositions.clear();
    for (final key in _selectedWidgetKeys) {
      final widget = _widgets.firstWhere((w) => w.key == key);
      _dragStartPositions[key] = widget.position;
    }
  }

  void _handleMultiDragUpdate(Offset delta) {
    setState(() {
      for (final entry in _dragStartPositions.entries) {
        final key = entry.key;
        final startPos = entry.value;
        final newPos = startPos + delta;
        
        final idx = _widgets.indexWhere((w) => w.key == key);
        if (idx != -1) {
          final w = _widgets[idx];
          _widgets[idx] = w.copyWith(position: newPos);
        }
      }
      // Update stored positions for next delta
      for (final key in _dragStartPositions.keys.toList()) {
        final widget = _widgets.firstWhere((w) => w.key == key);
        _dragStartPositions[key] = widget.position;
      }
    });
  }

  String _getWidgetName(WidgetType type) {
    return switch (type) {
      WidgetType.weather => '天气',
      WidgetType.todo => '待办',
      WidgetType.network => '网络',
      WidgetType.deviceStatus => '设备',
      WidgetType.location => '位置',
      WidgetType.calendar => '日历',
      WidgetType.hardwareDetails => '硬件',
    };
  }

  IconData _getWidgetIcon(WidgetType type) {
    return switch (type) {
      WidgetType.weather => Icons.cloud,
      WidgetType.todo => Icons.checklist,
      WidgetType.network => Icons.network_wifi,
      WidgetType.deviceStatus => Icons.device_thermostat,
      WidgetType.location => Icons.location_on,
      WidgetType.calendar => Icons.calendar_today,
      WidgetType.hardwareDetails => Icons.info,
    };
  }
}

class WidgetItem {
  final GlobalKey key;
  final WidgetType type;
  final Offset position;
  final Size size;
  final Size minSize;

  WidgetItem({
    required this.key,
    required this.type,
    required this.position,
    required this.size,
    required this.minSize,
  });

  WidgetItem copyWith({Offset? position, Size? size}) {
    return WidgetItem(
      key: key,
      type: type,
      position: position ?? this.position,
      size: size ?? this.size,
      minSize: minSize,
    );
  }
}

enum WidgetType {
  weather, todo, network, deviceStatus, location, calendar, hardwareDetails
}

// Minimap painter
class MinimapPainter extends CustomPainter {
  final List<WidgetItem> widgets;
  final Rect viewportRect;
  final double scale;
  final Offset origin;

  MinimapPainter({
    required this.widgets,
    required this.viewportRect,
    required this.scale,
    required this.origin,
  });

  @override
  void paint(Canvas canvas, Size size) {
    // Draw background
    final bgPaint = Paint()..color = Colors.grey.shade100;
    canvas.drawRect(Offset.zero & size, bgPaint);

    // Draw widgets
    final widgetPaint = Paint()..color = Colors.blue.shade300;
    for (final widget in widgets) {
      final rect = Rect.fromLTWH(
        origin.dx + widget.position.dx * scale,
        origin.dy + widget.position.dy * scale,
        widget.size.width * scale,
        widget.size.height * scale,
      );
      canvas.drawRect(rect, widgetPaint);
    }

    // Draw viewport indicator
    final viewportPaint = Paint()
      ..color = Colors.red.withValues(alpha: 0.3)
      ..style = PaintingStyle.fill;
    final viewportBorderPaint = Paint()
      ..color = Colors.red
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;

    final viewportRectLocal = Rect.fromLTWH(
      origin.dx + viewportRect.left * scale,
      origin.dy + viewportRect.top * scale,
      viewportRect.width * scale,
      viewportRect.height * scale,
    );
    canvas.drawRect(viewportRectLocal, viewportPaint);
    canvas.drawRect(viewportRectLocal, viewportBorderPaint);
  }

  @override
  bool shouldRepaint(covariant MinimapPainter oldDelegate) {
    return oldDelegate.widgets != widgets ||
        oldDelegate.viewportRect != viewportRect ||
        oldDelegate.scale != scale ||
        oldDelegate.origin != origin;
  }
}