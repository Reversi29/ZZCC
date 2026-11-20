// lib/data/sources/feed_remote_source.dart
//
// 广场内容数据源。
// 当前为本地 Mock 数据（可稳定跑通 UI），接口抽象好，
// 后续接入真实后端时只需替换 fetchByType 的实现。

import '../models/feed_content_model.dart';

/// 广场内容数据源抽象。
abstract class FeedRemoteSource {
  /// 按类型拉取内容列表。
  Future<List<FeedContent>> fetchByType(FeedContentType type);
}

/// 本地 Mock 数据源。
///
/// 用 picsum.photos 生成稳定封面图，视频用公共测试流，
/// 音频用公共测试音频。真实后端接入后替换此实现。
class MockFeedRemoteSource implements FeedRemoteSource {
  static const _seedBase = 'https://picsum.photos/seed/zzcc';

  // 公共测试视频流（可播、免登录）
  static const _testVideos = [
    'https://flutter.github.io/assets-for-api-docs/assets/videos/bee.mp4',
    'https://flutter.github.io/assets-for-api-docs/assets/videos/butterfly.mp4',
  ];

  // 公共测试音频（可播、免登录）
  static const _testAudios = [
    'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3',
    'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3',
    'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3',
  ];

  @override
  Future<List<FeedContent>> fetchByType(FeedContentType type) async {
    // 模拟网络延迟
    await Future<void>.delayed(const Duration(milliseconds: 300));

    switch (type) {
      case FeedContentType.recommend:
        return _recommendFeed();
      case FeedContentType.video:
        return _videoFeed();
      case FeedContentType.audio:
        return _audioFeed();
      case FeedContentType.article:
        return _articleFeed();
    }
  }

  List<FeedContent> _recommendFeed() {
    const authors = ['科技前沿', '设计美学', '知识分享', '生活随记', 'AI 观察'];
    const titles = [
      'Flutter 3.41 新特性全解析：从渲染引擎到 CanvasKit',
      '六角跳棋算法设计：从网格坐标到 AI 对手',
      '类脑推理系统设计：并行脑区协调架构',
      'NebulaGraph 图数据库在知识图谱中的应用',
      '用 CustomPainter 手写知识图谱可视化',
      'SNN 脉冲神经网络：从生物启发到工程落地',
      '短视频推流服务架构：RTMP/SRT/WebRTC 选型',
      '量化交易系统回测引擎设计要点',
    ];
    const descriptions = [
      '深入剖析 Flutter 最新版本的渲染管线优化与 Web 支持改进。',
      '完整讲解六角形网格坐标系统、寻路算法与 AI 对手设计。',
      '以并行脑区协调为核心，拆解类脑推理引擎的架构设计。',
      '介绍 NebulaGraph 在知识图谱存储与查询中的实践。',
      '从零手写力导布局、LOD 裁剪与节点渲染。',
      '脉冲神经网络的结构可塑性、学习规则与工程化集成。',
      '对比多种流媒体协议的适用场景，给出选型建议。',
      '总结回测引擎的撮合、绩效与风险指标设计要点。',
    ];
    return List.generate(8, (i) {
      return FeedContent(
        id: 'rec_$i',
        type: FeedContentType.recommend,
        title: titles[i % titles.length],
        description: descriptions[i % descriptions.length],
        author: authors[i % authors.length],
        authorAvatar: '$_seedBase/av$i/200',
        coverImage: '$_seedBase/rec$i/600/400',
        likes: 120 + i * 37,
        comments: 8 + i * 3,
        shares: 2 + i,
        views: 1500 + i * 220,
        createdAt: DateTime.now().subtract(Duration(hours: i * 5 + 1)),
        tags: [titles[i % titles.length].split(' ').first],
      );
    });
  }

  List<FeedContent> _videoFeed() {
    const titles = [
      'Flutter 动画实战：Hero 与过渡效果',
      '六角跳棋对局演示',
      '知识图谱可视化导览',
      '类脑推理引擎实时推理演示',
      'SNN 脉冲网络可视化',
      '短视频推流架构演示',
    ];
    const authors = ['科技前沿', '开发者A', '设计美学', 'AI 观察'];
    return List.generate(6, (i) {
      return FeedContent(
        id: 'vid_$i',
        type: FeedContentType.video,
        title: titles[i % titles.length],
        description: '第 ${i + 1} 条短视频内容',
        author: authors[i % authors.length],
        authorAvatar: '$_seedBase/vav$i/200',
        coverImage: '$_seedBase/vid$i/600/800',
        videoUrl: _testVideos[i % _testVideos.length],
        likes: 300 + i * 55,
        comments: 15 + i * 4,
        shares: 3 + i,
        views: 5000 + i * 900,
        durationText: '00:${(10 + i * 5).toString().padLeft(2, '0')}',
        createdAt: DateTime.now().subtract(Duration(hours: i * 3 + 1)),
        tags: ['视频', '短视频'],
      );
    });
  }

  List<FeedContent> _audioFeed() {
    const titles = [
      '清晨冥想引导',
      '专注工作白噪音',
      '深夜助眠雨声',
      '咖啡馆氛围音',
      '自然森林之声',
      '轻音乐钢琴集',
    ];
    const authors = ['音律工作室', '自然之声', 'Mindfulness', 'SoundLab'];
    return List.generate(6, (i) {
      return FeedContent(
        id: 'aud_$i',
        type: FeedContentType.audio,
        title: titles[i % titles.length],
        description: '时长约 ${(3 + i).toString().padLeft(2, '0')} 分钟',
        author: authors[i % authors.length],
        authorAvatar: '$_seedBase/aav$i/200',
        coverImage: '$_seedBase/aud$i/600/600',
        audioUrl: _testAudios[i % _testAudios.length],
        audioWaveform: null,
        likes: 80 + i * 21,
        comments: 5 + i * 2,
        shares: 1 + i,
        views: 800 + i * 150,
        durationText: '${3 + i}:${(20 + i * 7).toString().padLeft(2, '0')}',
        createdAt: DateTime.now().subtract(Duration(days: i % 3, hours: i * 2)),
        tags: ['音频', '音乐'],
      );
    });
  }

  List<FeedContent> _articleFeed() {
    const authors = ['知识分享', '生活随记', 'AI 观察'];
    const titles = ['深度长文：类脑架构的哲学思考', '六角跳棋攻略大全', '量化策略回测方法论'];
    return List.generate(3, (i) {
      return FeedContent(
        id: 'art_$i',
        type: FeedContentType.article,
        title: titles[i % titles.length],
        description: '这是一篇图文长文内容，包含图片与文字排版。',
        author: authors[i % authors.length],
        authorAvatar: '$_seedBase/arav$i/200',
        coverImage: '$_seedBase/art$i/800/400',
        likes: 200 + i * 30,
        comments: 20 + i * 5,
        shares: 5 + i,
        views: 3000 + i * 400,
        createdAt: DateTime.now().subtract(Duration(days: i + 1)),
        tags: ['图文', '文章'],
      );
    });
  }
}
