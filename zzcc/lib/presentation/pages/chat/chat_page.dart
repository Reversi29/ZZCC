// lib/presentation/pages/chat/chat_page.dart
//
// Individual chat room page with message list and input.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../../data/models/chat_message.dart';
import '../../../data/models/chat_room.dart';
import '../../../data/repositories/chat_repository.dart';
import '../../widgets/chat/message_bubble.dart';

/// Chat page for a specific room
class ChatPage extends StatefulWidget {
  final ChatRepository repository;
  final ChatRoom room;
  
  const ChatPage({
    super.key,
    required this.repository,
    required this.room,
  });
  
  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final List<ChatMessage> _messages = [];
  final TextEditingController _messageController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _focusNode = FocusNode();
  
  bool _isLoading = true;
  bool _isSending = false;
  String? _error;
  StreamSubscription? _messageSubscription;
  Timer? _refreshTimer;
  
  @override
  void initState() {
    super.initState();
    _loadMessages();
    _startSync();
    
    // Periodic refresh as fallback
    _refreshTimer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => _loadMessages(silent: true),
    );
  }
  
  @override
  void dispose() {
    _messageSubscription?.cancel();
    _refreshTimer?.cancel();
    _messageController.dispose();
    _scrollController.dispose();
    _focusNode.dispose();
    super.dispose();
  }
  
  void _startSync() {
    // Listen for new messages from sync service
    // This would be connected to a global sync service in production
  }
  
  Future<void> _loadMessages({bool silent = false}) async {
    if (!silent) {
      setState(() => _isLoading = true);
    }
    
    try {
      final messages = await widget.repository.getMessages(
        widget.room.roomId,
        limit: 100,
      );
      
      if (mounted) {
        setState(() {
          _messages.clear();
          _messages.addAll(messages.reversed); // Oldest first
          _isLoading = false;
          _error = null;
        });
        
        // Scroll to bottom
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (_scrollController.hasClients) {
            _scrollController.jumpTo(
              _scrollController.position.maxScrollExtent,
            );
          }
        });
      }
    } catch (e) {
      if (mounted && !silent) {
        setState(() {
          _error = e.toString();
          _isLoading = false;
        });
      }
    }
  }
  
  Future<void> _sendMessage() async {
    final text = _messageController.text.trim();
    if (text.isEmpty) return;
    
    _messageController.clear();
    _focusNode.requestFocus();
    
    setState(() => _isSending = true);
    
    try {
      await widget.repository.sendMessage(widget.room.roomId, text);
      
      // Add optimistic message
      final optimisticMessage = ChatMessage(
        eventId: 'pending_${DateTime.now().millisecondsSinceEpoch}',
        sender: widget.repository.currentUser?.userId ?? '@me',
        timestamp: DateTime.now().millisecondsSinceEpoch,
        body: text,
        isMe: true,
      );
      
      if (mounted) {
        setState(() {
          _messages.add(optimisticMessage);
          _isSending = false;
        });
        
        // Scroll to bottom
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (_scrollController.hasClients) {
            _scrollController.animateTo(
              _scrollController.position.maxScrollExtent,
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOut,
            );
          }
        });
      }
      
      // Refresh to get real message
      await Future.delayed(const Duration(milliseconds: 500));
      await _loadMessages(silent: true);
    } catch (e) {
      if (mounted) {
        setState(() => _isSending = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to send: $e')),
        );
      }
    }
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.room.name ?? 'Unnamed Room',
              style: const TextStyle(fontSize: 16),
            ),
            if (widget.room.topic != null)
              Text(
                widget.room.topic!,
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.normal),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => _loadMessages(),
          ),
          PopupMenuButton<String>(
            onSelected: (value) async {
              if (value == 'leave') {
                final navigator = Navigator.of(context);
                final messenger = ScaffoldMessenger.of(context);
                final confirm = await showDialog<bool>(
                  context: context,
                  builder: (ctx) => AlertDialog(
                    title: const Text('Leave Room?'),
                    content: const Text('You will need to be re-invited to rejoin.'),
                    actions: [
                      TextButton(
                        onPressed: () => Navigator.pop(ctx, false),
                        child: const Text('Cancel'),
                      ),
                      FilledButton(
                        onPressed: () => Navigator.pop(ctx, true),
                        child: const Text('Leave'),
                      ),
                    ],
                  ),
                );
                
                if (confirm == true) {
                  try {
                    await widget.repository.leaveRoom(widget.room.roomId);
                    if (mounted) navigator.pop();
                  } catch (e) {
                    if (mounted) {
                      messenger.showSnackBar(
                        SnackBar(content: Text('Failed to leave: $e')),
                      );
                    }
                  }
                }
              }
            },
            itemBuilder: (context) => [
              const PopupMenuItem(
                value: 'leave',
                child: Row(
                  children: [
                    Icon(Icons.exit_to_app, color: Colors.red),
                    SizedBox(width: 8),
                    Text('Leave Room', style: TextStyle(color: Colors.red)),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
      body: Column(
        children: [
          // Messages list
          Expanded(child: _buildMessageList()),
          
          // Input area
          _buildInputArea(),
        ],
      ),
    );
  }
  
  Widget _buildMessageList() {
    if (_isLoading && _messages.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    
    if (_error != null && _messages.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('Error: $_error'),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () => _loadMessages(),
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }
    
    if (_messages.isEmpty) {
      return const Center(
        child: Text(
          'No messages yet\nSend the first message!',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.grey),
        ),
      );
    }
    
    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: _messages.length,
      itemBuilder: (context, index) {
        final message = _messages[index];
        final showSender = index == 0 || 
            _messages[index - 1].sender != message.sender;
        
        return MessageBubble(
          message: message,
          showSender: showSender,
        );
      },
    );
  }
  
  Widget _buildInputArea() {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          border: Border(
            top: BorderSide(
              color: Theme.of(context).colorScheme.outline.withValues(alpha: 0.2),
            ),
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _messageController,
                focusNode: _focusNode,
                decoration: InputDecoration(
                  hintText: 'Type a message...',
                  filled: true,
                  fillColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24),
                    borderSide: BorderSide.none,
                  ),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 12,
                  ),
                ),
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _sendMessage(),
                maxLines: null,
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              onPressed: _isSending ? null : _sendMessage,
              icon: _isSending
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.send),
            ),
          ],
        ),
      ),
    );
  }
}
