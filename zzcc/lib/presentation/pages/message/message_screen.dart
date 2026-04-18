// lib/presentation/pages/message/message_screen.dart
//
// Real chat integration — replaces fake data with ChatRepository.

import 'dart:async';
import 'package:logging/logging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/routes/route_names.dart';
import 'package:zzcc/data/models/chat_room.dart';
import 'package:zzcc/data/repositories/chat_repository.dart';
import 'package:zzcc/presentation/pages/chat/chat_page.dart';

class MessageScreen extends ConsumerStatefulWidget {
  const MessageScreen({super.key});

  @override
  ConsumerState<MessageScreen> createState() => _MessageScreenState();
}

class _MessageScreenState extends ConsumerState<MessageScreen>
    with TickerProviderStateMixin {
  late TabController _tabController;
  bool _showContacts = true;
  double _sidebarWidth = 250;
  final TextEditingController _searchController = TextEditingController();

  // Chat state
  ChatRepository get _chatRepo => getIt<ChatRepository>();
  List<ChatRoom> _rooms = [];
  List<ChatRoom> _directRooms = [];
  List<ChatRoom> _groupRooms = [];
  bool _roomsLoading = true;
  String? _roomsError;
  ChatRoom? _selectedRoom;
  String _searchQuery = '';

  StreamSubscription<bool>? _authSubscription;
  final _log = Logger('MessageScreen');

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _tabController.addListener(() {
      if (_tabController.indexIsChanging) return;
      if (_tabController.index != _activeTabIndex) {
        setState(() => _activeTabIndex = _tabController.index);
      }
    });

    // Listen auth state: on login → load rooms; on logout → clear rooms
    _authSubscription = _chatRepo.authStateStream.listen((isAuth) {
      if (!mounted) return;
      if (isAuth) {
        _loadRooms();
      } else {
        setState(() {
          _rooms = [];
          _directRooms = [];
          _groupRooms = [];
          _selectedRoom = null;
          _roomsLoading = false;
        });
      }
    });

    // Init: load if already auth
    final isLoggedIn = _chatRepo.isAuthenticated;
    if (isLoggedIn) {
      _loadRooms();
    } else {
      setState(() => _roomsLoading = false);
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Auth guard — if auth changed from another screen, refresh
    if (_chatRepo.isAuthenticated && _roomsLoading && _roomsError == null) {
      _loadRooms();
    }
  }

  @override
  void dispose() {
    _authSubscription?.cancel();
    _tabController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadRooms() async {
    if (!mounted) return;
    final isAuth = _chatRepo.isAuthenticated;
    _log.fine('_loadRooms: isAuthenticated=$isAuth, needsSync=${_chatRepo.currentUser?.needsSync}');
    if (!isAuth) return;
    setState(() {
      _roomsLoading = true;
      _roomsError = null;
    });
    try {
      final rooms = await _chatRepo.getRooms();
      if (mounted) {
        setState(() {
          _rooms = rooms;
          _directRooms = rooms.where((r) => r.isDirect).toList();
          _groupRooms = rooms.where((r) => !r.isDirect).toList();
          _roomsLoading = false;
        });
      }
    } catch (e) {
      _log.warning('_loadRooms failed: $e');
      if (mounted) {
        setState(() {
          _roomsError = e.toString();
          _roomsLoading = false;
        });
      }
    }
  }

  Future<void> _logout() async {
    await _chatRepo.logout();
    if (mounted) {
      context.go('${RouteNames.root}${RouteNames.login}');
    }
  }

  void _selectRoom(ChatRoom room) {
    setState(() => _selectedRoom = room);
  }

  void _closeChat() {
    setState(() => _selectedRoom = null);
  }

  Future<void> _createRoom() async {
    final nameController = TextEditingController();
    final topicController = TextEditingController();

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('创建房间'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameController,
              decoration: const InputDecoration(
                labelText: '房间名称',
                hintText: '输入房间名称',
              ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: topicController,
              decoration: const InputDecoration(
                labelText: '主题（可选）',
                hintText: '输入房间主题',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('创建'),
          ),
        ],
      ),
    );

    if (result == true && nameController.text.isNotEmpty && mounted) {
      try {
        final room = await _chatRepo.createRoom(
          name: nameController.text,
          topic: topicController.text.isNotEmpty ? topicController.text : null,
        );
        await _loadRooms();
        _selectRoom(room);
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('创建失败: $e')),
          );
        }
      }
    }
  }

  Future<void> _joinRoom() async {
    final controller = TextEditingController();

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('加入房间'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(
            labelText: '房间 ID 或别名',
            hintText: '!roomid:server 或 #alias:server',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('加入'),
          ),
        ],
      ),
    );

    if (result == true && controller.text.isNotEmpty && mounted) {
      try {
        final room = await _chatRepo.joinRoom(controller.text);
        await _loadRooms();
        _selectRoom(room);
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('加入失败: $e')),
          );
        }
      }
    }
  }

  // ── Sidebar content ──────────────────────────────────────────

  int _activeTabIndex = 0;

  Widget _buildSidebarContent() {
    switch (_activeTabIndex) {
      case 0:
        return _buildChatTab();
      case 1:
        return _buildContactsTab();
      case 2:
        return _buildGroupsTab();
      default:
        return const SizedBox();
    }
  }

  Widget _buildChatTab() {
    if (!_chatRepo.isAuthenticated) {
      // Distinguish: completely logged out vs. offline-but-logged-in (needsSync)
      final needsSync = _chatRepo.currentUser?.needsSync ?? false;
      if (needsSync) {
        return Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.cloud_off, size: 48, color: Colors.orange),
              const SizedBox(height: 12),
              const Text('离线账号', style: TextStyle(color: Colors.orange, fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              const Text('密码未保存，请重新登录以同步', style: TextStyle(color: Colors.grey)),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: () => context.go('${RouteNames.root}${RouteNames.login}'),
                child: const Text('重新登录'),
              ),
            ],
          ),
        );
      }
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.lock_outline, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            const Text('请先登录', style: TextStyle(color: Colors.grey)),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: () => context.go('${RouteNames.root}${RouteNames.login}'),
              child: const Text('登录 / 注册'),
            ),
          ],
        ),
      );
    }
    if (_roomsLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_roomsError != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('加载失败', style: const TextStyle(color: Colors.red)),
            const SizedBox(height: 8),
            Text(_roomsError!, style: const TextStyle(fontSize: 12)),
            const SizedBox(height: 8),
            FilledButton(onPressed: _loadRooms, child: const Text('重试')),
          ],
        ),
      );
    }
    if (_rooms.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.chat_bubble_outline, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            const Text('暂无房间', style: TextStyle(color: Colors.grey)),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _createRoom,
              icon: const Icon(Icons.add),
              label: const Text('创建房间'),
            ),
          ],
        ),
      );
    }

    final filtered = _searchQuery.isEmpty
        ? _rooms
        : _rooms.where((r) {
            final q = _searchQuery.toLowerCase();
            return (r.name?.toLowerCase().contains(q) ?? false) ||
                r.roomId.toLowerCase().contains(q);
          }).toList();

    return Column(
      children: [
        Row(
          children: [
            IconButton(
              icon: const Icon(Icons.login, size: 20),
              tooltip: '加入房间',
              onPressed: _joinRoom,
            ),
            IconButton(
              icon: const Icon(Icons.add, size: 20),
              tooltip: '创建房间',
              onPressed: _createRoom,
            ),
            IconButton(
              icon: const Icon(Icons.refresh, size: 20),
              tooltip: '刷新',
              onPressed: _loadRooms,
            ),
          ],
        ),
        const Divider(height: 1),
        Expanded(
          child: filtered.isEmpty
              ? const Center(
                  child: Text('无匹配房间', style: TextStyle(color: Colors.grey)),
                )
              : ListView.builder(
                  itemCount: filtered.length,
                  itemBuilder: (context, index) {
                    final room = filtered[index];
                    final isSelected = _selectedRoom?.roomId == room.roomId;
                    return ListTile(
                      selected: isSelected,
                      selectedTileColor:
                          Theme.of(context).primaryColor.withValues(alpha: 0.1),
                      leading: CircleAvatar(
                        backgroundColor: Theme.of(context).primaryColor,
                        child: Text(
                          (room.name ?? room.roomId)
                              .substring(0, 1)
                              .toUpperCase(),
                          style: const TextStyle(color: Colors.white),
                        ),
                      ),
                      title: Text(room.name ?? room.roomId,
                          maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: Text(
                        room.topic ?? room.lastMessage ?? '',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12),
                      ),
                      trailing: room.unreadCount > 0
                          ? CircleAvatar(
                              radius: 10,
                              backgroundColor: Colors.red,
                              child: Text(
                                '${room.unreadCount}',
                                style: const TextStyle(
                                    color: Colors.white, fontSize: 10),
                              ),
                            )
                          : null,
                      onTap: () => _selectRoom(room),
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _buildContactsTab() {
    if (!_chatRepo.isAuthenticated) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.lock_outline, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            const Text('请先登录', style: TextStyle(color: Colors.grey)),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: () => context.go('${RouteNames.root}${RouteNames.login}'),
              child: const Text('登录 / 注册'),
            ),
          ],
        ),
      );
    }
    if (_roomsLoading) return const Center(child: CircularProgressIndicator());

    final filtered = _searchQuery.isEmpty
        ? _directRooms
        : _directRooms
            .where((r) =>
                (r.name?.toLowerCase().contains(_searchQuery.toLowerCase()) ??
                    false) ||
                r.roomId.toLowerCase().contains(_searchQuery.toLowerCase()))
            .toList();

    if (filtered.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.person_outline, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            const Text('暂无联系人', style: TextStyle(color: Colors.grey)),
            const SizedBox(height: 8),
            const Text('发起私聊即可添加联系人',
                style: TextStyle(fontSize: 12, color: Colors.grey)),
          ],
        ),
      );
    }

    return ListView.builder(
      itemCount: filtered.length,
      itemBuilder: (context, index) {
        final room = filtered[index];
        return ListTile(
          leading: CircleAvatar(
            backgroundColor: Theme.of(context).primaryColor,
            child: Text(
              (room.name ?? '?').substring(0, 1).toUpperCase(),
              style: const TextStyle(color: Colors.white),
            ),
          ),
          title: Text(room.name ?? room.roomId,
              maxLines: 1, overflow: TextOverflow.ellipsis),
          subtitle: Text(room.lastMessage ?? '',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 12)),
          onTap: () => _selectRoom(room),
        );
      },
    );
  }

  Widget _buildGroupsTab() {
    if (!_chatRepo.isAuthenticated) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.lock_outline, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            const Text('请先登录', style: TextStyle(color: Colors.grey)),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: () => context.go('${RouteNames.root}${RouteNames.login}'),
              child: const Text('登录 / 注册'),
            ),
          ],
        ),
      );
    }
    if (_roomsLoading) return const Center(child: CircularProgressIndicator());

    final filtered = _searchQuery.isEmpty
        ? _groupRooms
        : _groupRooms
            .where((r) =>
                (r.name?.toLowerCase().contains(_searchQuery.toLowerCase()) ??
                    false) ||
                r.roomId.toLowerCase().contains(_searchQuery.toLowerCase()))
            .toList();

    if (filtered.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.group_outlined, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            const Text('暂无群组', style: TextStyle(color: Colors.grey)),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _createRoom,
              icon: const Icon(Icons.add),
              label: const Text('创建群组'),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      itemCount: filtered.length,
      itemBuilder: (context, index) {
        final room = filtered[index];
        return ListTile(
          leading: const CircleAvatar(
            backgroundColor: Colors.blue,
            child: Icon(Icons.group, color: Colors.white),
          ),
          title: Text(room.name ?? room.roomId,
              maxLines: 1, overflow: TextOverflow.ellipsis),
          subtitle: Text(room.topic ?? room.lastMessage ?? '',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 12)),
          trailing: room.unreadCount > 0
              ? CircleAvatar(
                  radius: 10,
                  backgroundColor: Colors.red,
                  child: Text('${room.unreadCount}',
                      style: const TextStyle(color: Colors.white, fontSize: 10)),
                )
              : null,
          onTap: () => _selectRoom(room),
        );
      },
    );
  }

  // ── Main build ───────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final isAuth = _chatRepo.isAuthenticated;
    return Scaffold(
      appBar: AppBar(
        title: Text(_selectedRoom?.name ?? '消息'),
        leading: IconButton(
          icon: Icon(_showContacts ? Icons.chevron_left : Icons.chevron_right),
          onPressed: () => setState(() => _showContacts = !_showContacts),
        ),
        automaticallyImplyLeading: false,
        actions: [
          if (_selectedRoom != null)
            IconButton(
              icon: const Icon(Icons.arrow_back),
              onPressed: _closeChat,
            ),
          if (isAuth)
            IconButton(
              icon: const Icon(Icons.logout),
              tooltip: '退出登录',
              onPressed: () async {
                final confirm = await showDialog<bool>(
                  context: context,
                  builder: (ctx) => AlertDialog(
                    title: const Text('退出登录'),
                    content: const Text('确定退出聊天账号？'),
                    actions: [
                      TextButton(
                        onPressed: () => Navigator.pop(ctx, false),
                        child: const Text('取消'),
                      ),
                      FilledButton(
                        onPressed: () => Navigator.pop(ctx, true),
                        child: const Text('退出'),
                      ),
                    ],
                  ),
                );
                if (confirm == true) await _logout();
              },
            ),
          IconButton(icon: const Icon(Icons.videocam), onPressed: () {}),
          IconButton(icon: const Icon(Icons.phone), onPressed: () {}),
        ],
      ),
      body: Row(
        children: [
          // Left sidebar
          if (_showContacts) ...[
            SizedBox(
              width: _sidebarWidth,
              child: Column(
                children: [
                  // Search
                  Padding(
                    padding: const EdgeInsets.all(8.0),
                    child: TextField(
                      controller: _searchController,
                      decoration: InputDecoration(
                        hintText: '搜索',
                        prefixIcon: const Icon(Icons.search),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 8,
                        ),
                      ),
                      onChanged: (v) => setState(() => _searchQuery = v),
                    ),
                  ),
                  // Tabs
                  TabBar(
                    controller: _tabController,
                    tabs: const [
                      Tab(icon: Icon(Icons.chat, size: 20)),
                      Tab(icon: Icon(Icons.contacts, size: 20)),
                      Tab(icon: Icon(Icons.group, size: 20)),
                    ],
                    labelColor: Theme.of(context).primaryColor,
                    unselectedLabelColor: Colors.grey,
                    indicatorSize: TabBarIndicatorSize.tab,
                  ),
                  // Tab content
                  Expanded(child: _buildSidebarContent()),
                ],
              ),
            ),
            // Resize handle
            GestureDetector(
              onHorizontalDragUpdate: (d) {
                setState(() {
                  _sidebarWidth += d.delta.dx;
                  _sidebarWidth = _sidebarWidth.clamp(150.0, 350.0);
                });
              },
              child: MouseRegion(
                cursor: SystemMouseCursors.resizeLeftRight,
                child: Container(width: 6, color: Colors.grey[300]),
              ),
            ),
          ],
          // Right content
          Expanded(
            child: _selectedRoom == null
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.forum, size: 64, color: Colors.grey[400]),
                        const SizedBox(height: 16),
                        Text(
                          _activeTabIndex == 0
                              ? '选择聊天开始'
                              : _activeTabIndex == 1
                                  ? '选择联系人开始聊天'
                                  : '选择群组开始聊天',
                          style: TextStyle(
                            color: Colors.grey[500],
                            fontSize: 16,
                          ),
                        ),
                      ],
                    ),
                  )
                : ChatPage(
                    repository: _chatRepo,
                    room: _selectedRoom!,
                  ),
          ),
        ],
      ),
    );
  }
}
