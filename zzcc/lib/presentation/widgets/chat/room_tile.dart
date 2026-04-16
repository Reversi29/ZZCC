// lib/presentation/widgets/chat/room_tile.dart
//
// Chat room list tile widget.

import 'package:flutter/material.dart';

import '../../../data/models/chat_room.dart';

/// Room list tile widget
class RoomTile extends StatelessWidget {
  final ChatRoom room;
  final VoidCallback? onTap;
  
  const RoomTile({
    super.key,
    required this.room,
    this.onTap,
  });
  
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final displayName = room.name ?? 'Unnamed Room';
    
    return ListTile(
      onTap: onTap,
      leading: CircleAvatar(
        backgroundColor: theme.colorScheme.primaryContainer,
        child: Text(
          displayName.isNotEmpty ? displayName[0].toUpperCase() : '?',
          style: TextStyle(
            color: theme.colorScheme.onPrimaryContainer,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      title: Text(
        displayName,
        style: theme.textTheme.bodyLarge?.copyWith(
          fontWeight: room.unreadCount > 0 ? FontWeight.bold : FontWeight.normal,
        ),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: room.topic != null && room.topic!.isNotEmpty
          ? Text(
              room.topic!,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall,
            )
          : room.lastMessage != null
              ? Text(
                  room.lastMessage!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodySmall,
                )
              : null,
      trailing: room.unreadCount > 0
          ? Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: theme.colorScheme.primary,
                shape: BoxShape.circle,
              ),
              child: Text(
                room.unreadCount.toString(),
                style: TextStyle(
                  color: theme.colorScheme.onPrimary,
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                ),
              ),
            )
          : null,
    );
  }
}
