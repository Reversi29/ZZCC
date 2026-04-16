// lib/presentation/pages/chat/rooms_page.dart
//
// Chat rooms list page.

import 'package:flutter/material.dart';

import '../../../data/models/chat_room.dart';
import '../../../data/repositories/chat_repository.dart';
import '../../widgets/chat/room_tile.dart';
import 'chat_page.dart';

/// Rooms list page
class RoomsPage extends StatefulWidget {
  final ChatRepository repository;
  
  const RoomsPage({
    super.key,
    required this.repository,
  });
  
  @override
  State<RoomsPage> createState() => _RoomsPageState();
}

class _RoomsPageState extends State<RoomsPage> {
  List<ChatRoom> _rooms = [];
  bool _isLoading = true;
  String? _error;
  
  @override
  void initState() {
    super.initState();
    _loadRooms();
  }
  
  Future<void> _loadRooms() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    
    try {
      final rooms = await widget.repository.getRooms();
      if (mounted) {
        setState(() {
          _rooms = rooms;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _isLoading = false;
        });
      }
    }
  }
  
  Future<void> _createRoom() async {
    final nameController = TextEditingController();
    final topicController = TextEditingController();
    
    final result = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Create Room'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameController,
              decoration: const InputDecoration(
                labelText: 'Room Name',
                hintText: 'Enter room name',
              ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: topicController,
              decoration: const InputDecoration(
                labelText: 'Topic (optional)',
                hintText: 'Enter room topic',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Create'),
          ),
        ],
      ),
    );
    
    if (result == true && nameController.text.isNotEmpty) {
      try {
        final room = await widget.repository.createRoom(
          name: nameController.text,
          topic: topicController.text.isNotEmpty ? topicController.text : null,
        );
        
        if (mounted) {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => ChatPage(
                repository: widget.repository,
                room: room,
              ),
            ),
          );
          _loadRooms(); // Refresh list
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Failed to create room: $e')),
          );
        }
      }
    }
  }
  
  Future<void> _joinRoom() async {
    final controller = TextEditingController();
    
    final result = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Join Room'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(
            labelText: 'Room ID or Alias',
            hintText: '!roomid:server or #alias:server',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Join'),
          ),
        ],
      ),
    );
    
    if (result == true && controller.text.isNotEmpty) {
      try {
        final room = await widget.repository.joinRoom(controller.text);
        
        if (mounted) {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => ChatPage(
                repository: widget.repository,
                room: room,
              ),
            ),
          );
          _loadRooms();
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Failed to join room: $e')),
          );
        }
      }
    }
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Chat'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadRooms,
          ),
        ],
      ),
      body: _buildBody(),
      floatingActionButton: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          FloatingActionButton.small(
            heroTag: 'join',
            onPressed: _joinRoom,
            child: const Icon(Icons.login),
          ),
          const SizedBox(height: 8),
          FloatingActionButton(
            heroTag: 'create',
            onPressed: _createRoom,
            child: const Icon(Icons.add),
          ),
        ],
      ),
    );
  }
  
  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('Error: $_error'),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _loadRooms,
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }
    
    if (_rooms.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.chat_bubble_outline, size: 64, color: Colors.grey),
            const SizedBox(height: 16),
            const Text(
              'No rooms yet',
              style: TextStyle(fontSize: 18, color: Colors.grey),
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: _createRoom,
              icon: const Icon(Icons.add),
              label: const Text('Create Room'),
            ),
          ],
        ),
      );
    }
    
    return RefreshIndicator(
      onRefresh: _loadRooms,
      child: ListView.builder(
        itemCount: _rooms.length,
        itemBuilder: (context, index) {
          final room = _rooms[index];
          return RoomTile(
            room: room,
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => ChatPage(
                  repository: widget.repository,
                  room: room,
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
