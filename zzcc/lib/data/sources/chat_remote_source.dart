// lib/data/sources/chat_remote_source.dart
//
// Chat API remote data source — talks to ZZCC FastAPI chat endpoints.

import 'package:dio/dio.dart';
import 'package:logging/logging.dart';

import '../models/chat_message.dart';
import '../models/chat_room.dart';
import '../models/chat_user.dart';
import 'package:zzcc/core/services/config_service.dart';
import 'package:zzcc/core/di/service_locator.dart';

/// Chat API exception
class ChatApiException implements Exception {
  final String message;
  final int? statusCode;
  
  ChatApiException(this.message, {this.statusCode});
  
  @override
  String toString() => 'ChatApiException: $message (status: $statusCode)';
}

/// Chat remote data source
class ChatRemoteSource {
  late final Dio _dio;
  final Logger _log = Logger('ChatRemoteSource');
  late final ConfigService _config;
  
  String? _accessToken;
  
  ChatRemoteSource({Dio? dio, ConfigService? config}) {
    _config = config ?? getIt<ConfigService>();
    _dio = dio ?? Dio(BaseOptions(
      baseUrl: _config.nebulaApiBaseUrl,  // Chat shares same base URL
      connectTimeout: const Duration(seconds: 8),
      receiveTimeout: const Duration(seconds: 60),  // Longer for long-poll
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': _config.nebulaApiKey,
      },
    ));
    
    // Restore persisted token on init
    if (_config.chatAccessToken != null) {
      setAccessToken(_config.chatAccessToken);
    }
  }
  
  /// Set access token for authenticated requests
  void setAccessToken(String? token) {
    _accessToken = token;
    _log.info('Access token ${token != null ? "set" : "cleared"}');
  }
  
  /// Get current access token
  String? get accessToken => _accessToken;
  
  /// Check if authenticated
  bool get isAuthenticated => _accessToken != null && _accessToken!.isNotEmpty;
  
  /// Build request headers with auth
  Map<String, String> _headers() {
    final headers = <String, String>{};
    if (_accessToken != null && _accessToken!.isNotEmpty) {
      headers['X-Access-Token'] = _accessToken!;
    }
    return headers;
  }
  
  /// Handle API errors
  Never _handleError(Object e, String operation) {
    if (e is DioException) {
      final status = e.response?.statusCode;
      final data = e.response?.data;
      final detail = data?['detail'] ?? e.message;
      _log.warning('$operation failed: $detail (status: $status)');
      throw ChatApiException(detail?.toString() ?? 'Network error', statusCode: status);
    }
    _log.warning('$operation failed: $e');
    throw ChatApiException(e.toString());
  }
  
  // ============================================================
  // Authentication
  // ============================================================
  
  /// Register new user
  Future<ChatUser> register({
    required String username,
    required String password,
    String? displayName,
  }) async {
    try {
      _log.info('Registering user: $username');
      final response = await _dio.post(
        '/chat/register',
        data: {
          'username': username,
          'password': password,
          if (displayName != null) 'display_name': displayName,
        },
      );
      
      final data = response.data['data'] as Map<String, dynamic>;
      final user = ChatUser.fromAuthResponse(data);
      setAccessToken(user.accessToken);
      await _config.saveChatAuth(
        accessToken: user.accessToken,
        userId: user.userId,
        displayName: user.displayName,
      );
      _log.info('Registered: ${user.userId}');
      return user;
    } catch (e) {
      _handleError(e, 'register');
    }
  }
  
  /// Login existing user
  Future<ChatUser> login({
    required String username,
    required String password,
  }) async {
    try {
      _log.info('Logging in: $username');
      final response = await _dio.post(
        '/chat/login',
        data: {
          'username': username,
          'password': password,
        },
      );
      
      final data = response.data['data'] as Map<String, dynamic>;
      final user = ChatUser.fromAuthResponse(data);
      setAccessToken(user.accessToken);
      await _config.saveChatAuth(
        accessToken: user.accessToken,
        userId: user.userId,
        displayName: user.displayName,
      );
      _log.info('Logged in: ${user.userId}');
      return user;
    } catch (e) {
      _handleError(e, 'login');
    }
  }
  
  /// Logout current user
  Future<void> logout() async {
    if (!isAuthenticated) return;
    
    try {
      _log.info('Logging out');
      await _dio.post('/chat/logout', options: Options(headers: _headers()));
    } catch (e) {
      _log.warning('Logout error (ignored): $e');
    } finally {
      setAccessToken(null);
      await _config.clearChatAuth();
    }
  }
  
  // ============================================================
  // Profile
  // ============================================================
  
  /// Get user profile
  Future<Map<String, dynamic>> getProfile(String userId) async {
    try {
      final response = await _dio.get('/chat/profile/$userId');
      return response.data['data'] as Map<String, dynamic>;
    } catch (e) {
      _handleError(e, 'getProfile');
    }
  }
  
  /// Set display name
  Future<void> setDisplayName(String displayName) async {
    if (!isAuthenticated) {
      throw ChatApiException('Not authenticated');
    }
    
    try {
      await _dio.put(
        '/chat/profile/displayname',
        data: {'display_name': displayName},
        options: Options(headers: _headers()),
      );
    } catch (e) {
      _handleError(e, 'setDisplayName');
    }
  }
  
  // ============================================================
  // Rooms
  // ============================================================
  
  /// Get joined rooms
  Future<List<ChatRoom>> getRooms() async {
    if (!isAuthenticated) {
      throw ChatApiException('Not authenticated');
    }
    
    try {
      _log.fine('Fetching rooms');
      final response = await _dio.get(
        '/chat/rooms',
        options: Options(headers: _headers()),
      );
      
      final data = response.data['data'] as Map<String, dynamic>;
      final rooms = (data['rooms'] as List<dynamic>)
          .map((r) => ChatRoom.fromMatrixResponse(r as Map<String, dynamic>))
          .toList();
      
      _log.fine('Fetched ${rooms.length} rooms');
      return rooms;
    } catch (e) {
      _handleError(e, 'getRooms');
    }
  }
  
  /// Create a new room
  Future<ChatRoom> createRoom({
    String? name,
    String? topic,
    List<String>? invite,
    bool isDirect = false,
  }) async {
    if (!isAuthenticated) {
      throw ChatApiException('Not authenticated');
    }
    
    try {
      _log.info('Creating room: $name');
      final response = await _dio.post(
        '/chat/rooms',
        data: {
          if (name != null) 'name': name,
          if (topic != null) 'topic': topic,
          if (invite != null) 'invite': invite,
          'is_direct': isDirect,
        },
        options: Options(headers: _headers()),
      );
      
      final data = response.data['data'] as Map<String, dynamic>;
      final roomId = data['room_id'] as String;
      
      // Fetch room info to get full details
      return await _getRoomInfo(roomId);
    } catch (e) {
      _handleError(e, 'createRoom');
    }
  }
  
  /// Join a room
  Future<ChatRoom> joinRoom(String roomIdOrAlias) async {
    if (!isAuthenticated) {
      throw ChatApiException('Not authenticated');
    }
    
    try {
      _log.info('Joining room: $roomIdOrAlias');
      await _dio.post(
        '/chat/rooms/$roomIdOrAlias/join',
        options: Options(headers: _headers()),
      );
      
      // Fetch room info
      return await _getRoomInfo(roomIdOrAlias);
    } catch (e) {
      _handleError(e, 'joinRoom');
    }
  }
  
  /// Leave a room
  Future<void> leaveRoom(String roomId) async {
    if (!isAuthenticated) {
      throw ChatApiException('Not authenticated');
    }
    
    try {
      _log.info('Leaving room: $roomId');
      await _dio.post(
        '/chat/rooms/$roomId/leave',
        options: Options(headers: _headers()),
      );
    } catch (e) {
      _handleError(e, 'leaveRoom');
    }
  }
  
  /// Get room info (internal)
  Future<ChatRoom> _getRoomInfo(String roomId) async {
    // Get room details from list
    final rooms = await getRooms();
    return rooms.firstWhere(
      (r) => r.roomId == roomId,
      orElse: () => ChatRoom(roomId: roomId),
    );
  }
  
  // ============================================================
  // Messages
  // ============================================================
  
  /// Get room messages
  Future<List<ChatMessage>> getMessages(
    String roomId, {
    int limit = 50,
    String? fromToken,
  }) async {
    if (!isAuthenticated) {
      throw ChatApiException('Not authenticated');
    }
    
    try {
      _log.fine('Fetching messages for $roomId');
      final response = await _dio.get(
        '/chat/rooms/$roomId/messages',
        queryParameters: {
          'limit': limit,
          if (fromToken != null) 'from_token': fromToken,
        },
        options: Options(headers: _headers()),
      );
      
      final data = response.data['data'] as Map<String, dynamic>;
      final messages = (data['messages'] as List<dynamic>)
          .map((m) => ChatMessage.fromMatrixResponse(m as Map<String, dynamic>))
          .toList();
      
      _log.fine('Fetched ${messages.length} messages');
      return messages;
    } catch (e) {
      _handleError(e, 'getMessages');
    }
  }
  
  /// Send a message
  Future<String> sendMessage(String roomId, String body) async {
    if (!isAuthenticated) {
      throw ChatApiException('Not authenticated');
    }
    
    try {
      _log.info('Sending message to $roomId');
      final response = await _dio.post(
        '/chat/rooms/$roomId/messages',
        data: {'body': body},
        options: Options(headers: _headers()),
      );
      
      final data = response.data['data'] as Map<String, dynamic>;
      final eventId = data['event_id'] as String;
      _log.fine('Message sent: $eventId');
      return eventId;
    } catch (e) {
      _handleError(e, 'sendMessage');
    }
  }
  
  // ============================================================
  // Sync (Real-time updates)
  // ============================================================
  
  /// Sync for real-time updates (long-polling)
  /// 
  /// Returns sync response with new messages and room updates.
  /// Use [since] from previous response's [nextBatch].
  Future<SyncResponse> sync({
    String? since,
    int timeout = 30000,
  }) async {
    if (!isAuthenticated) {
      throw ChatApiException('Not authenticated');
    }
    
    try {
      _log.fine('Syncing (since: ${since?.substring(0, since.length > 20 ? 20 : since.length)}...)');
      final response = await _dio.get(
        '/chat/sync',
        queryParameters: {
          if (since != null) 'since': since,
          'timeout': timeout,
        },
        options: Options(
          headers: _headers(),
          // Long timeout for long-polling
          receiveTimeout: Duration(milliseconds: timeout + 10000),
        ),
      );
      
      final data = response.data['data'] as Map<String, dynamic>;
      return SyncResponse.fromJson(data);
    } catch (e) {
      _handleError(e, 'sync');
    }
  }
}

/// Sync response model
class SyncResponse {
  final String nextBatch;
  final Map<String, RoomSyncData> rooms;
  
  SyncResponse({
    required this.nextBatch,
    required this.rooms,
  });
  
  factory SyncResponse.fromJson(Map<String, dynamic> json) {
    final roomsJson = json['rooms'] as Map<String, dynamic>? ?? {};
    final rooms = <String, RoomSyncData>{};
    
    roomsJson.forEach((roomId, data) {
      rooms[roomId] = RoomSyncData.fromJson(data as Map<String, dynamic>);
    });
    
    return SyncResponse(
      nextBatch: json['next_batch'] as String,
      rooms: rooms,
    );
  }
}

/// Room sync data (new messages from sync)
class RoomSyncData {
  final List<ChatMessage> newMessages;
  final bool? limited;
  final String? prevBatch;
  
  RoomSyncData({
    required this.newMessages,
    this.limited,
    this.prevBatch,
  });
  
  factory RoomSyncData.fromJson(Map<String, dynamic> json) {
    final messages = (json['new_messages'] as List<dynamic>? ?? [])
        .map((m) => ChatMessage.fromMatrixResponse(m as Map<String, dynamic>))
        .toList();
    
    return RoomSyncData(
      newMessages: messages,
      limited: json['limited'] as bool?,
      prevBatch: json['prev_batch'] as String?,
    );
  }
}
