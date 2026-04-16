// lib/data/models/chat_message.dart
//
// Chat message model for Matrix messages.

/// Chat message (Matrix m.room.message event)
class ChatMessage {
  /// Matrix event ID
  final String eventId;

  /// Sender user ID (e.g., "@user:matrix.local")
  final String sender;

  /// Message timestamp (origin_server_ts)
  final int timestamp;

  /// Message type (m.text, m.image, etc.)
  final String msgtype;

  /// Message body text
  final String body;

  /// Optional: formatted HTML body
  final String? formattedBody;

  /// Whether this message is from the current user
  final bool isMe;

  const ChatMessage({
    required this.eventId,
    required this.sender,
    required this.timestamp,
    this.msgtype = 'm.text',
    required this.body,
    this.formattedBody,
    this.isMe = false,
  });

  ChatMessage copyWith({
    String? eventId,
    String? sender,
    int? timestamp,
    String? msgtype,
    String? body,
    String? formattedBody,
    bool? isMe,
  }) {
    return ChatMessage(
      eventId: eventId ?? this.eventId,
      sender: sender ?? this.sender,
      timestamp: timestamp ?? this.timestamp,
      msgtype: msgtype ?? this.msgtype,
      body: body ?? this.body,
      formattedBody: formattedBody ?? this.formattedBody,
      isMe: isMe ?? this.isMe,
    );
  }

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    return ChatMessage(
      eventId: json['eventId'] as String,
      sender: json['sender'] as String,
      timestamp: json['timestamp'] as int,
      msgtype: json['msgtype'] as String? ?? 'm.text',
      body: json['body'] as String,
      formattedBody: json['formattedBody'] as String?,
      isMe: json['isMe'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'eventId': eventId,
      'sender': sender,
      'timestamp': timestamp,
      'msgtype': msgtype,
      'body': body,
      if (formattedBody != null) 'formattedBody': formattedBody,
      'isMe': isMe,
    };
  }

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

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ChatMessage &&
          runtimeType == other.runtimeType &&
          eventId == other.eventId;

  @override
  int get hashCode => eventId.hashCode;

  @override
  String toString() => 'ChatMessage(eventId: $eventId, sender: $sender, body: $body)';
}
