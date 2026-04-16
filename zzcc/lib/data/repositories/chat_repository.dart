// lib/data/repositories/chat_repository.dart
//
// Chat repository — abstracts data source for the domain layer.

import 'dart:async';

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
  
  /// Register new user
  Future<ChatUser> register({
    required String username,
    required String password,
    String? displayName,
  });
  
  /// Login
  Future<ChatUser> login({required String username, required String password});
  
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
  final _authController = StreamController<bool>.broadcast();
  ChatUser? _currentUser;
  
  ChatRepositoryImpl({required ChatRemoteSource remoteSource})
      : _remoteSource = remoteSource;
  
  @override
  ChatUser? get currentUser => _currentUser;
  
  @override
  Stream<bool> get authStateStream => _authController.stream;
  
  @override
  bool get isAuthenticated => _remoteSource.isAuthenticated;
  
  void _updateAuthState(bool authenticated) {
    _authController.add(authenticated);
  }
  
  @override
  Future<ChatUser> register({
    required String username,
    required String password,
    String? displayName,
  }) async {
    final user = await _remoteSource.register(
      username: username,
      password: password,
      displayName: displayName,
    );
    _currentUser = user;
    _updateAuthState(true);
    return user;
  }
  
  @override
  Future<ChatUser> login({
    required String username,
    required String password,
  }) async {
    final user = await _remoteSource.login(
      username: username,
      password: password,
    );
    _currentUser = user;
    _updateAuthState(true);
    return user;
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
