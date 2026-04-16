// lib/domain/services/sync_service.dart
//
// Background sync service — handles real-time message updates via long-polling.

import 'dart:async';

import 'package:logging/logging.dart';

import '../../data/models/chat_message.dart';
import '../../data/repositories/chat_repository.dart';
import '../../data/sources/chat_remote_source.dart';

/// Sync service for real-time chat updates
class SyncService {
  final ChatRepository _repository;
  final Logger _log = Logger('SyncService');
  
  Timer? _syncTimer;
  String? _nextBatch;
  bool _isSyncing = false;
  bool _isRunning = false;
  
  // Streams for UI updates
  final _messageController = StreamController<RoomMessageEvent>.broadcast();
  final _connectionController = StreamController<bool>.broadcast();
  
  /// Stream of new messages from any room
  Stream<RoomMessageEvent> get messageStream => _messageController.stream;
  
  /// Stream of connection state changes
  Stream<bool> get connectionStream => _connectionController.stream;
  
  SyncService({required ChatRepository repository}) : _repository = repository;
  
  /// Start background sync
  void start() {
    if (_isRunning) return;
    
    _isRunning = true;
    _log.info('Starting sync service');
    _connectionController.add(true);
    
    // Initial sync
    _performSync();
    
    // Schedule periodic sync (as fallback)
    _syncTimer = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _performSync(),
    );
  }
  
  /// Stop background sync
  void stop() {
    if (!_isRunning) return;
    
    _isRunning = false;
    _log.info('Stopping sync service');
    _syncTimer?.cancel();
    _syncTimer = null;
    _connectionController.add(false);
  }
  
  /// Perform a single sync
  Future<void> _performSync() async {
    if (_isSyncing || !_repository.isAuthenticated) return;
    
    _isSyncing = true;
    
    try {
      final response = await _repository.sync(
        since: _nextBatch,
        timeout: 30000,
      );
      
      _nextBatch = response.nextBatch;
      
      // Process new messages
      response.rooms.forEach((roomId, roomData) {
        for (final message in roomData.newMessages) {
          _messageController.add(RoomMessageEvent(
            roomId: roomId,
            message: message,
          ));
        }
      });
      
      _log.fine('Sync completed, next_batch: ${_nextBatch?.substring(0, 20)}...');
    } catch (e) {
      _log.warning('Sync error: $e');
      // Don't stop on error, retry next cycle
    } finally {
      _isSyncing = false;
    }
  }
  
  /// Force immediate sync
  Future<void> syncNow() async {
    if (!_isRunning) {
      _log.warning('Sync service not running, cannot sync now');
      return;
    }
    await _performSync();
  }
  
  /// Reset sync state (e.g., after login/logout)
  void reset() {
    _nextBatch = null;
    _log.info('Sync state reset');
  }
  
  /// Dispose resources
  void dispose() {
    stop();
    _messageController.close();
    _connectionController.close();
  }
}

/// Event: new message in a room
class RoomMessageEvent {
  final String roomId;
  final ChatMessage message;
  
  RoomMessageEvent({
    required this.roomId,
    required this.message,
  });
}
