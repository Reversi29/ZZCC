// knowledge_graph_view_web.dart
// Flutter Web 知识图谱 — iframe + ECharts + JS interop
// 与 native 版 UI 和数据流保持一致

import 'dart:convert';
import 'dart:html' as html;
import 'dart:js' as js;
import 'dart:ui_web' as ui_web;

import 'package:flutter/material.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/data/models/graph_model.dart';
import 'package:zzcc/data/repositories/graph_repository.dart';

import 'knowledge_graph_html.dart';

class KnowledgeGraphView extends StatefulWidget {
  const KnowledgeGraphView({super.key});

  @override
  State<KnowledgeGraphView> createState() => _KnowledgeGraphViewState();
}

class _KnowledgeGraphViewState extends State<KnowledgeGraphView> {
  late final GraphRepository _repo;

  bool _isLoading = true;
  bool _isFetching = false;
  String? _errorMsg;
  List<GraphSpace> _spaces = [];
  GraphSpace? _selectedSpace;
  final _queryCtrl = TextEditingController(
      text: 'MATCH (a)-[r]->(b) RETURN a, r, b LIMIT 100');
  bool _is3D = true;

  // iframe 管理
  html.IFrameElement? _iframe;
  late final String _viewType;

  @override
  void initState() {
    super.initState();
    _viewType = 'kg-chart-${DateTime.now().microsecondsSinceEpoch}';
    _registerIframe();
    try {
      _repo = getIt<GraphRepository>();
      _initSpaces();
    } catch (e, st) {
      debugPrint('[KGView-Web] DI error: $e\n$st');
      setState(() => _errorMsg = '依赖注入失败: $e');
    }
  }

  @override
  void dispose() {
    _queryCtrl.dispose();
    super.dispose();
  }

  void _registerIframe() {
    ui_web.platformViewRegistry.registerViewFactory(_viewType, (int viewId) {
      final iframe = html.IFrameElement()
        ..style.border = 'none'
        ..style.width = '100%'
        ..style.height = '100%'
        ..srcdoc = kGraphHtml;
      iframe.onLoad.listen((_) {
        debugPrint('[KGView-Web] iframe onLoad');
        setState(() => _isLoading = false);
        if (_selectedSpace != null) {
          Future.delayed(const Duration(milliseconds: 600), _loadGraph);
        }
      });
      _iframe = iframe;
      return iframe;
    });
  }

  Future<void> _initSpaces() async {
    try {
      final spaces = await _repo.getSpaces();
      if (!mounted) return;
      setState(() {
        _spaces = spaces;
        if (spaces.isNotEmpty && _selectedSpace == null) {
          _selectedSpace = spaces.first;
        }
      });
      if (_selectedSpace == null) {
        setState(() {
          _isLoading = false;
          _errorMsg = '无法连接后端服务器\n请检查 124.223.47.167:8001 是否运行';
        });
      }
    } catch (e, st) {
      debugPrint('[KGView-Web] _initSpaces error: $e\n$st');
      if (mounted) setState(() => _errorMsg = '获取空间列表失败: $e');
    }
  }

  void _callJs(String code) {
    final cw = _iframe?.contentWindow;
    if (cw == null) return;
    try {
      js.JsObject.fromBrowserObject(cw).callMethod('eval', [code]);
    } catch (e) {
      debugPrint('[KGView-Web] JS eval error: $e');
    }
  }

  Future<void> _loadGraph() async {
    if (_selectedSpace == null || _iframe == null) return;
    setState(() => _isFetching = true);

    try {
      final graphData =
          await _repo.fetchGraphData(_selectedSpace!.name, limit: 200);
      if (!mounted) return;
      setState(() => _isFetching = false);

      if (graphData.nodes.isEmpty && graphData.links.isEmpty) {
        setState(() => _errorMsg = '该空间暂无数据');
        return;
      }

      final nodes = graphData.nodes.map((n) => {
            'id': n.id,
            'label': n.label,
            'category': n.category,
            'symbolSize': n.symbolSize,
            'tags': n.tags,
            'props': n.props,
          }).toList();

      final links = graphData.links
          .map((l) => {'source': l.source, 'target': l.target, 'label': l.label})
          .toList();

      final payload = jsonEncode({
        'nodes': nodes,
        'links': links,
        'categories': graphData.categories,
        'space': _selectedSpace?.name ?? '',
      });

      _callJs('if(window.updateGraph) window.updateGraph($payload);');
      if (mounted) setState(() => _errorMsg = null);
    } catch (e, st) {
      debugPrint('[KGView-Web] _loadGraph error: $e\n$st');
      if (mounted) {
        setState(() {
          _isFetching = false;
          _errorMsg = '加载图谱失败: $e';
        });
      }
    }
  }

  Future<void> _executeQuery() async {
    if (_selectedSpace == null) return;
    final stmt = _queryCtrl.text.trim();
    if (stmt.isEmpty) return;

    setState(() {
      _isFetching = true;
      _errorMsg = null;
    });

    final raw = await _repo.query(_selectedSpace!.name, stmt);
    if (!mounted) return;
    setState(() => _isFetching = false);

    if (raw == null) {
      setState(() => _errorMsg = '查询失败或返回为空');
      return;
    }

    final nodes = <Map<String, dynamic>>[];
    final links = <Map<String, dynamic>>[];
    final seen = <String>{};

    final rows = (raw['rows'] as List<dynamic>?) ?? [];
    for (final row in rows) {
      for (final key in ['a', 'b']) {
        final node = row[key] as Map<String, dynamic>?;
        if (node != null) {
          final id = node['_id']?.toString() ?? node['id']?.toString() ?? '';
          if (id.isNotEmpty && !seen.contains(id)) {
            seen.add(id);
            nodes.add({
              'id': id,
              'label':
                  node['name']?.toString() ?? node['title']?.toString() ?? id,
              'symbolSize': 30,
              'tags': [node['_tag']?.toString() ?? key],
              'props': Map<String, dynamic>.from(node)
                ..remove('_id')
                ..remove('id')
                ..remove('_tag'),
            });
          }
        }
      }

      final r = row['r'] as Map<String, dynamic>?;
      final a = row['a'] as Map<String, dynamic>?;
      final b = row['b'] as Map<String, dynamic>?;
      if (a != null && b != null && r != null) {
        final src = a['_id']?.toString() ?? '';
        final dst = b['_id']?.toString() ?? '';
        if (src.isNotEmpty && dst.isNotEmpty) {
          links.add({
            'source': src,
            'target': dst,
            'label': r['_edge']?.toString() ?? ''
          });
        }
      }
    }

    if (nodes.isEmpty) {
      setState(() => _errorMsg = '查询无结果');
      return;
    }

    final payload = jsonEncode({
      'nodes': nodes,
      'links': links,
      'categories': <String>[],
      'space': _selectedSpace?.name ?? '',
    });

    _callJs('if(window.updateGraph) window.updateGraph($payload);');
  }

  void _toggle3D() {
    setState(() => _is3D = !_is3D);
    _callJs('if(window.toggleView) window.toggleView();');
  }

  Future<void> _reloadGraph() async {
    if (_selectedSpace == null) return;
    await _loadGraph();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _buildToolbar(),
        Expanded(child: _buildBody()),
      ],
    );
  }

  Widget _buildBody() {
    return Stack(
      children: [
        // iframe 平台视图
        HtmlElementView(viewType: _viewType),

        if (_isLoading)
          Positioned.fill(
            child: Container(
              color: const Color(0xFF0a0a1a),
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const SizedBox(
                      width: 200,
                      child: LinearProgressIndicator(
                        color: Color(0xFF00d4ff),
                        backgroundColor: Colors.white12,
                      ),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      '正在初始化...',
                      style: TextStyle(color: Color(0xFF00d4ff)),
                    ),
                  ],
                ),
              ),
            ),
          ),

        if (_isFetching && !_isLoading)
          Positioned(
            top: 8,
            right: 8,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Color(0xFF00d4ff),
                    ),
                  ),
                  SizedBox(width: 8),
                  Text(
                    '查询中...',
                    style: TextStyle(color: Color(0xFF00d4ff), fontSize: 12),
                  ),
                ],
              ),
            ),
          ),

        if (_errorMsg != null && !_isLoading)
          Positioned(
            bottom: 12,
            left: 12,
            right: 12,
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.black.withAlpha(200),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.orange.withAlpha(180)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.warning_amber,
                      color: Colors.orange, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _errorMsg!,
                      style:
                          const TextStyle(color: Colors.orange, fontSize: 13),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.refresh,
                        color: Colors.orange, size: 18),
                    onPressed: _reloadGraph,
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildToolbar() {
    return Container(
      height: 52,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: const BoxDecoration(
        color: Color(0xFF0d1117),
        border: Border(bottom: BorderSide(color: Color(0xFF21262d), width: 1)),
      ),
      child: Row(
        children: [
          _buildSpaceDropdown(),
          const SizedBox(width: 10),
          Expanded(child: _buildQueryInput()),
          const SizedBox(width: 8),
          _buildToolbarActions(),
        ],
      ),
    );
  }

  Widget _buildQueryInput() {
    return Container(
      height: 34,
      decoration: BoxDecoration(
        color: const Color(0xFF161b22),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: const Color(0xFF30363d)),
      ),
      child: Row(
        children: [
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 8),
            child: Text(
              'nGQL',
              style: TextStyle(color: Color(0xFF8b949e), fontSize: 12),
            ),
          ),
          Expanded(
            child: TextField(
              controller: _queryCtrl,
              style: const TextStyle(color: Color(0xFFe6edf3), fontSize: 12),
              decoration: const InputDecoration(
                isDense: true,
                contentPadding: EdgeInsets.symmetric(vertical: 8),
                border: InputBorder.none,
                hintText: 'MATCH (a)-[r]->(b) RETURN a, r, b LIMIT 100',
                hintStyle: TextStyle(color: Color(0xFF484f58), fontSize: 12),
              ),
              onSubmitted: (_) => _executeQuery(),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.play_arrow,
                color: Color(0xFF58a6ff), size: 18),
            onPressed: _isFetching ? null : _executeQuery,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32),
            tooltip: '执行查询',
          ),
        ],
      ),
    );
  }

  Widget _buildSpaceDropdown() {
    if (_spaces.isEmpty) {
      return Container(
        height: 32,
        padding: const EdgeInsets.symmetric(horizontal: 10),
        decoration: BoxDecoration(
          color: const Color(0xFF161b22),
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: const Color(0xFF30363d)),
        ),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.storage, color: Color(0xFF8b949e), size: 14),
            SizedBox(width: 6),
            Text('加载中...',
                style: TextStyle(color: Color(0xFF8b949e), fontSize: 12)),
          ],
        ),
      );
    }

    return Container(
      height: 32,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF161b22),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: const Color(0xFF30363d)),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<GraphSpace>(
          value: _selectedSpace,
          isDense: true,
          dropdownColor: const Color(0xFF161b22),
          style: const TextStyle(color: Color(0xFFe6edf3), fontSize: 12),
          icon: const Icon(Icons.arrow_drop_down,
              color: Color(0xFF8b949e), size: 18),
          items: _spaces.map((s) {
            return DropdownMenuItem(
              value: s,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.storage, color: Color(0xFF58a6ff), size: 14),
                  const SizedBox(width: 6),
                  Text(s.name),
                ],
              ),
            );
          }).toList(),
          onChanged: (space) {
            if (space == null) return;
            setState(() => _selectedSpace = space);
            _loadGraph();
          },
        ),
      ),
    );
  }

  Widget _buildToolbarActions() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (_spaces.any((s) => s.name == 'brain_semantic'))
          _buildQuickSpaceButton(
            label: '🧠 Brain',
            spaceName: 'brain_semantic',
            isActive: _selectedSpace?.name == 'brain_semantic',
          ),
        IconButton(
          icon: const Icon(Icons.refresh, color: Color(0xFF8b949e), size: 20),
          onPressed: _isFetching ? null : _reloadGraph,
          tooltip: '刷新图谱',
        ),
        IconButton(
          icon: Icon(
            _is3D ? Icons.view_in_ar : Icons.view_agenda,
            color: const Color(0xFF8b949e),
            size: 20,
          ),
          onPressed: _toggle3D,
          tooltip: _is3D ? '切换 2D' : '切换 3D',
        ),
        if (_spaces.isNotEmpty)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(0xFF161b22),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(color: const Color(0xFF30363d)),
            ),
            child: Text(
              '${_spaces.length} space${_spaces.length != 1 ? 's' : ''}',
              style: const TextStyle(color: Color(0xFF8b949e), fontSize: 11),
            ),
          ),
      ],
    );
  }

  Widget _buildQuickSpaceButton({
    required String label,
    required String spaceName,
    required bool isActive,
  }) {
    return GestureDetector(
      onTap: () {
        final space = _spaces.firstWhere((s) => s.name == spaceName);
        if (_selectedSpace?.name != spaceName) {
          setState(() => _selectedSpace = space);
          _loadGraph();
        }
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: isActive ? const Color(0xFF1a3a5c) : const Color(0xFF161b22),
          borderRadius: BorderRadius.circular(4),
          border: Border.all(
            color: isActive ? const Color(0xFF00d4ff) : const Color(0xFF30363d),
            width: isActive ? 1.5 : 1,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isActive ? const Color(0xFF00d4ff) : const Color(0xFF8b949e),
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
    );
  }
}
