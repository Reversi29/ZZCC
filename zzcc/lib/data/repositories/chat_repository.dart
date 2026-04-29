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
  
  /// Login. Returns null on network failure; on 403 auto-synces local account.
  Future<ChatUser?> login({required String username, required String password, String? displayName});

  /// Sync a local-only account to the server (replaces local UID with server UID).
  /// Returns null on network failure; throws on auth errors.
  Future<ChatUser?> syncAccount({required String localUid, required String password, String? displayName});

  /// Sync offline account to server (used during auto-login).
  Future<void> syncOfflineAccountIfNeeded({required String password});

  /// Logout
  Future<void> logout();

  /// Permanently delete the user's account.
  /// [erase=true] removes all user data on the server (not reversible).
  Future<void> deleteAccount({bool erase = false});
  
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

  /// Called externally (e.g., from main.dart after auto-login) to sync any
  /// offline account. Safe to call multiple times; only syncs if needsSync=true.
  /// Requires [password] — register stores it in userInfo for auto-sync.
  @override
  Future<void> syncOfflineAccountIfNeeded({required String password}) async {
    final hasPw = password.isNotEmpty;
    final pwStatus = hasPw ? 'present' : 'EMPTY';
    _log.info('syncOfflineAccountIfNeeded: password=<$pwStatus> needsSync=${_currentUser?.needsSync}');
    if (_currentUser == null || !_currentUser!.needsSync) return;
    if (!hasPw) {
      _log.warning('syncOfflineAccountIfNeeded: password empty — user must log in with password first to enable sync');
      return;
    }
    _log.info('syncOfflineAccountIfNeeded: syncing offline user=${_currentUser!.userId}');
    final result = await syncAccount(
      localUid: _currentUser!.userId,
      password: password,
      displayName: _currentUser!.displayName,
    );
    if (result != null) {
      _log.info('syncOfflineAccountIfNeeded: success, userId=${result.userId}');
    } else {
      _log.warning('syncOfflineAccountIfNeeded: failed, remain offline');
    }
    // Emit auth state so message_screen and chatAuthProvider update
    _updateAuthState(_currentUser?.isAuthenticated ?? false);
  }

  void _restoreSession() {
    final config = _remoteSource.config;
    final token = config.chatAccessToken;
    final userId = config.chatUserId;
    final displayName = config.chatDisplayName;
    _log.info('_restoreSession: token=${token != null ? "present" : "null"}, userId=$userId, displayName=$displayName');

    if (token != null && token.isNotEmpty) {
      // Server-authenticated session
      _currentUser = ChatUser(
        userId: userId ?? '',
        displayName: displayName,
        accessToken: token,
        needsSync: false,
      );
      _log.info('Session restored: server user=$userId');
    } else if (userId != null) {
      // Offline session: server unreachable previously — flag for auto-sync
      _currentUser = ChatUser(
        userId: userId,
        displayName: displayName,
        accessToken: null,
        needsSync: true,
      );
      _log.info('Session restored: offline user=$userId (needsSync=true)');
    } else {
      _log.info('_restoreSession: no chat session found, _currentUser=null');
    }
    // Emit initial auth state so watchers (e.g. chatAuthProvider) get current value
    _updateAuthState(_currentUser?.isAuthenticated ?? false);
  }

  @override
  ChatUser? get currentUser => _currentUser;
  
  @override
  Stream<bool> get authStateStream => _authController.stream;
  
  /// True if user has an active session (server token or local needsSync account)
  @override
  bool get isAuthenticated => _currentUser?.isAuthenticated ?? false;
  
  void _updateAuthState(bool authenticated) {
    _log.info('_updateAuthState called with authenticated=$authenticated, _currentUser.isAuthenticated=${_currentUser?.isAuthenticated}');
    _authController.add(authenticated);
  }
  
  @override
  Future<ChatUser?> register({
    required String uid,
    required String password,
    String? displayName,
  }) async {
    _log.info('chatRepo.register: START uid=$uid');
    // Try server first (UID as username)
    ChatUser? serverUser;
    try {
      serverUser = await _remoteSource.register(
        username: uid,
        password: password,
        displayName: displayName,
      );
      _log.info('chatRepo.register: serverUser=${serverUser?.userId} token=${serverUser?.accessToken}');
    } catch (e) {
      _log.warning('chatRepo.register: remoteSource.register ERROR $e');
    }

    if (serverUser != null) {
      _log.info('chatRepo.register: server success userId=${serverUser.userId} token=${serverUser.accessToken?.substring(0, 8)}...');
      _currentUser = serverUser;
      _log.info('chatRepo.register: _currentUser set, isAuthenticated=${_currentUser?.isAuthenticated}');
      await _remoteSource.config.saveChatAuth(
        accessToken: serverUser.accessToken,
        userId: serverUser.userId,
        displayName: serverUser.displayName,
      );
      _log.info('chatRepo.register: saveChatAuth done, about to _updateAuthState(true)');
      _updateAuthState(true);
      _log.info('chatRepo.register: _updateAuthState(true) called');
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
    String? displayName,
  }) async {
    try {
      final user = await _remoteSource.login(
        username: username,
        password: password,
      );
      if (user != null) {
        _currentUser = user;
        _log.info('chatRepo.login: _currentUser set, isAuthenticated=${_currentUser?.isAuthenticated}');
        await _remoteSource.config.saveChatAuth(
          accessToken: user.accessToken,
          userId: user.userId,
          displayName: user.displayName,
        );
        _log.info('chatRepo.login: saveChatAuth done, about to _updateAuthState(true)');
        _updateAuthState(true);
        _log.info('chatRepo.login: _updateAuthState(true) called');
        return user;
      }
      // Network failure
      return null;
    } on ChatApiException catch (exc) {
      // 403: local account not yet on server — auto sync
      if (exc.statusCode == 403) {
        _log.info('Login 403 for $username, attempting sync');
        return syncAccount(localUid: username, password: password, displayName: displayName);
      }
      rethrow;
    }
  }

  @override
  Future<ChatUser?> syncAccount({
    required String localUid,
    required String password,
    String? displayName,
  }) async {
    final user = await _remoteSource.syncAccount(
      localUid: localUid,
      password: password,
      displayName: displayName,
    );
    if (user != null) {
      _currentUser = user;
      await _remoteSource.config.saveChatAuth(
        accessToken: user.accessToken,
        userId: user.userId,
        displayName: user.displayName,
      );
      _updateAuthState(true);
      return user;
    }
    // Network failure — not recoverable locally, caller handles
    return null;
  }
  
  @override
  Future<void> logout() async {
    await _remoteSource.logout();
    _currentUser = null;
    _updateAuthState(false);
  }

  @override
  Future<void> deleteAccount({bool erase = false}) async {
    _log.info('deleteAccount: erase=$erase');
    await _remoteSource.deleteAccount(erase: erase);
    _currentUser = null;
    _updateAuthState(false);
    _log.info('deleteAccount: done');
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
