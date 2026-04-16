// lib/data/models/chat_room.dart
//
// Chat room model for Matrix rooms.

/// Chat room (Matrix room)
class ChatRoom {
  /// Matrix room ID (e.g., "!roomid:matrix.local")
  final String roomId;

  /// Room display name (optional)
  final String? name;

  /// Room topic/description (optional)
  final String? topic;

  /// Whether this is a direct message room
  final bool isDirect;

  /// Last message preview (for room list)
  final String? lastMessage;

  /// Last message timestamp
  final int? lastMessageTimestamp;

  /// Unread message count
  final int unreadCount;

  const ChatRoom({
    required this.roomId,
    this.name,
    this.topic,
    this.isDirect = false,
    this.lastMessage,
    this.lastMessageTimestamp,
    this.unreadCount = 0,
  });

  ChatRoom copyWith({
    String? roomId,
    String? name,
    String? topic,
    bool? isDirect,
    String? lastMessage,
    int? lastMessageTimestamp,
    int? unreadCount,
  }) {
    return ChatRoom(
      roomId: roomId ?? this.roomId,
      name: name ?? this.name,
      topic: topic ?? this.topic,
      isDirect: isDirect ?? this.isDirect,
      lastMessage: lastMessage ?? this.lastMessage,
      lastMessageTimestamp: lastMessageTimestamp ?? this.lastMessageTimestamp,
      unreadCount: unreadCount ?? this.unreadCount,
    );
  }

  factory ChatRoom.fromJson(Map<String, dynamic> json) {
    return ChatRoom(
      roomId: json['roomId'] as String,
      name: json['name'] as String?,
      topic: json['topic'] as String?,
      isDirect: json['isDirect'] as bool? ?? false,
      lastMessage: json['lastMessage'] as String?,
      lastMessageTimestamp: json['lastMessageTimestamp'] as int?,
      unreadCount: json['unreadCount'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'roomId': roomId,
      if (name != null) 'name': name,
      if (topic != null) 'topic': topic,
      'isDirect': isDirect,
      if (lastMessage != null) 'lastMessage': lastMessage,
      if (lastMessageTimestamp != null) 'lastMessageTimestamp': lastMessageTimestamp,
      'unreadCount': unreadCount,
    };
  }

  /// Create from Matrix API response
  factory ChatRoom.fromMatrixResponse(Map<String, dynamic> data) {
    return ChatRoom(
      roomId: data['room_id'] as String,
      name: data['name'] as String?,
      topic: data['topic'] as String?,
    );
  }

  /// Display name: room name, or fallback to room ID localpart
  String get displayName {
    if (name != null && name!.isNotEmpty) return name!;
    // Strip leading ! and :server part
    final match = RegExp(r'!([^:]+):').firstMatch(roomId);
    return match?.group(1) ?? roomId;
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ChatRoom &&
          runtimeType == other.runtimeType &&
          roomId == other.roomId;

  @override
  int get hashCode => roomId.hashCode;

  @override
  String toString() => 'ChatRoom(roomId: $roomId, name: $name)';
}
