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

  /// Whether this account was created locally and needs to sync with server.
  /// When true, user is logged in locally but not yet registered on the server.
  final bool needsSync;

  const ChatUser({
    required this.userId,
    this.displayName,
    this.avatarUrl,
    this.accessToken,
    this.deviceId,
    this.homeServer,
    this.needsSync = false,
  });

  ChatUser copyWith({
    String? userId,
    String? displayName,
    String? avatarUrl,
    String? accessToken,
    String? deviceId,
    String? homeServer,
    bool? needsSync,
  }) {
    return ChatUser(
      userId: userId ?? this.userId,
      displayName: displayName ?? this.displayName,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      accessToken: accessToken ?? this.accessToken,
      deviceId: deviceId ?? this.deviceId,
      homeServer: homeServer ?? this.homeServer,
      needsSync: needsSync ?? this.needsSync,
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
      needsSync: json['needsSync'] as bool? ?? false,
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
      if (needsSync) 'needsSync': true,
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

  /// True if user is logged in (server auth OR local account with needsSync)
  bool get isAuthenticated =>
      (accessToken != null && accessToken!.isNotEmpty) || needsSync;

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
          homeServer == other.homeServer &&
          needsSync == other.needsSync;

  @override
  int get hashCode => Object.hash(
      userId, displayName, avatarUrl, accessToken, deviceId, homeServer, needsSync);

  @override
  String toString() =>
      'ChatUser(userId: $userId, displayName: $displayName, needsSync: $needsSync)';
}
