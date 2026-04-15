// lib/presentation/pages/square/widgets/knowledge_graph_view.dart
//
// 知识图谱子标签页 — WebView 加载 ECharts 3D 图谱，数据来自 ZZCC 后端
//
// 通信: Flutter → JS 通过 evaluateJavascript 注入图谱数据
//       JS → Flutter 通过 JavaScriptChannel 接收事件

import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:zzcc/data/models/graph_model.dart';
import 'package:zzcc/data/repositories/graph_repository.dart';

class KnowledgeGraphView extends StatefulWidget {
  const KnowledgeGraphView({super.key});

  @override
  State<KnowledgeGraphView> createState() => _KnowledgeGraphViewState();
}

class _KnowledgeGraphViewState extends State<KnowledgeGraphView> {
  final GraphRepository _repo = GraphRepository();

  // WebView
  InAppWebViewController? _webCtrl;
  String? _htmlDataUrl;
  bool _htmlLoaded = false;

  // State
  bool _isLoading = true;
  bool _isFetching = false;
  double _progress = 0;
  String? _errorMsg;
  List<GraphSpace> _spaces = [];
  GraphSpace? _selectedSpace;
  final _queryCtrl = TextEditingController(text: 'MATCH (a)-[r]->(b) RETURN a, r, b LIMIT 100');
  bool _is3D = true;


  @override
  void initState() {
    super.initState();
    _loadHtml();
    _initSpaces();
  }

  @override
  void dispose() {
    _queryCtrl.dispose();
    super.dispose();
  }

  // ── HTML 加载（rootBundle → data URL）────────────────

  Future<void> _loadHtml() async {
    try {
      final html = await rootBundle.loadString(
        'assets/echarts/knowledge_graph.html',
        cache: false,
      );
      if (!mounted) return;
      setState(() {
        _htmlDataUrl = 'data:text/html;charset=utf-8,${Uri.encodeComponent(html)}';
        _htmlLoaded = true;
      });
    } catch (e) {
      debugPrint('Failed to load HTML: $e');
      if (mounted) setState(() => _htmlLoaded = true); // show error state
    }
  }

  // ── Spaces 初始化 ───────────────────────────────────

  Future<void> _initSpaces() async {
    final spaces = await _repo.getSpaces();
    if (!mounted) return;
    setState(() {
      _spaces = spaces;
      if (spaces.isNotEmpty && _selectedSpace == null) {
        _selectedSpace = spaces.first;
      }
    });
    if (_selectedSpace != null) {
      _loadGraph();
    }
  }

  // ── 图谱加载 ───────────────────────────────────────

  Future<void> _loadGraph() async {
    if (_selectedSpace == null || _webCtrl == null) return;
    setState(() => _isFetching = true);

    final graphData = await _repo.fetchGraphData(_selectedSpace!.name, limit: 200);

    if (!mounted) return;
    setState(() => _isFetching = false);

    if (graphData.nodes.isEmpty && graphData.links.isEmpty) {
      setState(() => _errorMsg = '该空间暂无数据');
      return;
    }

    final nodes = graphData.nodes.map((n) {
      return {
        'id': n.id,
        'label': n.label,
        'category': n.category,
        'symbolSize': n.symbolSize,
        'tags': n.tags,
        'props': n.props,
      };
    }).toList();

    final links = graphData.links.map((l) {
      return {'source': l.source, 'target': l.target, 'label': l.label};
    }).toList();

    final payload = jsonEncode({
      'nodes': nodes,
      'links': links,
      'categories': graphData.categories,
      'space': _selectedSpace?.name ?? '',
    });

    await _webCtrl!.evaluateJavascript(
      source: 'if(window.updateGraph) window.updateGraph($payload);',
    );
    setState(() => _errorMsg = null);
  }

  // ── nGQL 查询执行 ──────────────────────────────────

  Future<void> _executeQuery() async {
    if (_selectedSpace == null || _webCtrl == null) return;
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
              'label': node['name']?.toString() ?? node['title']?.toString() ?? id,
              'symbolSize': 30,
              'tags': [node['_tag']?.toString() ?? key],
              'props': Map<String, dynamic>.from(node)
                ..remove('_id')..remove('id')..remove('_tag'),
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
          links.add({'source': src, 'target': dst, 'label': r['_edge']?.toString() ?? ''});
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

    await _webCtrl!.evaluateJavascript(
      source: 'if(window.updateGraph) window.updateGraph($payload);',
    );
  }

  // ── 3D/2D 切换 ─────────────────────────────────────

  void _toggle3D() {
    setState(() => _is3D = !_is3D);
    _webCtrl?.evaluateJavascript(
      source: 'if(window.toggleView) window.toggleView();',
    );
  }

  Future<void> _reloadGraph() async {
    if (_selectedSpace == null) return;
    await _loadGraph();
  }

  // ── Build ──────────────────────────────────────────

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
    // HTML 加载中
    if (!_htmlLoaded) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(color: Color(0xFF00d4ff)),
            SizedBox(height: 12),
            Text('加载图谱引擎...', style: TextStyle(color: Color(0xFF8b949e))),
          ],
        ),
      );
    }

    return Stack(
      children: [
        // WebView
        if (_htmlDataUrl != null)
          InAppWebView(
            initialUrlRequest: URLRequest(url: WebUri(_htmlDataUrl!)),
            initialSettings: InAppWebViewSettings(
              javaScriptEnabled: true,
              transparentBackground: false,
              useShouldOverrideUrlLoading: false,
              allowFileAccessFromFileURLs: true,
              allowUniversalAccessFromFileURLs: true,
            ),
            onWebViewCreated: (ctrl) {
              _webCtrl = ctrl;
            },
            onLoadStart: (ctrl, url) {
              setState(() => _isLoading = true);
            },
            onLoadStop: (ctrl, url) async {
              setState(() => _isLoading = false);
              if (_selectedSpace != null) {
                await Future.delayed(const Duration(milliseconds: 600));
                _loadGraph();
              }
            },
            onProgressChanged: (ctrl, p) {
              setState(() => _progress = p / 100);
            },
            onReceivedError: (ctrl, req, err) {
              debugPrint('WebView error: ${err.description}');
              if (mounted) {
                setState(() {
                  _isLoading = false;
                  _errorMsg = 'WebView 加载失败: ${err.description}';
                });
              }
            },
          ),

        // Loading overlay
        if (_isLoading)
          Positioned.fill(
            child: Container(
              color: const Color(0xFF0a0a1a),
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      width: 200,
                      child: LinearProgressIndicator(
                        value: _progress > 0 ? _progress : null,
                        color: const Color(0xFF00d4ff),
                        backgroundColor: Colors.white12,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      _progress > 0
                          ? '加载中 ${(_progress * 100).toStringAsFixed(0)}%'
                          : '正在初始化...',
                      style: const TextStyle(color: Color(0xFF00d4ff)),
                    ),
                  ],
                ),
              ),
            ),
          ),

        // Fetching overlay
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

        // Error overlay
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
                  const Icon(Icons.warning_amber, color: Colors.orange, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _errorMsg!,
                      style: const TextStyle(color: Colors.orange, fontSize: 13),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.refresh, color: Colors.orange, size: 18),
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
            icon: const Icon(Icons.play_arrow, color: Color(0xFF58a6ff), size: 18),
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
            Text('加载中...', style: TextStyle(color: Color(0xFF8b949e), fontSize: 12)),
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
          icon: const Icon(Icons.arrow_drop_down, color: Color(0xFF8b949e), size: 18),
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
}
