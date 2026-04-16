// lib/data/models/chat_user.dart
//
// Chat user model for Matrix users.

/// Chat user (Matrix user)
class ChatUser {
  /// Matrix user ID (e.g., "@user:matrix.local")
  final String userId;

  /// Display name (optional)
  final String? displayName;

  /// Avatar URL (optional, MXC URI)
  final String? avatarUrl;

  /// Access token (for authenticated requests)
  final String? accessToken;

  /// Device ID
  final String? deviceId;

  /// Home server
  final String? homeServer;

  const ChatUser({
    required this.userId,
    this.displayName,
    this.avatarUrl,
    this.accessToken,
    this.deviceId,
    this.homeServer,
  });

  ChatUser copyWith({
    String? userId,
    String? displayName,
    String? avatarUrl,
    String? accessToken,
    String? deviceId,
    String? homeServer,
  }) {
    return ChatUser(
      userId: userId ?? this.userId,
      displayName: displayName ?? this.displayName,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      accessToken: accessToken ?? this.accessToken,
      deviceId: deviceId ?? this.deviceId,
      homeServer: homeServer ?? this.homeServer,
    );
  }

  factory ChatUser.fromJson(Map<String, dynamic> json) {
    return ChatUser(
      userId: json['userId'] as String,
      displayName: json['displayName'] as String?,
      avatarUrl: json['avatarUrl'] as String?,
      accessToken: json['accessToken'] as String?,
      deviceId: json['deviceId'] as String?,
      homeServer: json['homeServer'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'userId': userId,
      if (displayName != null) 'displayName': displayName,
      if (avatarUrl != null) 'avatarUrl': avatarUrl,
      if (accessToken != null) 'accessToken': accessToken,
      if (deviceId != null) 'deviceId': deviceId,
      if (homeServer != null) 'homeServer': homeServer,
    };
  }

  /// Create from Matrix login/register response
  factory ChatUser.fromAuthResponse(Map<String, dynamic> data) {
    return ChatUser(
      userId: data['user_id'] as String,
      accessToken: data['access_token'] as String?,
      deviceId: data['device_id'] as String?,
      homeServer: data['home_server'] as String?,
    );
  }

  /// Get display name or fallback to user ID localpart
  String get displayNameOrId {
    if (displayName != null && displayName!.isNotEmpty) {
      return displayName!;
    }
    final match = RegExp(r'@([^:]+):').firstMatch(userId);
    return match?.group(1) ?? userId;
  }

  /// Check if user is authenticated
  bool get isAuthenticated => accessToken != null && accessToken!.isNotEmpty;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ChatUser &&
          runtimeType == other.runtimeType &&
          userId == other.userId &&
          displayName == other.displayName &&
          avatarUrl == other.avatarUrl &&
          accessToken == other.accessToken &&
          deviceId == other.deviceId &&
          homeServer == other.homeServer;

  @override
  int get hashCode => Object.hash(userId, displayName, avatarUrl, accessToken, deviceId, homeServer);

  @override
  String toString() => 'ChatUser(userId: $userId, displayName: $displayName)';
}
