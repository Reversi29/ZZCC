// ZZCC 知识图谱视图 — 原生 CustomPainter 实现
//
// 设计原则：
// - 视窗裁剪：仅绘制 viewport 内的节点/边，避免绘制远处不可见内容
// - 多层 LOD：按 zoom 层级切换聚类显示（zoom 小时显示父聚类，zoom 大时展开子节点）
// - 矢量风格：无限缩放不失真，边/节点都是 Canvas 直接绘制
// - 手势：拖拽平移、双指/滚轮缩放、点选聚焦
//
// 数据源：ZZCC 后端 /api/v1/query 返回 GraphData（nodes/links/categories）

import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:zzcc/data/models/graph_model.dart';
import 'package:zzcc/data/repositories/graph_repository.dart';
import 'package:zzcc/core/di/service_locator.dart';

enum LayoutType { circular, force }

// ═══════════════════════════════════════════════════════════
// GraphQuadtree — O(log n) 视窗查询的空间索引
// ═══════════════════════════════════════════════════════════

class GraphQuadtree {
  final Rect bounds;
  final int maxItems;
  final int maxDepth;
  Rect? _current;
  List<dynamic>? _items;
  List<GraphQuadtree>? _children;

  GraphQuadtree(this.bounds, {this.maxItems = 8, this.maxDepth = 0}) {
    _current = bounds;
    _items = [];
  }

  void insert(dynamic item, Rect itemBounds) {
    if (_current!.overlaps(itemBounds) || _current!.overlaps(itemBounds)) {
      if (_items!.length < maxItems || _depth >= maxDepth) {
        _items!.add(item);
      } else {
        _subdivide();
        _insertIntoChild(item, itemBounds);
      }
    }
  }

  int _depth = 0;

  void _subdivide() {
    final b = _current!;
    _children = [
      GraphQuadtree(Rect.fromLTWH(b.left, b.top, b.width / 2, b.height / 2),
              maxItems: maxItems, maxDepth: maxDepth - 1)
        .._depth = _depth + 1,
      GraphQuadtree(Rect.fromLTWH(b.center.dx, b.top, b.width / 2, b.height / 2),
              maxItems: maxItems, maxDepth: maxDepth - 1)
        .._depth = _depth + 1,
      GraphQuadtree(Rect.fromLTWH(b.left, b.center.dy, b.width / 2, b.height / 2),
              maxItems: maxItems, maxDepth: maxDepth - 1)
        .._depth = _depth + 1,
      GraphQuadtree(Rect.fromLTWH(b.center.dx, b.center.dy, b.width / 2, b.height / 2),
              maxItems: maxItems, maxDepth: maxDepth - 1)
        .._depth = _depth + 1,
    ];
  }

  void _insertIntoChild(dynamic item, Rect itemBounds) {
    for (final c in _children!) {
      if (c._current!.overlaps(itemBounds) || c._current!.overlaps(itemBounds)) {
        c.insert(item, itemBounds);
        return;
      }
    }
    _items!.add(_QuadEntry(item, itemBounds));
  }

  List<dynamic> query(Rect region, [List<dynamic>? result]) {
    result ??= [];
    if (!_current!.overlaps(region)) return result;
    for (final item in _items!) {
      // item 是 _QuadEntry {obj, bounds}
      if (region.overlaps((item as _QuadEntry).bounds)) {
        result.add(item.obj);
      }
    }
    if (_children != null) {
      for (final c in _children!) {
        c.query(region, result);
      }
    }
    return result;
  }

  void clear() {
    _items = [];
    _children = null;
  }
}

class _QuadEntry {
  final dynamic obj;
  final Rect bounds;
  _QuadEntry(this.obj, this.bounds);
}



// ═══════════════════════════════════════════════════════════
// ForceLayoutEngine — Fruchterman-Reingold 力导布局
// ═══════════════════════════════════════════════════════════
class ForceLayoutEngine {
  static Map<String, Offset> computeLayout(List<EChartNode> nodes) {
    final n = nodes.length;
    if (n == 0) return {};
    const k = 80.0;
    double temperature = 200.0;
    final positions = <String, Offset>{};
    for (int i = 0; i < n; i++) {
      positions[nodes[i].id] = Offset(math.cos(2 * math.pi * i / n) * 200,
                                       math.sin(2 * math.pi * i / n) * 200);
    }
    for (int iter = 0; iter < 100; iter++) {
      final disp = <String, Offset>{for (final id in positions.keys) id: Offset.zero};
      for (var a in positions.keys.toList()) {
        for (var b in positions.keys.toList()) {
          if (a == b) continue;
          final delta = positions[a]! - positions[b]!;
          final dist = math.max(0.01, delta.distance);
          final repulse = k * k / dist;
          disp[a] = disp[a]! + (delta / dist) * repulse;
        }
      }
      for (var a in positions.keys.toList()) {
        final d = disp[a]!;
        final mag = d.distance;
        if (mag > temperature) disp[a] = d / mag * temperature;
        positions[a] = positions[a]! + disp[a]!;
      }
      temperature *= 0.95;
    }
    return _normalize(positions);
  }

  static Map<String, Offset> _normalize(Map<String, Offset> pos) {
    if (pos.isEmpty) return pos;
    double minX = double.infinity, maxX = double.negativeInfinity;
    double minY = double.infinity, maxY = double.negativeInfinity;
    for (final p in pos.values) {
      minX = math.min(minX, p.dx); maxX = math.max(maxX, p.dx);
      minY = math.min(minY, p.dy); maxY = math.max(maxY, p.dy);
    }
    final cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    final s = 600.0 / math.max(1.0, math.max(maxX - minX, maxY - minY));
    return {for (final e in pos.entries) e.key: Offset((e.value.dx - cx) * s, (e.value.dy - cy) * s)};
  }
}

// ═══════════════════════════════════════════════════════════
// LayoutEngine — 客户端布局（后端未返回坐标时使用）
//
// 策略：按 category 分组，category 中心绕大圆分布，
// 组内节点绕小组中心做 golden-angle 螺旋排布。
// 确定性（无随机），刷新不变。
// ═══════════════════════════════════════════════════════════

class LayoutEngine {
  static const double _goldenAngle = 2.399963229728653;

  /// 计算所有节点的最终 (x, y) 坐标
  static Map<String, Offset> computeLayout(GraphData data,
      {double worldRadius = 800}) {
    final result = <String, Offset>{};
    if (data.nodes.isEmpty) return result;

    // 按 category 分组
    final groups = <int, List<EChartNode>>{};
    for (final n in data.nodes) {
      groups.putIfAbsent(n.category, () => []).add(n);
    }

    final groupCount = groups.keys.length;
    final center = Offset.zero;

    // 单类别直接居中铺
    if (groupCount == 1) {
      _layoutCluster(groups.values.first, center, worldRadius * 0.7, result);
      return result;
    }

    // 多类别：类别中心绕大圆分布
    int groupIdx = 0;
    for (final entry in groups.entries) {
      final angle = (groupIdx / groupCount) * 2 * math.pi - math.pi / 2;
      final groupCenter = Offset(
        center.dx + math.cos(angle) * worldRadius * 0.6,
        center.dy + math.sin(angle) * worldRadius * 0.6,
      );
      _layoutCluster(entry.value, groupCenter, worldRadius * 0.35, result);
      groupIdx++;
    }
    return result;
  }

  static void _layoutCluster(List<EChartNode> nodes, Offset center,
      double radius, Map<String, Offset> out) {
    if (nodes.length == 1) {
      out[nodes.single.id] = center;
      return;
    }
    // Golden angle spiral: 每加一个节点角度累加 goldenAngle，半径按 sqrt(i) 递增
    final localRadius = radius / math.sqrt(nodes.length) * 2.5;
    for (int i = 0; i < nodes.length; i++) {
      final angle = i * _goldenAngle;
      final r = localRadius * math.sqrt(i + 1);
      out[nodes[i].id] = Offset(
        center.dx + math.cos(angle) * r,
        center.dy + math.sin(angle) * r,
      );
    }
  }
}

// ═══════════════════════════════════════════════════════════
// LodCluster — LOD 聚类节点（虚拟节点，代表被折叠的子节点集合）
// ═══════════════════════════════════════════════════════════

class LodCluster {
  final String id;
  final List<String> childIds;
  final Offset centroid;
  final double radius; // 覆盖子节点的包围半径
  final int category; // 若子节点同一 category 用它上色，否则 -1
  final String label;

  LodCluster({
    required this.id,
    required this.childIds,
    required this.centroid,
    required this.radius,
    required this.category,
    required this.label,
  });
}

// ═══════════════════════════════════════════════════════════
// LodManager — 按 zoom 层级切换聚类/展开
//
// 策略：
//   zoom >= kLoDExpandZoom：渲染所有子节点
//   kLoDDistZoom <= zoom < kLoDExpandZoom：按 bbox 距离聚类
//   zoom < kLoDDistZoom：进一步聚合（把相邻聚类再合成）
// ═══════════════════════════════════════════════════════════

class LodManager {
  static const double kLoDExpandZoom = 0.6;   // 大于此值展开全部
  static const double kLoDDistZoom = 0.25;     // 小于此值聚合一层
  static const double kLoDCollapseZoom = 0.12; // 更小聚合两层

  static const double _clusterRadiusFactor = 0.08; // 距离阈值 = 世界半径 * factor

  /// 根据 zoom 决定要渲染的节点与聚类
  static ({List<EChartNode> visible, List<LodCluster> clusters}) build(
      GraphData data, Map<String, Offset> positions, double zoom,
      {double worldRadius = 800}) {
    if (data.nodes.isEmpty) return (visible: const [], clusters: const []);

    if (zoom >= kLoDExpandZoom) {
      // 全展开
      return (visible: data.nodes, clusters: const []);
    }

    if (zoom < kLoDCollapseZoom) {
      // 聚合两层：先按 category，再聚合相邻 category
      return _collapseByCategory(data, positions);
    }

    // 距离聚类：把 bbox 内距离 < worldRadius * factor 的节点合成一个聚类
    return _clusterByDistance(data, positions,
        distance: worldRadius * _clusterRadiusFactor);
  }

  static ({List<EChartNode> visible, List<LodCluster> clusters})
      _clusterByDistance(
          GraphData data, Map<String, Offset> positions,
          {required double distance}) {
    final visited = <String>{};
    final clusters = <LodCluster>[];
    final visible = <EChartNode>[];

    for (final n in data.nodes) {
      if (visited.contains(n.id)) continue;

      // BFS 收集 bbox 内的邻居
      final group = <EChartNode>[n];
      visited.add(n.id);
      final queue = <EChartNode>[n];

      while (queue.isNotEmpty) {
        final current = queue.removeAt(0);
        final currentPos = positions[current.id] ?? Offset.zero;
        for (final candidate in data.nodes) {
          if (visited.contains(candidate.id)) continue;
          final candidatePos = positions[candidate.id] ?? Offset.zero;
          if ((candidatePos - currentPos).distance <= distance) {
            visited.add(candidate.id);
            group.add(candidate);
            queue.add(candidate);
          }
        }
      }

      if (group.length == 1) {
        visible.add(group.single);
      } else {
        clusters.add(_makeCluster(group, positions));
      }
    }

    // 过滤边：只保留两端都在可见集（含聚类）的边
    return (visible: visible, clusters: clusters);
  }

  static ({List<EChartNode> visible, List<LodCluster> clusters})
      _collapseByCategory(GraphData data, Map<String, Offset> positions) {
    final groups = <int, List<EChartNode>>{};
    for (final n in data.nodes) {
      groups.putIfAbsent(n.category, () => []).add(n);
    }

    final clusters = <LodCluster>[];
    final visible = <EChartNode>[];
    for (final entry in groups.entries) {
      if (entry.value.length == 1) {
        visible.add(entry.value.single);
      } else {
        clusters.add(_makeCluster(entry.value, positions));
      }
    }
    return (visible: visible, clusters: clusters);
  }

  static LodCluster _makeCluster(
      List<EChartNode> nodes, Map<String, Offset> positions) {
    Offset centroid = Offset.zero;
    double maxDist = 0;
    final category = nodes.first.category;

    for (final n in nodes) {
      final p = positions[n.id] ?? Offset.zero;
      centroid = centroid + p;
    }
    centroid = centroid / nodes.length.toDouble();

    for (final n in nodes) {
      final p = positions[n.id] ?? Offset.zero;
      maxDist = math.max(maxDist, (p - centroid).distance);
    }

    return LodCluster(
      id: 'cluster:${nodes.first.category}:${nodes.length}',
      childIds: nodes.map((n) => n.id).toList(),
      centroid: centroid,
      radius: maxDist * 1.2, // 略大留白
      category: nodes.length == 1 ? category :
          (nodes.map((n) => n.category).toSet().length == 1 ? category : -1),
      label: '×${nodes.length}',
    );
  }
}

// ═══════════════════════════════════════════════════════════
// KnowledgeGraphView — 主 widget
// ═══════════════════════════════════════════════════════════

class KnowledgeGraphView extends StatefulWidget {
  const KnowledgeGraphView({super.key});
  @override
  State<KnowledgeGraphView> createState() => _KnowledgeGraphViewState();
}

class _KnowledgeGraphViewState extends State<KnowledgeGraphView> {
  final GraphRepository _repo = getIt<GraphRepository>();

  List<GraphSpace> _spaces = [];
  GraphSpace? _selectedSpace;
  GraphData? _data;
  Map<String, Offset> _positions = {};
  List<LodCluster> _clusters = [];
  List<EChartNode> _visibleNodes = [];
  EChartNode? _selectedNode;
  EChartNode? _draggingNode;
  EChartNode? _hoveredNode;
  Offset _hoverScreenPos = Offset.zero;
  LayoutType _layoutType = LayoutType.circular;
  final TextEditingController _searchCtrl = TextEditingController();
  String _searchQuery = '';
  final Set<String> _hiddenCats = {};

  // 变换状态：world → screen
  Offset _panOffset = Offset.zero;   // 屏幕平移（世界坐标原点在哪）
  double _zoom = 0.4;                 // 缩放系数
  double _lastZoom = 0.4;
  Size _canvasSize = Size.zero;

  // LOD 阈值
  static const double kMinZoom = 0.03;
  static const double kMaxZoom = 5.0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _init());
  }

  Future<void> _init() async {
    try {
      final spaces = await _repo.getSpaces();
      if (!mounted) return;
      setState(() {
        _spaces = spaces;
        _selectedSpace = spaces.isNotEmpty ? spaces.first : null;
      });
      if (_selectedSpace != null) {
        await _loadGraph();
      }
    } catch (e) {
      debugPrint('[KG] init error: $e');
    }
  }

  Future<void> _loadGraph() async {
    final space = _selectedSpace;
    if (space == null) return;
    try {
      final data = await _repo.fetchGraphData(space.name, limit: 300);
      if (!mounted) return;
      setState(() {
        _data = data;
        _positions = (_layoutType == LayoutType.force)
            ? ForceLayoutEngine.computeLayout(data.nodes)
            : LayoutEngine.computeLayout(data);
        _updateLod();
        // 自适应初始 zoom 让所有节点可见
        _fitToView();
      });
    } catch (e) {
      debugPrint('[KG] load error: $e');
    }
  }

  void _updateLod() {
    final data = _data;
    if (data == null) return;
    final result = LodManager.build(data, _positions, _zoom);
    _visibleNodes = _applyLegendFilter(result.visible);
    _clusters = _applyLegendClusterFilter(result.clusters);
    _visibleNodes = _applySearchFilter(_visibleNodes);
  }

  List<EChartNode> _applyLegendFilter(List<EChartNode> nodes) {
    if (_hiddenCats.isEmpty) return nodes;
    return nodes.where((n) {
      for (final t in n.tags) {
        if (_hiddenCats.contains(t)) return false;
      }
      return true;
    }).toList();
  }

  List<LodCluster> _applyLegendClusterFilter(List<LodCluster> clusters) {
    if (_hiddenCats.isEmpty) return clusters;
    final data = _data;
    if (data == null) return clusters;
    return clusters.where((cl) {
      final catName = cl.category >= 0 && cl.category < data.categories.length
          ? data.categories[cl.category] : '';
      if (_hiddenCats.contains(catName)) return false;
      if (cl.childIds.isEmpty) return true;
      return cl.childIds.any((id) {
        for (final n in data.nodes) {
          if (n.id == id) {
            for (final t in n.tags) {
              if (_hiddenCats.contains(t)) return false;
            }
            return true;
          }
        }
        return false;
      });
    }).toList();
  }

  List<EChartNode> _applySearchFilter(List<EChartNode> nodes) {
    final q = _searchQuery.trim();
    if (q.isEmpty) return nodes;
    final terms = q.toLowerCase().split(RegExp(r'\\s+'));
    return nodes.where((n) {
      final label = n.label.toLowerCase();
      final id = n.id.toLowerCase();
      return terms.every((t) => label.contains(t) || id.contains(t));
    }).toList();
  }

  void _fitToView() {
    if (_positions.isEmpty || _canvasSize == Size.zero) return;
    // 计算所有节点的世界坐标范围
    double minX = double.infinity, minY = double.infinity;
    double maxX = -double.infinity, maxY = -double.infinity;
    for (final p in _positions.values) {
      if (p.dx < minX) minX = p.dx;
      if (p.dy < minY) minY = p.dy;
      if (p.dx > maxX) maxX = p.dx;
      if (p.dy > maxY) maxY = p.dy;
    }
    if (!minX.isFinite) return;
    final worldW = (maxX - minX) + 200;
    final worldH = (maxY - minY) + 200;
    final wZoom = _canvasSize.width / worldW;
    final hZoom = _canvasSize.height / worldH;
    final fitZoom = math.min(wZoom, hZoom);
    final worldCenter = Offset((minX + maxX) / 2, (minY + maxY) / 2);
    _zoom = fitZoom;
    _lastZoom = fitZoom;
    _panOffset = _worldToScreen(worldCenter, fitZoom);
  }

  // ═══════════════════════════════════════════════════════════
  // 坐标变换
  // ═══════════════════════════════════════════════════════════

  /// 世界坐标 → 屏幕坐标
  Offset _worldToScreen(Offset world, double zoom) {
    return Offset(
      _canvasSize.width / 2 + (world.dx - 0) * zoom + _panOffset.dx,
      _canvasSize.height / 2 + (world.dy - 0) * zoom + _panOffset.dy,
    );
  }

  /// 屏幕坐标 → 世界坐标
  Offset _screenToWorld(Offset screen) {
    return Offset(
      (screen.dx - _canvasSize.width / 2 - _panOffset.dx) / _zoom,
      (screen.dy - _canvasSize.height / 2 - _panOffset.dy) / _zoom,
    );
  }

  // ═══════════════════════════════════════════════════════════
  // 手势
  // ═══════════════════════════════════════════════════════════

  void _onPanStart(DragStartDetails d) {
    // Hit test: if we start dragging from a node, drag the node instead of panning
    EChartNode? hit;
    double bestDist = 24.0;
    for (final n in _visibleNodes) {
      final pos = _positions[n.id];
      if (pos == null) continue;
      final screen = _worldToScreen(pos, _zoom);
      final dist = (screen - d.localPosition).distance;
      if (dist < bestDist) {
        bestDist = dist;
        hit = n;
      }
    }
    _draggingNode = hit;
  }

  void _onPanUpdate(DragUpdateDetails d) {
    if (_draggingNode != null) {
      // Move node position in world space
      final worldDelta = Offset(d.delta.dx / _zoom, d.delta.dy / _zoom);
      final currentPos = _positions[_draggingNode!.id] ?? Offset.zero;
      _positions[_draggingNode!.id] = currentPos + worldDelta;
      setState(() {});
    } else {
      setState(() {
        _panOffset = _panOffset + d.delta;
      });
    }
  }

  void _onPanEnd(DragEndDetails d) {
    _draggingNode = null;
    _updateLod();
  }

  void _onScaleStart(ScaleStartDetails d) {
    _lastZoom = _zoom;
  }

  void _onScaleUpdate(ScaleUpdateDetails d) {
    if (d.scale == 0 || !d.scale.isFinite) return;
    final newZoom = (_lastZoom * d.scale).clamp(kMinZoom, kMaxZoom);
    // 保持焦点位置不移动
    final worldFocal = _screenToWorld(d.focalPoint - _panOffset);
    setState(() {
      _zoom = newZoom;
      // 补偿 panOffset 使世界焦点保持不动
      final newScreen = Offset(
        _canvasSize.width / 2 + worldFocal.dx * _zoom,
        _canvasSize.height / 2 + worldFocal.dy * _zoom,
      );
      _panOffset = d.focalPoint - newScreen;
      _updateLod();
    });
  }

  void _onScaleEnd(ScaleEndDetails d) {}

  void _onTapUp(TapUpDetails d) {
    // 查找点击命中的节点
    EChartNode? hit;
    double bestDist = 24.0;

    for (final n in _visibleNodes) {
      final pos = _positions[n.id];
      if (pos == null) continue;
      final screen = _worldToScreen(pos, _zoom);
      final dist = (screen - d.localPosition).distance;
      if (dist < bestDist) {
        bestDist = dist;
        hit = n;
      }
    }

    setState(() {
      _selectedNode = hit;
    });
  }

  void _onHover(PointerEvent e) {
    // Hit test for hover tooltip
    EChartNode? hit;
    double bestDist = 20.0;
    for (final n in _visibleNodes) {
      final pos = _positions[n.id];
      if (pos == null) continue;
      final screen = _worldToScreen(pos, _zoom);
      final dist = (screen - e.localPosition).distance;
      if (dist < bestDist) {
        bestDist = dist;
        hit = n;
      }
    }
    if (hit != _hoveredNode) {
      setState(() {
        _hoveredNode = hit;
        _hoverScreenPos = e.localPosition;
      });
    }
  }

  // ═══════════════════════════════════════════════════════════
  // UI
  // ═══════════════════════════════════════════════════════════

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF0A0A1A),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.cyan.withValues(alpha: 0.25)),
      ),
      child: Stack(
        children: [
          // 图谱画布
          LayoutBuilder(
            builder: (context, constraints) {
              final newSize = constraints.biggest;
              if (newSize != _canvasSize && _positions.isNotEmpty) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  setState(() {
                    _canvasSize = newSize;
                  });
                });
              } else if (_canvasSize == Size.zero) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  setState(() {
                    _canvasSize = newSize;
                    if (_data != null) _fitToView();
                  });
                });
              }
              return Listener(
                onPointerMove: _onHover,
                child: GestureDetector(
                onPanStart: _onPanStart,
                onPanUpdate: _onPanUpdate,
                onPanEnd: _onPanEnd,
                onScaleStart: _onScaleStart,
                onScaleUpdate: _onScaleUpdate,
                onScaleEnd: _onScaleEnd,
                onTapUp: _onTapUp,
                child: CustomPaint(
                  size: newSize,
                  painter: _KnowledgeGraphPainter(
                    visibleNodes: _visibleNodes,
                    clusters: _clusters,
                    edges: _filteredEdges(),
                    positions: _positions,
                    selectedNode: _selectedNode,
                    hoveredNode: _hoveredNode,
                    panOffset: _panOffset,
                    zoom: _zoom,
                    canvasSize: newSize,
                    backgroundColor: const Color(0xFF0A0A1A),
                    accentColor: scheme.primary,
                  ),
                ),
              ),
              );
            },
          ),

          // 顶部工具栏
          Positioned(
            top: 10, left: 10, right: 10,
            child: Row(
              children: [
                if (_spaces.isNotEmpty) ...[
                  Expanded(
                    child: DropdownButton<GraphSpace>(
                      value: _selectedSpace,
                      onChanged: (s) {
                        if (s == null || s == _selectedSpace) return;
                        setState(() { _selectedSpace = s; _selectedNode = null; });
                        _loadGraph();
                      },
                      items: _spaces.map((s) =>
                          DropdownMenuItem(value: s, child: Text(s.name))).toList(),
                      style: const TextStyle(color: Colors.white, fontSize: 12),
                      dropdownColor: const Color(0xFF101830),
                      underline: const SizedBox(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  SizedBox(
                    width: 140,
                    child: TextField(
                      controller: _searchCtrl,
                      onChanged: _onSearchChanged,
                      decoration: InputDecoration(
                        hintText: '搜索...',
                        prefixIcon: const Icon(Icons.search, size: 16),
                        suffixIcon: _searchQuery.isNotEmpty
                            ? IconButton(
                                icon: const Icon(Icons.clear, size: 14),
                                onPressed: () { _searchCtrl.clear(); _onSearchChanged(''); },
                              )
                            : null,
                        border: OutlineInputBorder(),
                        contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                        isDense: true,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  DropdownButton<LayoutType>(
                    value: _layoutType,
                    onChanged: (v) => _switchLayout(v!),
                    underline: const SizedBox(),
                    style: const TextStyle(color: Colors.white, fontSize: 12),
                    dropdownColor: const Color(0xFF101830),
                    items: const [
                      DropdownMenuItem(value: LayoutType.circular, child: Text('环形')),
                      DropdownMenuItem(value: LayoutType.force, child: Text('力导')),
                    ],
                  ),
                  const SizedBox(width: 8),
                  _iconButton(Icons.refresh, '重新加载', () => _loadGraph()),
                  _iconButton(Icons.center_focus_weak, '缩放适配', () => setState(_fitToView)),
                ],
                const Spacer(),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                  child: Text(
                    '${(_zoom * 100).round()}% · ${_visibleNodes.length} 节点 · ${_clusters.length} 聚类',
                    style: const TextStyle(color: Colors.white70, fontSize: 11),
                  ),
                ),
              ],
            ),
          ),

          // 底部图例
          Positioned(
            bottom: 10, left: 10,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text('图例:',
                      style: TextStyle(color: Colors.white70, fontSize: 11)),
                  const SizedBox(width: 6),
                  for (final cat in _data?.categories ?? []) ...[
                    InkWell(
                      onTap: () => _toggleCategory(cat),
                      child: Row(
                        children: [
                          Container(width: 10, height: 10,
                            decoration: BoxDecoration(
                              color: _hiddenCats.contains(cat)
                                  ? Colors.grey.withValues(alpha: 0.3)
                                  : _categoryColor(cat.hashCode, _data?.categories.length ?? 1),
                              shape: BoxShape.circle,
                            )),
                          const SizedBox(width: 4),
                          Text(cat, style: TextStyle(
                              color: _hiddenCats.contains(cat) ? Colors.grey : Colors.white70,
                              fontSize: 10,
                              decoration: _hiddenCats.contains(cat) ? TextDecoration.lineThrough : null)),
                          const SizedBox(width: 10),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),

          // Hover tooltip
          if (_hoveredNode != null && _draggingNode == null)
            Positioned(
              left: (_hoverScreenPos.dx + 14).clamp(0.0, (_canvasSize.width - 180).clamp(0.0, double.infinity)),
              top: (_hoverScreenPos.dy + 14).clamp(0.0, (_canvasSize.height - 80).clamp(0.0, double.infinity)),
              child: _NodeTooltip(node: _hoveredNode!),
            ),

          // 节点详情面板
          if (_selectedNode != null)
            Positioned(
              top: 50, right: 10,
              child: _NodeDetailPanel(
                node: _selectedNode!,
                onClose: () => setState(() => _selectedNode = null),
                onZoomIn: () => setState(() {
                  final pos = _positions[_selectedNode!.id];
                  if (pos == null) return;
                  _zoom = (_zoom * 1.8).clamp(kMinZoom, kMaxZoom);
                  _lastZoom = _zoom;
                  _panOffset = _worldToScreen(Offset.zero, _zoom) -
                      _worldToScreen(pos, _zoom) + _canvasSize.center(Offset.zero) - _canvasSize.center(Offset.zero);
                  // 简化：让选中节点移到屏幕中心
                  _panOffset = Offset(
                    -pos.dx * _zoom,
                    -pos.dy * _zoom,
                  );
                  _updateLod();
                }),
              ),
            ),

          // 空状态
          if (_data == null || _data!.nodes.isEmpty)
            Positioned(
              left: 0, right: 0, top: 60, bottom: 0,
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.graphic_eq, size: 64, color: Colors.cyan.withValues(alpha: 0.3)),
                    const SizedBox(height: 12),
                    Text(
                      _spaces.isEmpty ? '暂无图谱空间' : '该空间暂无数据',
                      style: const TextStyle(color: Colors.white38, fontSize: 14),
                    ),
                    if (_spaces.isEmpty)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 8),
                        child: Text('请先在后端 NebulaGraph 创建 space 和 tag',
                            style: TextStyle(color: Colors.white24, fontSize: 11)),
                      ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  void _switchLayout(LayoutType type) {
    setState(() { _layoutType = type; });
    _loadGraph();
  }

  void _onSearchChanged(String q) {
    setState(() { _searchQuery = q; });
    _updateLod();
  }

  void _toggleCategory(String cat) {
    setState(() {
      if (_hiddenCats.contains(cat)) { _hiddenCats.remove(cat); }
      else { _hiddenCats.add(cat); }
    });
    _updateLod();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  List<EChartLink> _filteredEdges() {
    final data = _data;
    if (data == null) return const [];
    final visibleIds = <String>{
      for (final n in _visibleNodes) n.id,
    };
    // 聚类包含的子节点也算"可见"
    for (final c in _clusters) {
      visibleIds.addAll(c.childIds);
    }
    final result = <EChartLink>[];
    for (final e in data.links) {
      if (visibleIds.contains(e.source) && visibleIds.contains(e.target)) {
        result.add(e);
      }
    }
    return result;
  }

  Widget _iconButton(IconData icon, String tooltip, VoidCallback onPressed) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Colors.white12,
        borderRadius: BorderRadius.circular(6),
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(6),
          child: Padding(
            padding: const EdgeInsets.all(6),
            child: Icon(icon, size: 16, color: Colors.white70),
          ),
        ),
      ),
    );
  }

  Color _categoryColor(int hash, int count) {
    // HSL 循环色板，count 决定均匀分布角度
    if (count == 0) return Colors.cyan;
    final angle = ((hash.abs() % count) / count) * 360.0;
    return HSLColor.fromAHSL(1, angle, 0.65, 0.7).toColor();
  }
}

// ═══════════════════════════════════════════════════════════
// NodeDetailPanel — 节点详情浮层
// ═══════════════════════════════════════════════════════════

class _NodeDetailPanel extends StatelessWidget {
  final EChartNode node;
  final VoidCallback onClose;
  final VoidCallback onZoomIn;

  const _NodeDetailPanel({
    required this.node,
    required this.onClose,
    required this.onZoomIn,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xE6101830),
      borderRadius: BorderRadius.circular(10),
      elevation: 8,
      child: Container(
        width: 260,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: Colors.cyan.withValues(alpha: 0.4)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 8, height: 8,
                  decoration: BoxDecoration(
                    color: Colors.cyan,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    node.label.isNotEmpty ? node.label : node.id,
                    style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                InkWell(
                  onTap: onClose,
                  child: const Padding(
                    padding: EdgeInsets.all(4),
                    child: Icon(Icons.close, size: 16, color: Colors.white54),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text('ID: ${node.id}',
                style: const TextStyle(color: Colors.white38, fontSize: 11, fontFamily: 'monospace')),
            if (node.tags.isNotEmpty) ...[
              const SizedBox(height: 6),
              Wrap(
                spacing: 4, runSpacing: 4,
                children: node.tags.map((t) => Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: Colors.cyan.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(t, style: const TextStyle(color: Colors.cyan, fontSize: 10)),
                )).toList(),
              ),
            ],
            if (node.props.isNotEmpty) ...[
              const SizedBox(height: 8),
              const Divider(color: Colors.white12, height: 1),
              const SizedBox(height: 6),
              for (final entry in node.props.entries)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 70,
                        child: Text(entry.key,
                            style: const TextStyle(color: Colors.white54, fontSize: 11)),
                      ),
                      Expanded(
                        child: Text(entry.value.toString(),
                            style: const TextStyle(color: Colors.white70, fontSize: 11),
                            overflow: TextOverflow.ellipsis),
                      ),
                    ],
                  ),
                ),
            ],
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: onZoomIn,
                icon: const Icon(Icons.zoom_in, size: 14),
                label: const Text('聚焦此节点'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.cyan,
                  side: const BorderSide(color: Colors.cyan),
                  padding: const EdgeInsets.symmetric(vertical: 6),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════
// KnowledgeGraphPainter — CustomPainter 绘制层
// ═══════════════════════════════════════════════════════════

class _KnowledgeGraphPainter extends CustomPainter {
  final List<EChartNode> visibleNodes;
  final List<LodCluster> clusters;
  final List<EChartLink> edges;
  final Map<String, Offset> positions;
  final EChartNode? selectedNode;
  final EChartNode? hoveredNode;
  final Offset panOffset;
  final double zoom;
  final Size canvasSize;
  final Color backgroundColor;
  final Color accentColor;
  GraphQuadtree? _qt;

  _KnowledgeGraphPainter({
    required this.visibleNodes,
    required this.clusters,
    required this.edges,
    required this.positions,
    required this.selectedNode,
    this.hoveredNode,
    required this.panOffset,
    required this.zoom,
    required this.canvasSize,
    required this.backgroundColor,
    required this.accentColor,
  });

  /// 世界坐标 → 屏幕坐标
  Offset _toScreen(Offset world) {
    return Offset(
      canvasSize.width / 2 + world.dx * zoom + panOffset.dx,
      canvasSize.height / 2 + world.dy * zoom + panOffset.dy,
    );
  }

  /// 视窗裁剪：返回屏幕矩形（扩大 padding 留边距）
  Rect _viewport() {
    return Rect.fromLTWH(-100, -100, canvasSize.width + 200, canvasSize.height + 200);
  }

  @override
  void paint(Canvas canvas, Size size) {
    _buildQuadtree();
    // 1. 背景
    canvas.drawRect(Rect.fromLTWH(0, 0, canvasSize.width, canvasSize.height), Paint()..color = backgroundColor);

    // 2. 网格（世界坐标对齐，只在视窗内画）
    _drawGrid(canvas);

    // 3. 边（先画，让节点压在上面）
    _drawEdges(canvas);

    // 4. 聚类（LOD 折叠）
    _drawClusters(canvas);

    // 5. 可见节点
    _drawNodes(canvas);

    // 6. 标签（zoom 足够大时）
    _drawLabels(canvas);
  }

  void _buildQuadtree() {
    _qt ??= GraphQuadtree(
      const Rect.fromLTRB(-20000, -20000, 20000, 20000),
      maxItems: 8,
      maxDepth: 4,
    );
    for (final node in visibleNodes) {
      final pos = positions[node.id];
      if (pos == null) continue;
      final screen = _toScreen(pos);
      const r = 20.0;
      _qt!.insert(node, Rect.fromCenter(center: screen, width: r * 2, height: r * 2));
    }
  }

  void _drawGrid(Canvas canvas) {
    // 世界坐标每 100 单位一格
    const gridStep = 100.0;
    final view = _viewport();
    // 计算视窗覆盖的世界范围
    // screen = center + world*zoom + pan, 所以 world = (screen - center - pan) / zoom
    final worldLeft = (view.left - canvasSize.width / 2 - panOffset.dx) / zoom;
    final worldRight = (view.right - canvasSize.width / 2 - panOffset.dx) / zoom;
    final worldTop = (view.top - canvasSize.height / 2 - panOffset.dy) / zoom;
    final worldBottom = (view.bottom - canvasSize.height / 2 - panOffset.dy) / zoom;

    // 只在小 zoom 时画网格（否则太密）
    if (zoom > 0.5) return;

    final paint = Paint()
      ..color = const Color(0x1800D4FF)
      ..strokeWidth = 0.5;

    double x = (worldLeft / gridStep).floorToDouble() * gridStep;
    while (x < worldRight) {
      final screen = _toScreen(Offset(x, 0));
      canvas.drawLine(screen, screen + Offset(0, canvasSize.height), paint);
      x += gridStep;
    }
    double y = (worldTop / gridStep).floorToDouble() * gridStep;
    while (y < worldBottom) {
      final screen = _toScreen(Offset(0, y));
      canvas.drawLine(screen, screen + Offset(canvasSize.width, 0), paint);
      y += gridStep;
    }
    // 中心十字
    final centerScreen = _toScreen(Offset.zero);
    final centerPaint = Paint()
      ..color = const Color(0x4000D4FF)
      ..strokeWidth = 1;
    canvas.drawLine(
      centerScreen - const Offset(8, 0), centerScreen + const Offset(8, 0), centerPaint);
    canvas.drawLine(
      centerScreen - const Offset(0, 8), centerScreen + const Offset(0, 8), centerPaint);
  }

  void _drawEdges(Canvas canvas) {
    final view = _viewport();
    final paint = Paint()
      ..color = const Color(0x66FFFFFF)
      ..strokeWidth = 1.2 * math.min(1.0, math.sqrt(zoom))
      ..style = PaintingStyle.stroke;

    for (final e in edges) {
      final s = positions[e.source];
      final t = positions[e.target];
      if (s == null || t == null) continue;

      final sScreen = _toScreen(s);
      final tScreen = _toScreen(t);

      // AABB 视窗裁剪
      final minX = math.min(sScreen.dx, tScreen.dx);
      final maxX = math.max(sScreen.dx, tScreen.dx);
      final minY = math.min(sScreen.dy, tScreen.dy);
      final maxY = math.max(sScreen.dy, tScreen.dy);
      if (!view.overlaps(Rect.fromLTRB(minX, minY, maxX, maxY))) continue;

      // 选中的节点相关边高亮
      final isHighlighted = e.source == selectedNode?.id || e.target == selectedNode?.id;
      Paint edgePaint;
      if (isHighlighted) {
        edgePaint = Paint()
          ..color = accentColor.withValues(alpha: 0.9)
          ..strokeWidth = 2.0 * math.min(1.5, math.sqrt(zoom))
          ..style = PaintingStyle.stroke;
      } else {
        edgePaint = paint;
      }
      canvas.drawLine(sScreen, tScreen, edgePaint);
    }
  }

  void _drawClusters(Canvas canvas) {
    final view = _viewport();
    for (final c in clusters) {
      final screen = _toScreen(c.centroid);
      final r = c.radius * zoom;
      if (!view.overlaps(Rect.fromCircle(center: screen, radius: r + 20))) continue;

      final color = _categoryColor(c.category);
      // 主圆
      canvas.drawCircle(screen, r, Paint()
        ..color = color.withValues(alpha: 0.15)
        ..style = PaintingStyle.fill);
      canvas.drawCircle(screen, r, Paint()
        ..color = color.withValues(alpha: 0.8)
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke);

      // 中心数字
      if (r > 12) {
        final text = TextPainter(
          text: TextSpan(
            text: c.label,
            style: TextStyle(
              color: Colors.white,
              fontSize: math.min(24, r * 0.9),
              fontWeight: FontWeight.bold,
            ),
          ),
          textDirection: TextDirection.ltr,
        )..layout();
        text.paint(
          canvas,
          Offset(screen.dx - text.width / 2, screen.dy - text.height / 2),
        );
      }
    }
  }

  void _drawNodes(Canvas canvas) {
    final view = _viewport();
    final nodeList = _qt == null
        ? visibleNodes.toList()
        : _qt!.query(view).cast<_QuadEntry>()
              .map((e) => e.obj)
              .whereType<EChartNode>()
              .toList();
    for (final n in nodeList) {
      final pos = positions[n.id];
      if (pos == null) continue;
      final screen = _toScreen(pos);
      if (!view.contains(screen)) continue;

      final isSelected = n.id == selectedNode?.id;
      final baseSize = n.symbolSize / 2.0;
      // 节点大小随 zoom 变化但保留最小尺寸
      final radius = baseSize * math.pow(zoom, 0.5).toDouble() + (isSelected ? 4 : 0);
      final color = _categoryColor(n.category);

      // 选中光晕
      if (isSelected) {
        canvas.drawCircle(screen, radius + 8, Paint()
          ..color = accentColor.withValues(alpha: 0.2)
          ..style = PaintingStyle.fill);
      }

      // 节点主体
      canvas.drawCircle(screen, radius, Paint()
        ..color = color.withValues(alpha: 0.95)
        ..style = PaintingStyle.fill);
      // 边
      canvas.drawCircle(screen, radius, Paint()
        ..color = Colors.white.withValues(alpha: isSelected ? 0.9 : 0.3)
        ..strokeWidth = isSelected ? 2.5 : 1.5
        ..style = PaintingStyle.stroke);
    }
  }

  void _drawLabels(Canvas canvas) {
    // zoom 太小时不画标签，避免视觉噪声
    if (zoom < 0.3) return;
    final view = _viewport();

    for (final n in visibleNodes) {
      final pos = positions[n.id];
      if (pos == null) continue;
      final screen = _toScreen(pos);
      if (!view.contains(screen)) continue;

      final isSelected = n.id == selectedNode?.id;
      final label = n.label.isNotEmpty ? n.label : n.id;
      if (label.length > 20) continue; // 太长不画

      final fontSize = (isSelected ? 14 : 11).toDouble();
      final tp = TextPainter(
        text: TextSpan(
          text: label,
          style: TextStyle(
            color: isSelected ? Colors.white : Colors.white70,
            fontSize: fontSize,
            fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();

      final radius = (n.symbolSize / 2.0) * math.pow(zoom, 0.5).toDouble();
      final labelPos = Offset(screen.dx - tp.width / 2, screen.dy + radius + 4);

      // 文字背景
      final bgRect = Rect.fromLTWH(labelPos.dx - 3, labelPos.dy - 1, tp.width + 6, tp.height + 2);
      canvas.drawRRect(
        RRect.fromRectAndRadius(bgRect, const Radius.circular(4)),
        Paint()..color = Colors.black.withValues(alpha: 0.55),
      );

      tp.paint(canvas, labelPos);
    }
  }

  Color _categoryColor(int category) {
    final angle = (category.abs() % 12) * 30.0;
    return HSLColor.fromAHSL(1, angle, 0.7, 0.7).toColor();
  }

  @override
  bool shouldRepaint(covariant _KnowledgeGraphPainter old) {
    return old.panOffset != panOffset
        || old.zoom != zoom
        || old.canvasSize != canvasSize
        || old.visibleNodes != visibleNodes
        || old.clusters != clusters
        || old.edges != edges
        || old.selectedNode?.id != selectedNode?.id;
  }
}

// ── Node Hover Tooltip ──
class _NodeTooltip extends StatelessWidget {
  final EChartNode node;
  const _NodeTooltip({required this.node});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xCC1A1A2E),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            node.label.isNotEmpty ? node.label : node.id,
            style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
          ),
          if (node.tags.isNotEmpty)
            Text(
              '#${node.tags.join(' #')}',
              style: const TextStyle(color: Colors.white54, fontSize: 10),
            ),
          if (node.props.isNotEmpty) ...[
            const SizedBox(height: 2),
            Text('${node.props.length} props', style: const TextStyle(color: Colors.white38, fontSize: 9)),
          ],
        ],
      ),
    );
  }
}
