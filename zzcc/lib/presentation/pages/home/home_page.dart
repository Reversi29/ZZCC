import 'package:flutter/material.dart';
import 'package:flutter/gestures.dart' show PointerSignalEvent, PointerScrollEvent;
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
  bool _showStashBox = false;
  final GlobalKey _stashBoxKey = GlobalKey();
  // Scroll controllers so we can manually route pointer scroll events
  // to the appropriate axis (vertical or horizontal).
  final ScrollController _hScrollController = ScrollController();
  final ScrollController _vScrollController = ScrollController();

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

  @override
  void dispose() {
    _hScrollController.dispose();
    _vScrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Row(
        children: [
          Expanded(
            child: MouseRegion(
              onEnter: (_) => setState(() => _showStashBox = false),
              child: DragTarget<WidgetType>(
                onAcceptWithDetails: (details) {
                  final renderBox = context.findRenderObject() as RenderBox;
                  final localPosition = renderBox.globalToLocal(details.offset);
                  _handleRestoreWidget(details.data, localPosition);
                },
                builder: (context, candidateData, rejectedData) {
                  return Listener(
                    onPointerSignal: (PointerSignalEvent event) {
                      if (event is PointerScrollEvent) {
                        try {
                          final dx = event.scrollDelta.dx;
                          final dy = event.scrollDelta.dy;

                          if (dx != 0 && _hScrollController.hasClients) {
                            final newOffset = (_hScrollController.offset + dx).clamp(_hScrollController.position.minScrollExtent, _hScrollController.position.maxScrollExtent);
                            _hScrollController.jumpTo(newOffset);
                          }

                          if (dy != 0 && _vScrollController.hasClients) {
                            final newOffset = (_vScrollController.offset + dy).clamp(_vScrollController.position.minScrollExtent, _vScrollController.position.maxScrollExtent);
                            _vScrollController.jumpTo(newOffset);
                          }
                        } catch (_) {}
                      }
                    },
                    child: SingleChildScrollView(
                      controller: _hScrollController,
                      scrollDirection: Axis.horizontal,
                      child: SingleChildScrollView(
                        controller: _vScrollController,
                        scrollDirection: Axis.vertical,
                        child: SizedBox(
                          // Keep canvas at viewport size so the surrounding Row
                          // isn't forced to expand beyond available width. The
                          // inner Stack still allows positioned/resizable
                          // children and the SingleChildScrollView enables
                          // panning when content overflows.
                          width: MediaQuery.of(context).size.width,
                          height: MediaQuery.of(context).size.height,
                          child: Stack(
                            children: _widgets.map((item) {
                              return ResizableWidget(
                                key: item.key,
                                position: item.position,
                                size: item.size,
                                minSize: item.minSize,
                                onStash: () => _handleStashWidget(item),
                                onBringToFront: () => _bringToFront(item),
                                stashBoxKey: _stashBoxKey,
                                isStashBoxExpanded: _showStashBox,
                                child: _buildWidgetByType(item.type),
                              );
                            }).toList(),
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
          MouseRegion(
            onEnter: (_) => setState(() => _showStashBox = true),
            onExit: (_) => setState(() => _showStashBox = false),
            child: AnimatedContainer(
              key: _stashBoxKey,
              duration: const Duration(milliseconds: 300),
              width: _showStashBox ? 120 : 20,
              decoration: BoxDecoration(
                color: Colors.grey[200],
                border: Border(left: BorderSide(color: Colors.grey.shade300)),
              ),
              child: _showStashBox ? Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.all(8.0),
                    child: Row(
                      children: [
                        const SizedBox(
                          width: 20,
                          height: 20,
                          child: Icon(Icons.inbox, size: 16),
                        ),
                        const SizedBox(width: 4),
                        Flexible(
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
                    ),
                  ),
                  const Divider(height: 1),
                  Expanded(
                    child: _stashBox.isEmpty
                        ? Center(
                            child: Text(
                              '拖拽组件到这里收纳',
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
              ) : Center(
                child: RotatedBox(
                  quarterTurns: 1,
                  child: Text(
                    '收纳盒',
                    style: TextStyle(
                      color: Colors.grey[600],
                      fontSize: 12,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
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
}

enum WidgetType {
  weather, todo, network, deviceStatus, location, calendar, hardwareDetails
}