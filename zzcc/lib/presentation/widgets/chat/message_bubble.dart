// lib/presentation/widgets/chat/message_bubble.dart
//
// Chat message bubble widget.

import 'package:flutter/material.dart';

import '../../../data/models/chat_message.dart';

/// Message bubble widget
class MessageBubble extends StatelessWidget {
  final ChatMessage message;
  final bool showSender;
  
  const MessageBubble({
    super.key,
    required this.message,
    this.showSender = true,
  });
  
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isMe = message.isMe;
    
    return Align(
      alignment: isMe ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 12),
        child: Column(
          crossAxisAlignment: isMe 
              ? CrossAxisAlignment.end 
              : CrossAxisAlignment.start,
          children: [
            // Sender name
            if (showSender && !isMe)
              Padding(
                padding: const EdgeInsets.only(left: 12, bottom: 2),
                child: Text(
                  message.senderDisplayName,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.primary,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            
            // Message bubble
            Container(
              constraints: BoxConstraints(
                maxWidth: MediaQuery.of(context).size.width * 0.75,
              ),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: BoxDecoration(
                color: isMe 
                    ? theme.colorScheme.primary 
                    : theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(20),
                  topRight: const Radius.circular(20),
                  bottomLeft: Radius.circular(isMe ? 20 : 4),
                  bottomRight: Radius.circular(isMe ? 4 : 20),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Message text
                  Text(
                    message.body,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: isMe 
                          ? theme.colorScheme.onPrimary 
                          : theme.colorScheme.onSurface,
                    ),
                  ),
                  
                  // Timestamp
                  const SizedBox(height: 4),
                  Text(
                    message.displayTime,
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontSize: 10,
                      color: isMe 
                          ? theme.colorScheme.onPrimary.withValues(alpha: 0.7) 
                          : theme.colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
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
