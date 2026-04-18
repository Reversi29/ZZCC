import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:get_it/get_it.dart';
import 'package:zzcc/data/repositories/chat_repository.dart';

/// Exposes whether the chat session is authenticated (server token present).
/// Prepends the current auth state so late subscribers get it immediately.
final chatAuthProvider = StreamProvider<bool>((ref) {
  final repo = GetIt.I<ChatRepository>();
  final current = repo.isAuthenticated;
  return Stream.value(current).asyncExpand((_) => repo.authStateStream);
});
