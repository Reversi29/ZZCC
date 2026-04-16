// lib/data/models/chat_message.dart
//
// Chat message model for Matrix messages.

import 'package:freezed_annotation/freezed_annotation.dart';

part 'chat_message.freezed.dart';
part 'chat_message.g.dart';

/// Chat message (Matrix m.room.message event)
@freezed
class ChatMessage with _$ChatMessage {
  const factory ChatMessage({
    /// Matrix event ID
    required String eventId,
    
    /// Sender user ID (e.g., "@user:matrix.local")
    required String sender,
    
    /// Message timestamp (origin_server_ts)
    required int timestamp,
    
    /// Message type (m.text, m.image, etc.)
    @Default('m.text') String msgtype,
    
    /// Message body text
    required String body,
    
    /// Optional: formatted HTML body
    String? formattedBody,
    
    /// Whether this message is from the current user
    @Default(false) bool isMe,
  }) = _ChatMessage;

  factory ChatMessage.fromJson(Map<String, dynamic> json) =>
      _$ChatMessageFromJson(json);
  
  /// Create from Matrix API response
  factory ChatMessage.fromMatrixResponse(Map<String, dynamic> data) {
    return ChatMessage(
      eventId: data['event_id'] as String,
      sender: data['sender'] as String,
      timestamp: data['timestamp'] as int,
      msgtype: data['msgtype'] as String? ?? 'm.text',
      body: data['body'] as String,
    );
  }
  
  /// Get display time string
  String get displayTime {
    final dt = DateTime.fromMillisecondsSinceEpoch(timestamp);
    final now = DateTime.now();
    
    if (dt.year == now.year && dt.month == now.month && dt.day == now.day) {
      // Today: show time only
      return '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } else if (dt.year == now.year) {
      // This year: show month/day
      return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } else {
      // Different year
      return '${dt.year}/${dt.month}/${dt.day}';
    }
  }
  
  /// Get sender display name (localpart)
  String get senderDisplayName {
    final match = RegExp(r'@([^:]+):').firstMatch(sender);
    return match?.group(1) ?? sender;
  }
}
