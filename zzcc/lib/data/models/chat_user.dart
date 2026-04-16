// lib/data/models/chat_user.dart
//
// Chat user model for Matrix users.

import 'package:freezed_annotation/freezed_annotation.dart';

part 'chat_user.freezed.dart';
part 'chat_user.g.dart';

/// Chat user (Matrix user)
@freezed
class ChatUser with _$ChatUser {
  const factory ChatUser({
    /// Matrix user ID (e.g., "@user:matrix.local")
    required String userId,
    
    /// Display name (optional)
    String? displayName,
    
    /// Avatar URL (optional, MXC URI)
    String? avatarUrl,
    
    /// Access token (for authenticated requests)
    String? accessToken,
    
    /// Device ID
    String? deviceId,
    
    /// Home server
    String? homeServer,
  }) = _ChatUser;

  factory ChatUser.fromJson(Map<String, dynamic> json) =>
      _$ChatUserFromJson(json);
  
  /// Create from Matrix login/register response
  factory ChatUser.fromAuthResponse(Map<String, dynamic> data) {
    return ChatUser(
      userId: data['user_id'] as String,
      accessToken: data['access_token'] as String,
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
}
