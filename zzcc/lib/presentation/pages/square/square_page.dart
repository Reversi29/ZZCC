import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:like_button/like_button.dart';
import 'package:intl/intl.dart';
import 'package:zzcc/presentation/pages/square/widgets/knowledge_graph_view.dart';

class Project {
  final String id;
  final String title;
  final String description;
  final String author;
  final String authorAvatar;
  final String coverImage;
  final int likes;
  final int comments;
  final int donations;
  final DateTime createdAt;
  final List<String> tags;
  final String category;

  const Project({
    required this.id,
    required this.title,
    required this.description,
    required this.author,
    required this.authorAvatar,
    required this.coverImage,
    required this.likes,
    required this.comments,
    required this.donations,
    required this.createdAt,
    required this.tags,
    required this.category,
  });
}

class SquarePage extends StatefulWidget {
  const SquarePage({super.key});

  @override
  State<SquarePage> createState() => _SquarePageState();
}

class _SquarePageState extends State<SquarePage> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final List<String> categories = [
    '知识库', '推荐', '视频', '音频', '图文', '应用', '项目', '直播'
  ];
  
  final List<Project> projects = [
    Project(
      id: '1',
      title: 'Flutter项目',
      description: '一个使用Flutter开发的跨平台应用',
      author: '开发者A',
      authorAvatar: 'https://picsum.photos/200',
      coverImage: 'https://picsum.photos/800/600',
      likes: 42,
      comments: 12,
      donations: 5,
      createdAt: DateTime.now().subtract(const Duration(days: 2)),
      tags: ['Flutter', 'Dart', '移动开发'],
      category: '项目',
    ),
    // 添加更多项目...
  ];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: categories.length, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          TabBar(
            controller: _tabController,
            tabs: categories.map((cat) => Tab(text: cat)).toList(),
            isScrollable: true,
            labelColor: Colors.blue,
            unselectedLabelColor: Colors.grey,
            indicatorSize: TabBarIndicatorSize.tab,
          ),
          Expanded(
            child: TabBarView(
              controller: _tabController,
              children: categories.map((category) {
                if (category == '知识库') {
                  return const KnowledgeGraphView();
                }
                return GridView.builder(
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2,
                  ),
                  itemCount: getProjectsByCategory(category).length,
                  itemBuilder: (context, index) {
                    return ProjectCard(
                      project: getProjectsByCategory(category)[index],
                    );
                  },
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }

  List<Project> getProjectsByCategory(String category) {
    return projects.where((p) => p.category == category).toList();
  }
}

class ProjectCard extends StatelessWidget {
  final Project project;

  const ProjectCard({super.key, required this.project});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 4,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () {
          Navigator.push(context, MaterialPageRoute(
            builder: (context) => ProjectDetailPage(project: project),
          ));
        },
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 封面图片
            ClipRRect(
              borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
              child: CachedNetworkImage(
                imageUrl: project.coverImage,
                height: 150,
                fit: BoxFit.cover,
                placeholder: (context, url) => Container(
                  color: Colors.grey[200],
                  height: 150,
                  child: const Center(child: CircularProgressIndicator()),
                ),
                errorWidget: (context, url, error) => const Icon(Icons.error),
              ),
            ),
            
            // 项目信息
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    project.title,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    project.description,
                    style: TextStyle(
                      fontSize: 14,
                      color: Colors.grey[600],
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 8),
                  
                  // 标签
                  Wrap(
                    spacing: 8,
                    runSpacing: 4,
                    children: project.tags.map((tag) => Chip(
                      label: Text(tag),
                      backgroundColor: Colors.blue[50],
                    )).toList(),
                  ),
                  const SizedBox(height: 12),
                  
                  // 作者信息
                  Row(
                    children: [
                      CircleAvatar(
                        radius: 16,
                        backgroundImage: CachedNetworkImageProvider(project.authorAvatar),
                      ),
                      const SizedBox(width: 8),
                      Text(project.author),
                      const Spacer(),
                      Text(
                        DateFormat.yMd().format(project.createdAt),
                        style: TextStyle(color: Colors.grey[600]),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  
                  // 互动按钮
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      LikeButton(
                        likeCount: project.likes,
                        countBuilder: (count, isLiked, text) {
                          return Text(
                            text,
                            style: TextStyle(
                              color: isLiked ? Colors.red : Colors.grey[600],
                              fontSize: 14,
                            ),
                          );
                        },
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ProjectDetailPage extends StatelessWidget {
  final Project project;

  const ProjectDetailPage({super.key, required this.project});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(project.title),
        actions: [
          IconButton(icon: const Icon(Icons.share), onPressed: () {}),
          IconButton(icon: const Icon(Icons.bookmark), onPressed: () {}),
        ],
      ),
      body: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 封面图片
            CachedNetworkImage(
              imageUrl: project.coverImage,
              height: 300,
              fit: BoxFit.cover,
              placeholder: (context, url) => Container(
                color: Colors.grey[200],
                height: 300,
                child: const Center(child: CircularProgressIndicator()),
              ),
              errorWidget: (context, url, error) => const Icon(Icons.error),
            ),
            
            // 项目详情
            Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      CircleAvatar(
                        radius: 24,
                        backgroundImage: CachedNetworkImageProvider(project.authorAvatar),
                      ),
                      const SizedBox(width: 16),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            project.author,
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          Text(
                            '发布于 ${DateFormat.yMd().add_jm().format(project.createdAt)}',
                            style: TextStyle(color: Colors.grey[600]),
                          ),
                        ],
                      ),
                      const Spacer(),
                      ElevatedButton.icon(
                        icon: const Icon(Icons.group_add),
                        label: const Text('加入团队'),
                        onPressed: () {},
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  
                  Text(
                    project.description,
                    style: const TextStyle(fontSize: 16, height: 1.6),
                  ),
                  const SizedBox(height: 24),
                  
                  // 标签
                  Wrap(
                    spacing: 12,
                    runSpacing: 8,
                    children: project.tags.map((tag) => Chip(
                      label: Text(tag),
                      backgroundColor: Colors.blue[50],
                    )).toList(),
                  ),
                  const SizedBox(height: 32),
                  
                  // 互动统计
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      _buildStatItem(Icons.favorite, project.likes.toString(), '点赞'),
                      _buildStatItem(Icons.comment, project.comments.toString(), '评论'),
                      _buildStatItem(Icons.attach_money, project.donations.toString(), '打赏'),
                    ],
                  ),
                  const SizedBox(height: 32),
                  
                  // 互动按钮
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      LikeButton(
                        size: 40,
                        likeCount: project.likes,
                      ),
                      IconButton(
                        icon: const Icon(Icons.comment, size: 30),
                        onPressed: () {},
                      ),
                      IconButton(
                        icon: const Icon(Icons.attach_money, size: 30),
                        onPressed: () {},
                      ),
                      IconButton(
                        icon: const Icon(Icons.share, size: 30),
                        onPressed: () {},
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  
                  // 评论区域
                  const Text(
                    '评论',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 16),
                  _buildCommentField(),
                  const SizedBox(height: 24),
                  _buildCommentList(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatItem(IconData icon, String value, String label) {
    return Column(
      children: [
        Icon(icon, color: Colors.blue, size: 32),
        const SizedBox(height: 8),
        Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
        Text(label, style: TextStyle(color: Colors.grey[600])),
      ],
    );
  }

  Widget _buildCommentField() {
    return Row(
      children: [
        const CircleAvatar(
          radius: 20,
          child: Icon(Icons.person),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: TextField(
            decoration: InputDecoration(
              hintText: '写下你的评论...',
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(24),
              ),
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              suffixIcon: IconButton(
                icon: const Icon(Icons.send),
                onPressed: () {},
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildCommentList() {
    // 模拟评论数据
    final comments = [
      {'author': '用户A', 'content': '这个项目太棒了！', 'time': '2小时前'},
      {'author': '用户B', 'content': '代码结构很清晰，学习到了很多', 'time': '5小时前'},
      {'author': '用户C', 'content': '有考虑加入XXX功能吗？', 'time': '1天前'},
    ];
    
    return Column(
      children: comments.map((comment) => Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const CircleAvatar(
              radius: 20,
              child: Icon(Icons.person),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    comment['author']!,
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 4),
                  Text(comment['content']!),
                  const SizedBox(height: 4),
                  Text(
                    comment['time']!,
                    style: TextStyle(color: Colors.grey[600], fontSize: 12),
                  ),
                ],
              ),
            ),
            IconButton(
              icon: const Icon(Icons.favorite_border, size: 18),
              onPressed: () {},
            ),
          ],
        ),
      )).toList(),
    );
  }
}