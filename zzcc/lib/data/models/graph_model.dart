// ZZCC NebulaGraph 数据模型
// 对应后端 /api/v1/* 的 Pydantic schema

class GraphSpace {
  final String name;
  final int partitionNum;
  final int replicaFactor;
  final String vidType;
  final Map<String, dynamic> extra;

  GraphSpace({
    required this.name,
    this.partitionNum = 3,
    this.replicaFactor = 1,
    this.vidType = 'FIXED_STRING(64)',
    this.extra = const {},
  });

  factory GraphSpace.fromJson(Map<String, dynamic> json) {
    return GraphSpace(
      name: json['Name']?.toString() ?? json['name']?.toString() ?? '',
      partitionNum: json['Partition Number'] ?? json['partition_num'] ?? 3,
      replicaFactor: json['Replica Factor'] ?? json['replica_factor'] ?? 1,
      vidType: json['Vid Type'] ?? json['vid_type'] ?? 'FIXED_STRING(64)',
      extra: json,
    );
  }
}

class GraphTag {
  final String name;
  final List<GraphProperty> properties;
  final Map<String, dynamic> extra;

  GraphTag({
    required this.name,
    this.properties = const [],
    this.extra = const {},
  });

  factory GraphTag.fromJson(Map<String, dynamic> json) {
    final name = json['Tag']?.toString() ?? json['name']?.toString() ?? '';
    final props = (json['Properties'] as List<dynamic>?)
            ?.map((p) => GraphProperty.fromJson(p as Map<String, dynamic>))
            .toList() ??
        (json['properties'] as List<dynamic>?)
            ?.map((p) => GraphProperty.fromJson(p as Map<String, dynamic>))
            .toList() ??
        [];
    return GraphTag(name: name, properties: props, extra: json);
  }
}

class GraphEdgeType {
  final String name;
  final List<GraphProperty> properties;
  final Map<String, dynamic> extra;

  GraphEdgeType({
    required this.name,
    this.properties = const [],
    this.extra = const {},
  });

  factory GraphEdgeType.fromJson(Map<String, dynamic> json) {
    final name = json['Edge']?.toString() ?? json['name']?.toString() ?? '';
    final props = (json['Properties'] as List<dynamic>?)
            ?.map((p) => GraphProperty.fromJson(p as Map<String, dynamic>))
            .toList() ??
        (json['properties'] as List<dynamic>?)
            ?.map((p) => GraphProperty.fromJson(p as Map<String, dynamic>))
            .toList() ??
        [];
    return GraphEdgeType(name: name, properties: props, extra: json);
  }
}

class GraphProperty {
  final String name;
  final String type;

  GraphProperty({required this.name, required this.type});

  factory GraphProperty.fromJson(Map<String, dynamic> json) {
    return GraphProperty(
      name: json['Name']?.toString() ?? json['name']?.toString() ?? '',
      type: json['Type']?.toString() ?? json['type']?.toString() ?? 'string',
    );
  }
}

// Vertex — 图谱中的节点
class GraphVertex {
  final String vid;
  final String tag;
  final Map<String, dynamic> props;

  GraphVertex({
    required this.vid,
    required this.tag,
    this.props = const {},
  });

  factory GraphVertex.fromJson(Map<String, dynamic> json) {
    return GraphVertex(
      vid: json['vid']?.toString() ?? json['_id']?.toString() ?? '',
      tag: json['tag']?.toString() ?? json['_tags']?.toString() ?? '',
      props: json['properties'] as Map<String, dynamic>? ??
          json['props'] as Map<String, dynamic>? ??
          {},
    );
  }
}

// Edge — 图谱中的边
class GraphEdge {
  final String src;
  final String dst;
  final String edge;
  final Map<String, dynamic> props;

  GraphEdge({
    required this.src,
    required this.dst,
    required this.edge,
    this.props = const {},
  });

  factory GraphEdge.fromJson(Map<String, dynamic> json) {
    return GraphEdge(
      src: json['src']?.toString() ?? json['_src']?.toString() ?? '',
      dst: json['dst']?.toString() ?? json['_dst']?.toString() ?? '',
      edge: json['edge']?.toString() ?? json['_edge']?.toString() ?? '',
      props: json['properties'] as Map<String, dynamic>? ??
          json['props'] as Map<String, dynamic>? ??
          {},
    );
  }
}

// 图谱可视化节点（传给 ECharts）
class EChartNode {
  final String id;
  final String label;
  final int category;
  final int symbolSize;
  final List<double>? xyz;
  final List<String> tags;
  final Map<String, dynamic> props;

  EChartNode({
    required this.id,
    required this.label,
    this.category = 0,
    this.symbolSize = 20,
    this.xyz,
    this.tags = const [],
    this.props = const {},
  });
}

// 图谱可视化边
class EChartLink {
  final String source;
  final String target;
  final String label;

  EChartLink({
    required this.source,
    required this.target,
    this.label = '',
  });
}

// 图谱完整数据（一次查询的全部内容）
class GraphData {
  final List<EChartNode> nodes;
  final List<EChartLink> links;
  final List<String> categories;
  final String space;

  GraphData({
    required this.nodes,
    required this.links,
    this.categories = const [],
    this.space = '',
  });
}

// API 通用响应包装
class ApiResult<T> {
  final bool ok;
  final T? data;
  final String? error;

  ApiResult({required this.ok, this.data, this.error});

  factory ApiResult.fromJson(
    Map<String, dynamic> json,
    T Function(dynamic)? fromJsonT,
  ) {
    return ApiResult(
      ok: json['ok'] == true,
      data: json['data'] != null && fromJsonT != null
          ? fromJsonT(json['data'])
          : null,
      error: json['error']?.toString(),
    );
  }
}
