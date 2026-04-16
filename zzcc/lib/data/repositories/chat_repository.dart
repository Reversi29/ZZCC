// lib/data/repositories/chat_repository.dart
//
// Chat repository — abstracts data source for the domain layer.

import 'dart:async';
import 'package:logging/logging.dart';

import '../models/chat_message.dart';
import '../models/chat_room.dart';
import '../models/chat_user.dart';
import '../sources/chat_remote_source.dart';

/// Chat repository interface
abstract class ChatRepository {
  /// Current user
  ChatUser? get currentUser;
  
  /// Auth state stream
  Stream<bool> get authStateStream;
  
  /// Check if authenticated
  bool get isAuthenticated;
  
  /// Register new user. Returns null if server unreachable (local UID generated, needsSync=true).
  Future<ChatUser?> register({
    required String uid,
    required String password,
    String? displayName,
  });
  
  /// Login. Returns null on network failure (caller handles local fallback).
  Future<ChatUser?> login({required String username, required String password});
  
  /// Logout
  Future<void> logout();
  
  /// Get rooms
  Future<List<ChatRoom>> getRooms();
  
  /// Create room
  Future<ChatRoom> createRoom({
    String? name,
    String? topic,
    List<String>? invite,
    bool isDirect = false,
  });
  
  /// Join room
  Future<ChatRoom> joinRoom(String roomIdOrAlias);
  
  /// Leave room
  Future<void> leaveRoom(String roomId);
  
  /// Get messages
  Future<List<ChatMessage>> getMessages(String roomId, {int limit = 50});
  
  /// Send message
  Future<void> sendMessage(String roomId, String body);
  
  /// Sync for updates
  Future<SyncResponse> sync({String? since, int timeout = 30000});
}

/// Chat repository implementation
class ChatRepositoryImpl implements ChatRepository {
  final ChatRemoteSource _remoteSource;
  final Logger _log = Logger('ChatRepository');
  final _authController = StreamController<bool>.broadcast();
  ChatUser? _currentUser;
  
  ChatRepositoryImpl({required ChatRemoteSource remoteSource})
      : _remoteSource = remoteSource {
    // Restore session from persistent storage
    _restoreSession();
  }

  void _restoreSession() {
    final config = _remoteSource.config;
    final token = config.chatAccessToken;
    final userId = config.chatUserId;
    final displayName = config.chatDisplayName;

    if (token != null && token.isNotEmpty) {
      // Server-authenticated session
      _currentUser = ChatUser(
        userId: userId ?? '',
        displayName: displayName,
        accessToken: token,
        needsSync: false,
      );
      _log.info('Session restored: server user=${userId}');
    } else if (userId != null) {
      // Offline session: server unreachable previously, needsSync
      _currentUser = ChatUser(
        userId: userId,
        displayName: displayName,
        accessToken: null,
        needsSync: true,
      );
      _log.info('Session restored: offline user=$userId');
    }
  }
  
  @override
  ChatUser? get currentUser => _currentUser;
  
  @override
  Stream<bool> get authStateStream => _authController.stream;
  
  /// True if user has an active session (server token or local needsSync account)
  @override
  bool get isAuthenticated => _currentUser?.isAuthenticated ?? false;
  
  void _updateAuthState(bool authenticated) {
    _authController.add(authenticated);
  }
  
  @override
  Future<ChatUser?> register({
    required String uid,
    required String password,
    String? displayName,
  }) async {
    // Try server first (UID as username)
    final serverUser = await _remoteSource.register(
      username: uid,
      password: password,
      displayName: displayName,
    );

    if (serverUser != null) {
      _currentUser = serverUser;
      _updateAuthState(true);
      return serverUser;
    }

    // Server unreachable — use local UID, mark needsSync
    _log.info('Server unreachable during register, using local UID');
    // Persist locally so session survives app restart
    await _remoteSource.config.saveChatAuth(
      accessToken: null,
      userId: uid,
      displayName: displayName,
    );
    final localUser = ChatUser(
      userId: uid,
      displayName: displayName,
      accessToken: null,
      needsSync: true,
    );
    _currentUser = localUser;
    _updateAuthState(true);
    return localUser;
  }
  
  @override
  Future<ChatUser?> login({
    required String username,
    required String password,
  }) async {
    final user = await _remoteSource.login(
      username: username,
      password: password,
    );
    if (user != null) {
      _currentUser = user;
      _updateAuthState(true);
      return user;
    }
    // Network failure — caller (LoginPage) will handle local fallback
    return null;
  }
  
  @override
  Future<void> logout() async {
    await _remoteSource.logout();
    _currentUser = null;
    _updateAuthState(false);
  }
  
  @override
  Future<List<ChatRoom>> getRooms() => _remoteSource.getRooms();
  
  @override
  Future<ChatRoom> createRoom({
    String? name,
    String? topic,
    List<String>? invite,
    bool isDirect = false,
  }) => _remoteSource.createRoom(
    name: name,
    topic: topic,
    invite: invite,
    isDirect: isDirect,
  );
  
  @override
  Future<ChatRoom> joinRoom(String roomIdOrAlias) => 
      _remoteSource.joinRoom(roomIdOrAlias);
  
  @override
  Future<void> leaveRoom(String roomId) => _remoteSource.leaveRoom(roomId);
  
  @override
  Future<List<ChatMessage>> getMessages(String roomId, {int limit = 50}) =>
      _remoteSource.getMessages(roomId, limit: limit);
  
  @override
  Future<void> sendMessage(String roomId, String body) =>
      _remoteSource.sendMessage(roomId, body);
  
  @override
  Future<SyncResponse> sync({String? since, int timeout = 30000}) =>
      _remoteSource.sync(since: since, timeout: timeout);
}
