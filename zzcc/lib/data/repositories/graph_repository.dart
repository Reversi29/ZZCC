// Graph Repository — 封装 NebulaGraph 数据操作
// 组合 nebula_remote_source，提供业务层友好接口

import '../models/graph_model.dart';
import '../sources/nebula_remote_source.dart';

class GraphRepository {
  final NebulaRemoteSource _remote;

  GraphRepository({NebulaRemoteSource? remote})
      : _remote = remote ?? NebulaRemoteSource();

  // ── Schema 操作 ────────────────────────────────────────

  Future<List<GraphSpace>> getSpaces() => _remote.listSpaces();

  Future<bool> createSpace({
    required String name,
    int partitionNum = 3,
    int replicaFactor = 1,
  }) =>
      _remote.createSpace(
        name: name,
        partitionNum: partitionNum,
        replicaFactor: replicaFactor,
      );

  Future<bool> dropSpace(String name) => _remote.dropSpace(name);

  Future<List<GraphTag>> getTags(String space) => _remote.listTags(space);

  Future<bool> createTag({
    required String space,
    required String tag,
    List<Map<String, String>> properties = const [],
  }) =>
      _remote.createTag(space: space, tag: tag, properties: properties);

  Future<bool> dropTag(String space, String tag) => _remote.dropTag(space, tag);

  Future<List<GraphEdgeType>> getEdgeTypes(String space) =>
      _remote.listEdgeTypes(space);

  Future<bool> createEdgeType({
    required String space,
    required String edge,
    List<Map<String, String>> properties = const [],
  }) =>
      _remote.createEdgeType(
          space: space, edge: edge, properties: properties);

  Future<bool> dropEdgeType(String space, String edge) =>
      _remote.dropEdgeType(space, edge);

  // ── Vertex/Edge 操作 ───────────────────────────────────

  Future<GraphVertex?> getVertex(String space, String vid) =>
      _remote.getVertex(space, vid);

  Future<bool> insertVertex({
    required String space,
    required String tag,
    required String vid,
    Map<String, dynamic> props = const {},
  }) =>
      _remote.insertVertex(space: space, tag: tag, vid: vid, props: props);

  Future<bool> updateVertex({
    required String space,
    required String tag,
    required String vid,
    Map<String, dynamic> props = const {},
  }) =>
      _remote.updateVertex(space: space, tag: tag, vid: vid, props: props);

  Future<bool> deleteVertex(String space, String vid,
          {bool withEdges = true}) =>
      _remote.deleteVertex(space, vid, withEdges: withEdges);

  Future<GraphEdge?> getEdge({
    required String space,
    required String edge,
    required String src,
    required String dst,
  }) =>
      _remote.getEdge(space: space, edge: edge, src: src, dst: dst);

  Future<bool> insertEdge({
    required String space,
    required String edge,
    required String src,
    required String dst,
    Map<String, dynamic> props = const {},
  }) =>
      _remote.insertEdge(
          space: space, edge: edge, src: src, dst: dst, props: props);

  Future<bool> deleteEdge({
    required String space,
    required String edge,
    required String src,
    required String dst,
  }) =>
      _remote.deleteEdge(space: space, edge: edge, src: src, dst: dst);

  // ── nGQL 查询 ──────────────────────────────────────────

  Future<Map<String, dynamic>?> query(String space, String nGQL) =>
      _remote.executeQuery(space, nGQL);

  /// 拉取图谱可视化数据（nodes + links）
  Future<GraphData> fetchGraphData(String space, {int limit = 200}) =>
      _remote.fetchGraphData(space, limit: limit);

  // ── 批量导入 ──────────────────────────────────────────

  Future<bool> importVerticesCsv({
    required String space,
    required String tag,
    required String csvContent,
  }) =>
      _remote.importCsvVertices(
          space: space, tag: tag, csvContent: csvContent);

  Future<bool> importEdgesCsv({
    required String space,
    required String edge,
    required String csvContent,
  }) =>
      _remote.importCsvEdges(space: space, edge: edge, csvContent: csvContent);

  // ── 服务状态 ──────────────────────────────────────────

  Future<bool> isHealthy() => _remote.isServerHealthy();
}
