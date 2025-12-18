import 'package:flutter/material.dart';
import 'package:zzcc/data/models/message_model.dart';
import 'package:zzcc/presentation/widgets/alphabet_index.dart';

class MessageScreen extends StatefulWidget {
  const MessageScreen({super.key});

  @override
  State<MessageScreen> createState() => _MessageScreenState();
}

class _MessageScreenState extends State<MessageScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController; // 添加 TabController
  bool _showContacts = true;
  double _sidebarWidth = 250;
  final TextEditingController _controller = TextEditingController();
  int _activeTabIndex = 0; // 0: 消息, 1: 联系人, 2: 群组
  String _searchQuery = '';
  List<ContactGroup> contactGroups = [
    ContactGroup(name: '家人', contacts: [
      Contact(name: '张三', lastMessage: '晚上回家吃饭吗？', time: '昨天'),
      Contact(name: '李四', lastMessage: '周末一起去公园', time: '2小时前'),
    ]),
    ContactGroup(name: '工作', contacts: [
      Contact(name: '王经理', lastMessage: '项目进度如何？', time: '今天'),
      Contact(name: '刘总监', lastMessage: '会议改到明天下午', time: '昨天'),
    ]),
    ContactGroup(name: '朋友', contacts: [
      Contact(name: '赵六', lastMessage: '生日聚会别忘了', time: '3天前'),
      Contact(name: '钱七', lastMessage: '新开的餐厅不错', time: '周一'),
    ]),
  ];
  
  final List<Message> messages = [
    const Message(text: "你好！今天有空吗？", isMe: false, time: "10:30 AM"),
    const Message(text: "有的，有什么事吗？", isMe: true, time: "10:32 AM"),
    const Message(text: "想讨论一下项目进度", isMe: false, time: "10:33 AM"),
    const Message(text: "好的，什么时候见面？", isMe: true, time: "10:35 AM"),
  ];

  @override
  void initState() {
    super.initState();
    // 初始化 TabController
    _tabController = TabController(
      length: 3, // 三个标签页
      vsync: this, // 使用 SingleTickerProviderStateMixin
    );
    
    // 添加监听器，当标签切换时更新状态
    // Only update state when the index is actually changing or when the
    // final index has settled. Avoid calling setState on every animation
    // tick to prevent UI jank/freezes.
    _tabController.addListener(() {
      if (_tabController.indexIsChanging) {
        setState(() {
          _activeTabIndex = _tabController.index;
        });
      } else if (_tabController.index != _activeTabIndex) {
        // handle the case when the animation finished but index changed
        setState(() {
          _activeTabIndex = _tabController.index;
        });
      }
    });
  }

  @override
  void dispose() {
    // 释放 TabController
    _tabController.dispose();
    // 释放文本控制器
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("消息"),
        leading: IconButton(
          icon: Icon(_showContacts ? Icons.chevron_left : Icons.chevron_right),
          onPressed: () => setState(() => _showContacts = !_showContacts),
        ),
        actions: [
          IconButton(icon: const Icon(Icons.videocam), onPressed: () {}),
          IconButton(icon: const Icon(Icons.phone), onPressed: () {}),
        ],
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          return Row(
            children: [
              if (_showContacts) ...[
                SizedBox(
                  width: _sidebarWidth,
                  child: Column(
                    children: [
                      // 搜索框
                      Padding(
                        padding: const EdgeInsets.all(8.0),
                        child: TextField(
                          decoration: InputDecoration(
                            hintText: '搜索联系人或消息',
                            prefixIcon: const Icon(Icons.search),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                          ),
                          onChanged: (value) {
                            setState(() {
                              _searchQuery = value;
                            });
                          },
                        ),
                      ),
                      
                      // 标签栏 - 使用 TabController
                      TabBar(
                        controller: _tabController, // 添加控制器
                        tabs: const [
                          Tab(icon: Icon(Icons.chat), text: '消息'),
                          Tab(icon: Icon(Icons.contacts), text: '联系人'),
                          Tab(icon: Icon(Icons.group), text: '群组'),
                        ],
                        labelColor: Theme.of(context).primaryColor,
                        unselectedLabelColor: Colors.grey,
                        indicatorSize: TabBarIndicatorSize.tab,
                      ),
                      
                      // 标签内容
                      Expanded(
                        child: _buildSidebarContent(),
                      ),
                    ],
                  ),
                ),
                GestureDetector(
                  onHorizontalDragUpdate: (details) {
                    setState(() {
                      _sidebarWidth += details.delta.dx;
                      _sidebarWidth = _sidebarWidth.clamp(150.0, 350.0);
                    });
                  },
                  child: MouseRegion(
                    cursor: SystemMouseCursors.resizeLeftRight,
                    child: Container(
                      width: 6,
                      color: Colors.grey[300],
                    ),
                  ),
                ),
              ],
              Expanded(
                child: Column(
                  children: [
                    Expanded(
                      child: ListView.builder(
                        reverse: true,
                        itemCount: messages.length,
                        itemBuilder: (context, index) {
                          final message = messages[index];
                          return MessageBubble(
                            message: message,
                            isMe: message.isMe,
                          );
                        },
                      ),
                    ),
                    _buildInputField(),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildSidebarContent() {
    switch (_activeTabIndex) {
      case 0: // 消息
        return ListView.builder(
          itemCount: 10,
          itemBuilder: (context, index) {
            return ListTile(
              leading: const CircleAvatar(
                backgroundImage: NetworkImage('https://picsum.photos/200'),
              ),
              title: Text('联系人 ${index + 1}'),
              subtitle: const Text('最后一条消息...'),
              trailing: const Text('昨天'),
              onTap: () {},
            );
          },
        );
      case 1: // 联系人
        return _buildContactsTab();
      case 2: // 群组
        return ListView.builder(
          itemCount: 5,
          itemBuilder: (context, index) {
            return ListTile(
              leading: const CircleAvatar(
                backgroundColor: Colors.blue,
                child: Icon(Icons.group, color: Colors.white),
              ),
              title: Text('群聊 ${index + 1}'),
              subtitle: const Text('最后一条群消息...'),
              trailing: const Text('今天'),
              onTap: () {},
            );
          },
        );
      default:
        return Container();
    }
  }

  Widget _buildContactsTab() {
    final filteredGroups = _searchQuery.isEmpty
        ? contactGroups
        : contactGroups.map((group) {
            final filteredContacts = group.contacts
                .where((contact) =>
                    contact.name.toLowerCase().contains(_searchQuery.toLowerCase()))
                .toList();
            return ContactGroup(
              name: group.name,
              contacts: filteredContacts,
            );
          }).where((group) => group.contacts.isNotEmpty).toList();

    if (filteredGroups.isEmpty) {
      return const Center(child: Text('没有找到联系人'));
    }

    return Column(
      children: [
        // 添加分组按钮
        ListTile(
          leading: const Icon(Icons.add),
          title: const Text('添加新分组'),
          onTap: _showAddGroupDialog,
        ),
        const Divider(),
        Expanded(
          child: AlphabetIndexListView(
            groups: filteredGroups,
            onAddGroup: _showAddGroupDialog,
          ),
        ),
      ],
    );
  }

  void _showAddGroupDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('新建分组'),
        content: const TextField(
          decoration: InputDecoration(
            labelText: '分组名称',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          ElevatedButton(
            onPressed: () {
              // 这里添加创建新分组的逻辑
              Navigator.pop(context);
            },
            child: const Text('创建'),
          ),
        ],
      ),
    );
  }

  Widget _buildInputField() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: Colors.grey.shade300)),
      ),
      child: Row(
        children: [
          IconButton(
            icon: const Icon(Icons.add),
            onPressed: () {},
          ),
          Expanded(
            child: TextField(
              controller: _controller,
              decoration: const InputDecoration(
                hintText: "输入消息...",
                border: InputBorder.none,
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.send),
            onPressed: () {
              if (_controller.text.isNotEmpty) {
                setState(() {
                  messages.insert(0, Message(
                    text: _controller.text,
                    isMe: true,
                    time: "刚刚"
                  ));
                  _controller.clear();
                });
              }
            },
          ),
        ],
      ),
    );
  }
}

class Message {
  final String text;
  final bool isMe;
  final String time;

  const Message({
    required this.text,
    required this.isMe,
    required this.time,
  });
}

class MessageBubble extends StatelessWidget {
  final Message message;
  final bool isMe;

  const MessageBubble({
    super.key,
    required this.message,
    required this.isMe,
  });

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: isMe ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.7,
        ),
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isMe ? Theme.of(context).primaryColor : Colors.grey[200],
          borderRadius: BorderRadius.circular(18),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              message.text,
              style: TextStyle(
                color: isMe ? Colors.white : Colors.black,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              message.time,
              style: TextStyle(
                color: isMe ? Colors.white70 : Colors.grey[600],
                fontSize: 10,
              ),
            ),
          ],
        ),
      ),
    );
  }
}