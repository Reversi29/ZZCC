// ZZCC NebulaGraph 后端 API 调用层
// Base URL: http://124.223.47.167:8001/api/v1/

import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:logging/logging.dart';
import '../models/graph_model.dart';

const _zzccBaseUrl = 'http://124.223.47.167:8001/api/v1/';

class NebulaRemoteSource {
  final Dio _dio;
  final Logger _log = Logger('NebulaRemote');

  NebulaRemoteSource({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: _zzccBaseUrl,
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 15),
              headers: {
                'Content-Type': 'application/json',
                // API key 由 config_service 注入，或硬编码在这里
                'X-API-Key': 'zzcc-secret-key-2025',
              },
            ));

  // ── Spaces ──────────────────────────────────────────────

  /// 获取所有图空间列表
  Future<List<GraphSpace>> listSpaces() async {
    try {
      final resp = await _dio.get('/spaces');
      final data = resp.data;
      final spaces = (data['data']['spaces'] as List<dynamic>?)
              ?.map((s) => GraphSpace.fromJson(s as Map<String, dynamic>))
              .toList() ??
          [];
      return spaces;
    } on DioException catch (e) {
      _log.warning('listSpaces failed: ${e.message}');
      return [];
    }
  }

  /// 创建图空间
  Future<bool> createSpace({
    required String name,
    int partitionNum = 3,
    int replicaFactor = 1,
    String vidType = 'FIXED_STRING(64)',
  }) async {
    try {
      await _dio.post('/spaces', data: {
        'name': name,
        'partition_num': partitionNum,
        'replica_factor': replicaFactor,
        'vid_type': vidType,
      });
      return true;
    } on DioException catch (e) {
      _log.warning('createSpace failed: ${e.message}');
      return false;
    }
  }

  /// 删除图空间
  Future<bool> dropSpace(String name) async {
    try {
      await _dio.delete('/spaces/$name');
      return true;
    } on DioException catch (e) {
      _log.warning('dropSpace failed: ${e.message}');
      return false;
    }
  }

  // ── Tags ────────────────────────────────────────────────

  /// 获取当前空间的 tag 列表
  Future<List<GraphTag>> listTags(String space) async {
    try {
      final resp = await _dio.get('/tags', queryParameters: {'space': space});
      final data = resp.data;
      return (data['data']['tags'] as List<dynamic>?)
              ?.map((t) => GraphTag.fromJson(t as Map<String, dynamic>))
              .toList() ??
          [];
    } on DioException catch (e) {
      _log.warning('listTags failed: ${e.message}');
      return [];
    }
  }

  /// 创建 tag
  Future<bool> createTag({
    required String space,
    required String tag,
    List<Map<String, String>> properties = const [],
  }) async {
    try {
      await _dio.post('/tags', data: {
        'space': space,
        'tag': tag,
        'properties': properties,
      });
      return true;
    } on DioException catch (e) {
      _log.warning('createTag failed: ${e.message}');
      return false;
    }
  }

  /// 删除 tag
  Future<bool> dropTag(String space, String tag) async {
    try {
      await _dio.delete('/tags', data: {'space': space, 'tag': tag});
      return true;
    } on DioException catch (e) {
      _log.warning('dropTag failed: ${e.message}');
      return false;
    }
  }

  // ── Edge Types ─────────────────────────────────────────

  /// 获取 edge type 列表
  Future<List<GraphEdgeType>> listEdgeTypes(String space) async {
    try {
      final resp =
          await _dio.get('/edge-types', queryParameters: {'space': space});
      final data = resp.data;
      return (data['data']['edge_types'] as List<dynamic>?)
              ?.map((e) => GraphEdgeType.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [];
    } on DioException catch (e) {
      _log.warning('listEdgeTypes failed: ${e.message}');
      return [];
    }
  }

  /// 创建 edge type
  Future<bool> createEdgeType({
    required String space,
    required String edge,
    List<Map<String, String>> properties = const [],
  }) async {
    try {
      await _dio.post('/edge-types', data: {
        'space': space,
        'edge': edge,
        'properties': properties,
      });
      return true;
    } on DioException catch (e) {
      _log.warning('createEdgeType failed: ${e.message}');
      return false;
    }
  }

  /// 删除 edge type
  Future<bool> dropEdgeType(String space, String edge) async {
    try {
      await _dio.delete('/edge-types', data: {'space': space, 'edge': edge});
      return true;
    } on DioException catch (e) {
      _log.warning('dropEdgeType failed: ${e.message}');
      return false;
    }
  }

  // ── Vertices ────────────────────────────────────────────

  /// 查单个 vertex
  Future<GraphVertex?> getVertex(String space, String vid) async {
    try {
      final resp =
          await _dio.get('/vertices/$vid', queryParameters: {'space': space});
      if (resp.data['ok'] == true && resp.data['data'] != null) {
        return GraphVertex.fromJson(resp.data['data']);
      }
      return null;
    } on DioException catch (e) {
      _log.warning('getVertex failed: ${e.message}');
      return null;
    }
  }

  /// 插入 vertex
  Future<bool> insertVertex({
    required String space,
    required String tag,
    required String vid,
    Map<String, dynamic> props = const {},
  }) async {
    try {
      await _dio.post('/vertices', data: {
        'space': space,
        'tag': tag,
        'vid': vid,
        'props': props,
      });
      return true;
    } on DioException catch (e) {
      _log.warning('insertVertex failed: ${e.message}');
      return false;
    }
  }

  /// 更新 vertex
  Future<bool> updateVertex({
    required String space,
    required String tag,
    required String vid,
    Map<String, dynamic> props = const {},
  }) async {
    try {
      await _dio.patch('/vertices/$vid', data: {
        'space': space,
        'tag': tag,
        'props': props,
      });
      return true;
    } on DioException catch (e) {
      _log.warning('updateVertex failed: ${e.message}');
      return false;
    }
  }

  /// 删除 vertex（含边）
  Future<bool> deleteVertex(String space, String vid,
      {bool withEdges = true}) async {
    try {
      await _dio.delete('/vertices', data: {
        'space': space,
        'vid': vid,
        'with_edges': withEdges,
      });
      return true;
    } on DioException catch (e) {
      _log.warning('deleteVertex failed: ${e.message}');
      return false;
    }
  }

  // ── Edges ──────────────────────────────────────────────

  /// 查边
  Future<GraphEdge?> getEdge({
    required String space,
    required String edge,
    required String src,
    required String dst,
  }) async {
    try {
      final resp = await _dio.get('/edges', queryParameters: {
        'space': space,
        'edge': edge,
        'src': src,
        'dst': dst,
      });
      if (resp.data['ok'] == true && resp.data['data'] != null) {
        return GraphEdge.fromJson(resp.data['data']);
      }
      return null;
    } on DioException catch (e) {
      _log.warning('getEdge failed: ${e.message}');
      return null;
    }
  }

  /// 插入边
  Future<bool> insertEdge({
    required String space,
    required String edge,
    required String src,
    required String dst,
    Map<String, dynamic> props = const {},
  }) async {
    try {
      await _dio.post('/edges', data: {
        'space': space,
        'edge': edge,
        'src': src,
        'dst': dst,
        'props': props,
      });
      return true;
    } on DioException catch (e) {
      _log.warning('insertEdge failed: ${e.message}');
      return false;
    }
  }

  /// 删除边
  Future<bool> deleteEdge({
    required String space,
    required String edge,
    required String src,
    required String dst,
  }) async {
    try {
      await _dio.delete('/edges', data: {
        'space': space,
        'edge': edge,
        'src': src,
        'dst': dst,
      });
      return true;
    } on DioException catch (e) {
      _log.warning('deleteEdge failed: ${e.message}');
      return false;
    }
  }

  // ── nGQL Query ─────────────────────────────────────────

  /// 执行 nGQL 查询，返回原始数据（供图谱渲染用）
  Future<Map<String, dynamic>?> executeQuery(String space, String nGQL) async {
    try {
      final resp = await _dio.get('/query', queryParameters: {
        'space': space,
        'stmt': nGQL,
      });
      if (resp.data['ok'] == true) {
        return resp.data['data'] as Map<String, dynamic>?;
      }
      return null;
    } on DioException catch (e) {
      _log.warning('executeQuery failed: ${e.message}');
      return null;
    }
  }

  // ── CSV Import ──────────────────────────────────────────

  /// 批量导入 vertices（CSV 文件 multipart）
  Future<bool> importCsvVertices({
    required String space,
    required String tag,
    required String csvContent,
  }) async {
    try {
      final bytes = utf8.encode(csvContent);
      final formData = FormData.fromMap({
        'space': space,
        'tag': tag,
        'file': MultipartFile.fromBytes(bytes, filename: 'vertices.csv'),
      });
      await _dio.post('/import/csv/vertices', data: formData);
      return true;
    } on DioException catch (e) {
      _log.warning('importCsvVertices failed: ${e.message}');
      return false;
    }
  }

  /// 批量导入 edges（CSV 文件 multipart）
  Future<bool> importCsvEdges({
    required String space,
    required String edge,
    required String csvContent,
  }) async {
    try {
      final bytes = utf8.encode(csvContent);
      final formData = FormData.fromMap({
        'space': space,
        'edge': edge,
        'file': MultipartFile.fromBytes(bytes, filename: 'edges.csv'),
      });
      await _dio.post('/import/csv/edges', data: formData);
      return true;
    } on DioException catch (e) {
      _log.warning('importCsvEdges failed: ${e.message}');
      return false;
    }
  }

  // ── Graph Schema ───────────────────────────────────────

  /// 获取某个 space 的完整图谱数据（nodes + links），用于 ECharts 渲染
  /// 通过 nGQL 查询拼装：MATCH (a)-[r]->(b) RETURN a, r, b
  Future<GraphData> fetchGraphData(String space, {int limit = 200}) async {
    final nGQL = 'MATCH (a)-[r]->(b) '
        'RETURN a, r, b '
        'LIMIT $limit';
    final raw = await executeQuery(space, nGQL);
    if (raw == null) return GraphData(nodes: [], links: []);

    final nodes = <EChartNode>[];
    final links = <EChartLink>[];
    final seen = <String>{};

    final rows = raw['rows'] as List<dynamic>? ?? [];
    for (final row in rows) {
      final aData = row['a'] as Map<String, dynamic>?;
      final rData = row['r'] as Map<String, dynamic>?;
      final bData = row['b'] as Map<String, dynamic>?;

      if (aData != null) {
        final vid = aData['_id']?.toString() ?? aData['id']?.toString() ?? '';
        if (vid.isNotEmpty && !seen.contains('src:$vid')) {
          seen.add('src:$vid');
          nodes.add(EChartNode(
            id: vid,
            label: aData['name']?.toString() ?? aData['title']?.toString() ?? vid,
            symbolSize: 28,
            tags: [(aData['_tag']?.toString() ?? '')],
            props: Map<String, dynamic>.from(aData)..remove('_id')..remove('id'),
          ));
        }
      }

      if (bData != null) {
        final vid = bData['_id']?.toString() ?? bData['id']?.toString() ?? '';
        if (vid.isNotEmpty && !seen.contains('dst:$vid')) {
          seen.add('dst:$vid');
          nodes.add(EChartNode(
            id: vid,
            label: bData['name']?.toString() ?? bData['title']?.toString() ?? vid,
            symbolSize: 28,
            tags: [(bData['_tag']?.toString() ?? '')],
            props: Map<String, dynamic>.from(bData)..remove('_id')..remove('id'),
          ));
        }
      }

      if (aData != null && bData != null && rData != null) {
        final src = aData['_id']?.toString() ?? '';
        final dst = bData['_id']?.toString() ?? '';
        if (src.isNotEmpty && dst.isNotEmpty) {
          links.add(EChartLink(
            source: src,
            target: dst,
            label: rData['_edge']?.toString() ?? '',
          ));
        }
      }
    }

    return GraphData(nodes: nodes, links: links, space: space);
  }

  // ── Health Check ───────────────────────────────────────

  /// 检查后端服务是否在线
  Future<bool> isServerHealthy() async {
    try {
      final resp = await _dio.get(
        'http://124.223.47.167:8001/health',
        options: Options(validateStatus: (_) => true),
      );
      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}
