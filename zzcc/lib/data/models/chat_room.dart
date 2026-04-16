// lib/data/models/chat_room.dart
//
// Chat room model for Matrix rooms.

import 'package:freezed_annotation/freezed_annotation.dart';

part 'chat_room.freezed.dart';
part 'chat_room.g.dart';

/// Chat room (Matrix room)
@freezed
class ChatRoom with _$ChatRoom {
  const factory ChatRoom({
    /// Matrix room ID (e.g., "!roomid:matrix.local")
    required String roomId,
    
    /// Room display name (optional)
    String? name,
    
    /// Room topic/description (optional)
    String? topic,
    
    /// Whether this is a direct message room
    @Default(false) bool isDirect,
    
    /// Last message preview (for room list)
    String? lastMessage,
    
    /// Last message timestamp
    int? lastMessageTimestamp,
    
    /// Unread message count
    @Default(0) int unreadCount,
  }) = _ChatRoom;

  factory ChatRoom.fromJson(Map<String, dynamic> json) =>
      _$ChatRoomFromJson(json);
  
  /// Create from Matrix API response
  factory ChatRoom.fromMatrixResponse(Map<String, dynamic> data) {
    return ChatRoom(
      roomId: data['room_id'] as String,
      name: data['name'] as String?,
      topic: data['topic'] as String?,
    );
  }
}
