// lib/presentation/pages/square/widgets/knowledge_graph_view.dart
//
// 知识图谱子标签页 — WebView 加载 ECharts 3D 图谱，数据来自 ZZCC 后端

import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:zzcc/data/models/graph_model.dart';
import 'package:zzcc/data/repositories/graph_repository.dart';
import 'package:zzcc/core/di/service_locator.dart';

// ── 内嵌 ECharts HTML（避免 asset 加载失败问题）───────────────
const String kGraphHtml = '<!DOCTYPE html>\n'
    '<html lang="zh-CN">\n'
    '<head>\n'
    '  <meta charset="UTF-8">\n'
    '  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">\n'
    '  <title>知识图谱 3D</title>\n'
    '  <style>\n'
    '    * { margin: 0; padding: 0; box-sizing: border-box; }\n'
    '    html, body { width: 100%; height: 100%; overflow: hidden; background: #0a0a1a; }\n'
    '    #chart { width: 100%; height: 100%; }\n'
    '\n'
    '    #panel {\n'
    '      position: absolute; top: 12px; left: 12px; z-index: 10;\n'
    '      background: rgba(10, 10, 30, 0.82);\n'
    '      border: 1px solid rgba(0, 212, 255, 0.3);\n'
    '      border-radius: 10px;\n'
    '      padding: 12px 14px;\n'
    '      min-width: 200px;\n'
    '      font-family: -apple-system, \'PingFang SC\', \'Microsoft YaHei\', sans-serif;\n'
    '      color: #cce8ff;\n'
    '      font-size: 13px;\n'
    '      backdrop-filter: blur(6px);\n'
    '    }\n'
    '    #panel h3 {\n'
    '      margin: 0 0 8px 0; font-size: 14px; font-weight: 600;\n'
    '      color: #00d4ff;\n'
    '      border-bottom: 1px solid rgba(0,212,255,0.2);\n'
    '      padding-bottom: 6px;\n'
    '    }\n'
    '    #panel .stat-row {\n'
    '      display: flex; justify-content: space-between; margin: 4px 0;\n'
    '    }\n'
    '    #panel .stat-val { color: #ffffff; font-weight: 600; }\n'
    '\n'
    '    #tooltip {\n'
    '      position: absolute; z-index: 20;\n'
    '      background: rgba(10, 10, 30, 0.9);\n'
    '      border: 1px solid rgba(0,212,255,0.5);\n'
    '      border-radius: 8px;\n'
    '      padding: 10px 14px;\n'
    '      font-family: -apple-system, \'PingFang SC\', sans-serif;\n'
    '      color: #e0f0ff;\n'
    '      font-size: 13px;\n'
    '      max-width: 260px;\n'
    '      pointer-events: none;\n'
    '      display: none;\n'
    '      line-height: 1.5;\n'
    '    }\n'
    '    #tooltip .tip-title { color: #00d4ff; font-weight: 600; margin-bottom: 4px; }\n'
    '    #tooltip .tip-tag { display: inline-block; background: rgba(0,212,255,0.15); border-radius: 4px; padding: 1px 6px; margin: 2px 3px 2px 0; font-size: 11px; }\n'
    '\n'
    '    #loading {\n'
    '      position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);\n'
    '      color: #00d4ff; font-family: -apple-system, sans-serif;\n'
    '      font-size: 16px; z-index: 5; text-align: center;\n'
    '    }\n'
    '    #loading.hidden { display: none; }\n'
    '  </style>\n'
    '</head>\n'
    '<body>\n'
    '\n'
    '<div id="panel">\n'
    '  <h3>📊 图谱概览</h3>\n'
    '  <div class="stat-row"><span>节点</span><span class="stat-val" id="stat-nodes">—</span></div>\n'
    '  <div class="stat-row"><span>边</span><span class="stat-val" id="stat-links">—</span></div>\n'
    '  <div class="stat-row"><span>空间</span><span class="stat-val" id="stat-space">—</span></div>\n'
    '  <div id="legend" style="margin-top:8px;"></div>\n'
    '</div>\n'
    '\n'
    '<div id="tooltip">\n'
    '  <div class="tip-title" id="tip-title"></div>\n'
    '  <div id="tip-tag" style="margin-top:4px;"></div>\n'
    '  <div id="tip-props" style="margin-top:4px; font-size:12px; color:#9dc8e8;"></div>\n'
    '</div>\n'
    '\n'
    '<div id="loading">\n'
    '  <div id="loading-spinner">⏳ 加载中...</div>\n'
    '</div>\n'
    '\n'
    '<div id="chart"></div>\n'
    '\n'
    '<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>\n'
    '<script src="https://cdn.jsdelivr.net/npm/echarts-gl@2.0.9/dist/echarts-gl.min.js"></script>\n'
    '<script>\n'
    '(function () {\n'
    '  var chart = echarts.init(document.getElementById(\'chart\'));\n'
    '  var is3D = true;\n'
    '  var currentSpace = \'\';\n'
    '  var rawData = { nodes: [], links: [], categories: [] };\n'
    '\n'
    '  var option = {\n'
    '    backgroundColor: \'#0a0a1a\',\n'
    '    animation: true,\n'
    '    animationDurationUpdate: 800,\n'
    '    progressive: 400,\n'
    '    tooltip: {\n'
    '      trigger: \'item\',\n'
    '      backgroundColor: \'transparent\',\n'
    '      borderWidth: 0,\n'
    '      padding: 0,\n'
    '      textStyle: { color: \'transparent\' },\n'
    '      formatter: function (params) {\n'
    '        if (params.dataType === \'node\') {\n'
    '          var d = params.data;\n'
    '          document.getElementById(\'tip-title\').textContent = d.label || d.id;\n'
    '          var tagHtml = (d.tags || []).map(function (t) {\n'
    '            return \'<span class="tip-tag">\' + t + \'</span>\';\n'
    '          }).join(\'\');\n'
    '          document.getElementById(\'tip-tag\').innerHTML = tagHtml;\n'
    '          var propsHtml = Object.keys(d.props || {}).slice(0, 4).map(function (k) {\n'
    '            return k + \': \' + (d.props[k] || \'\');\n'
    '          }).join(\'<br>\');\n'
    '          document.getElementById(\'tip-props\').innerHTML = propsHtml;\n'
    '          var tipEl = document.getElementById(\'tooltip\');\n'
    '          tipEl.style.display = \'block\';\n'
    '          return \'\';\n'
    '        }\n'
    '        return \'\';\n'
    '      }\n'
    '    },\n'
    '    xAxis3D: { show: false, min: -100, max: 100 },\n'
    '    yAxis3D: { show: false, min: -100, max: 100 },\n'
    '    zAxis3D: { show: false, min: -100, max: 100 },\n'
    '    grid3D: { show: false, width: \'100%\', height: \'100%\', viewControl: { beta: 40, alpha: 30, rotateSpeed: 30, zoomSensitivity: 1.2, autoRotate: true, autoRotateAfterInitialAnimationDelay: 2000 } },\n'
    '    series: [{\n'
    '      type: \'graphGL\',\n'
    '      name: \'knowledge_graph\',\n'
    '      coordinateSystem: \'cartesian3D\',\n'
    '      symbolSize: function (d) { return Math.min(60, 18 + (d.symbolSize || 1) * 4); },\n'
    '      nodeScaleRatio: 0.8,\n'
    '      roam: true,\n'
    '      focusNodeAdjacency: true,\n'
    '      lineStyle: { width: 1.2, color: \'rgba(0,212,255,0.55)\', curveness: 0.2, opacity: 0.7 },\n'
    '      itemStyle: { borderWidth: 2, borderColor: \'#fff\', shadowBlur: 12, shadowColor: \'rgba(0,212,255,0.4)\' },\n'
    '      label: { show: true, formatter: \'{b}\', fontSize: 12, color: \'#fff\', fontFamily: \'-apple-system, PingFang SC, sans-serif\', textShadowColor: \'#000\', textShadowBlur: 4 },\n'
    '      emphasis: { lineStyle: { width: 2.5, color: \'#00d4ff\', curveness: 0.1 }, itemStyle: { shadowBlur: 20, shadowColor: \'#00d4ff\' } },\n'
    '      categories: [],\n'
    '      data: [],\n'
    '      links: [],\n'
    '      force: {\n'
    '        repulsion: 120,\n'
    '        gravity: 0.05,\n'
    '        edgeLength: [50, 200],\n'
    '        layoutAnimation: true,\n'
    '        initLayout: \'circular\'\n'
    '      }\n'
    '    }]\n'
    '  };\n'
    '\n'
    '  chart.setOption(option);\n'
    '\n'
    '  // Follow mouse for tooltip\n'
    '  document.addEventListener(\'mousemove\', function (e) {\n'
    '    var tip = document.getElementById(\'tooltip\');\n'
    '    if (tip.style.display === \'block\') {\n'
    '      tip.style.left = (e.clientX + 14) + \'px\';\n'
    '      tip.style.top = (e.clientY - 10) + \'px\';\n'
    '    }\n'
    '  });\n'
    '  document.addEventListener(\'click\', function () {\n'
    '    document.getElementById(\'tooltip\').style.display = \'none\';\n'
    '  });\n'
    '\n'
    '  function buildOption(nodes, links, categories) {\n'
    '    var catNames = categories || [];\n'
    '    var catColors = [\'#00d4ff\', \'#ff6b6b\', \'#ffd93d\', \'#6bcb77\', \'#c77dff\', \'#ff9a3c\', \'#4cc9f0\', \'#f72585\'];\n'
    '    chart.setOption({\n'
    '      series: [{\n'
    '        name: \'knowledge_graph\',\n'
    '        categories: catNames.map(function (c, i) {\n'
    '          return { name: c, itemStyle: { color: catColors[i % catColors.length] } };\n'
    '        }),\n'
    '        data: nodes.map(function (n) {\n'
    '          return {\n'
    '            id: n.id,\n'
    '            name: n.label || n.id,\n'
    '            label: n.label || n.id,\n'
    '            value: [n.x || 0, n.y || 0, n.z || 0],\n'
    '            symbolSize: n.symbolSize || 20,\n'
    '            category: n.category || 0,\n'
    '            tags: n.tags || [],\n'
    '            props: n.props || {},\n'
    '            itemStyle: { color: catColors[(n.category || 0) % catColors.length] }\n'
    '          };\n'
    '        }),\n'
    '        links: links.map(function (l) {\n'
    '          return { source: l.source, target: l.target, name: l.label || \'\' };\n'
    '        })\n'
    '      }]\n'
    '    }, { notMerge: true });\n'
    '  }\n'
    '\n'
    '  function updateStats(nodes, links, space) {\n'
    '    document.getElementById(\'stat-nodes\').textContent = nodes.length;\n'
    '    document.getElementById(\'stat-links\').textContent = links.length;\n'
    '    document.getElementById(\'stat-space\').textContent = space || \'—\';\n'
    '  }\n'
    '\n'
    '  window.updateGraph = function (data) {\n'
    '    var nodes = data.nodes || [];\n'
    '    var links = data.links || [];\n'
    '    var categories = data.categories || [];\n'
    '    var space = data.space || \'\';\n'
    '\n'
    '    if (nodes.length === 0) {\n'
    '      document.getElementById(\'loading-spinner\').textContent = \'⚠️ 暂无图谱数据\';\n'
    '      return;\n'
    '    }\n'
    '\n'
    '    document.getElementById(\'loading\').classList.add(\'hidden\');\n'
    '    rawData = { nodes: nodes, links: links, categories: categories };\n'
    '    currentSpace = space;\n'
    '\n'
    '    buildOption(nodes, links, categories);\n'
    '    updateStats(nodes, links, space);\n'
    '  };\n'
    '\n'
    '  window.addEventListener(\'resize\', function () { chart.resize(); });\n'
    '\n'
    '  // 3D / 2D 切换\n'
    '  window.toggleView = function () {\n'
    '    is3D = !is3D;\n'
    '    if (is3D) {\n'
    '      chart.setOption({\n'
    '        grid3D: { show: false, viewControl: { beta: 40, alpha: 30, rotateSpeed: 30, zoomSensitivity: 1.2, autoRotate: true, autoRotateAfterInitialAnimationDelay: 2000 } }\n'
    '      });\n'
    '    } else {\n'
    '      chart.setOption({\n'
    '        grid3D: { show: false, viewControl: { projection: \'orthographic\', beta: 0, alpha: 0, rotateSpeed: 0, zoomSensitivity: 0.8 } }\n'
    '      });\n'
    '    }\n'
    '  };\n'
    '\n'
    '})();\n'
    '</script>\n'
    '</body>\n'
    '</html>\n';

String get _graphDataUrl =>
    'data:text/html;charset=utf-8,${Uri.encodeComponent(kGraphHtml)}';

class KnowledgeGraphView extends StatefulWidget {
  const KnowledgeGraphView({super.key});

  @override
  State<KnowledgeGraphView> createState() => _KnowledgeGraphViewState();
}

class _KnowledgeGraphViewState extends State<KnowledgeGraphView> {
  late final GraphRepository _repo;
  InAppWebViewController? _webCtrl;

  bool _isLoading = true;
  bool _isFetching = false;
  double _progress = 0;
  String? _errorMsg;
  List<GraphSpace> _spaces = [];
  GraphSpace? _selectedSpace;
  final _queryCtrl = TextEditingController(
      text: 'MATCH (a)-[r]->(b) RETURN a, r, b LIMIT 100');
  bool _is3D = true;

  @override
  void initState() {
    super.initState();
    debugPrint('[KGView] initState: getting GraphRepository...');
    try {
      _repo = getIt<GraphRepository>();
      debugPrint('[KGView] GraphRepository OK, calling _initSpaces...');
      _initSpaces();
    } catch (e, st) {
      debugPrint('[KGView] DI error: $e\n$st');
      setState(() => _errorMsg = '依赖注入失败: $e');
    }
  }

  @override
  void dispose() {
    _queryCtrl.dispose();
    super.dispose();
  }

  Future<void> _initSpaces() async {
    debugPrint('[KGView] _initSpaces: calling getSpaces...');
    try {
      final spaces = await _repo.getSpaces();
      debugPrint('[KGView] getSpaces returned ${spaces.length} spaces');
      if (!mounted) return;
      setState(() {
        _spaces = spaces;
        if (spaces.isNotEmpty && _selectedSpace == null) {
          _selectedSpace = spaces.first;
        }
      });
      if (_selectedSpace != null) {
        debugPrint('[KGView] selectedSpace: ${_selectedSpace!.name}');
        _loadGraph();
      } else {
        debugPrint('[KGView] no spaces available');
        setState(() {
          _isLoading = false;
          _errorMsg = '无法连接后端服务器\n请检查 124.223.47.167:8001 是否运行';
        });
      }
    } catch (e, st) {
      debugPrint('[KGView] _initSpaces error: $e\n$st');
      if (mounted) {
        setState(() => _errorMsg = '获取空间列表失败: $e');
      }
    }
  }

  Future<void> _loadGraph() async {
    if (_selectedSpace == null || _webCtrl == null) {
      debugPrint('[KGView] _loadGraph: skip (selectedSpace=$_selectedSpace, webCtrl=$_webCtrl)');
      return;
    }
    debugPrint('[KGView] _loadGraph: fetching ${_selectedSpace!.name}...');
    setState(() => _isFetching = true);

    try {
      final graphData =
          await _repo.fetchGraphData(_selectedSpace!.name, limit: 200);

      if (!mounted) return;
      setState(() => _isFetching = false);

      if (graphData.nodes.isEmpty && graphData.links.isEmpty) {
        debugPrint('[KGView] _loadGraph: empty data');
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

      debugPrint('[KGView] injecting ${nodes.length} nodes, ${links.length} links');
      await _webCtrl!.evaluateJavascript(
        source: 'if(window.updateGraph) window.updateGraph($payload);',
      );
      if (mounted) setState(() => _errorMsg = null);
    } catch (e, st) {
      debugPrint('[KGView] _loadGraph error: $e\n$st');
      if (mounted) {
        setState(() {
          _isFetching = false;
          _errorMsg = '加载图谱失败: $e';
        });
      }
    }
  }

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

    await _webCtrl!.evaluateJavascript(
      source: 'if(window.updateGraph) window.updateGraph(${payload});',
    );
  }

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
        InAppWebView(
          initialUrlRequest: URLRequest(url: WebUri(_graphDataUrl)),
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
            debugPrint('[KGView] onLoadStop: url=$url');
            setState(() => _isLoading = false);
            if (_selectedSpace != null) {
              debugPrint('[KGView] delaying 600ms then _loadGraph...');
              await Future.delayed(const Duration(milliseconds: 600));
              _loadGraph();
            } else {
              debugPrint('[KGView] onLoadStop: no selectedSpace, skip _loadGraph');
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
