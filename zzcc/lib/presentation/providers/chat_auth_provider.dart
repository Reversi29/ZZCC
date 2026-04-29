import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:get_it/get_it.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/data/repositories/chat_repository.dart';
import 'package:zzcc/core/services/logger_service.dart';

/// Exposes whether the chat session is authenticated (server token present).
/// Emits the current auth value immediately, then relays live auth state changes.
final chatAuthProvider = StreamProvider<bool>((ref) {
  final repo = GetIt.I<ChatRepository>();
  final initial = repo.isAuthenticated;
  getIt<LoggerService>().info('[chatAuthProvider] init, initial isAuthenticated=$initial');

  // StreamController: emit initial value synchronously, then relay live stream.
  final controller = StreamController<bool>();

  // Emit initial value immediately so late subscribers see it on first build.
  controller.add(initial);
  getIt<LoggerService>().info('[chatAuthProvider] seed emit=$initial');

  // Relay live auth state changes from the repository.
  repo.authStateStream.listen((value) {
    getIt<LoggerService>().info('[chatAuthProvider] authStateStream emit=$value');
    if (!controller.isClosed) controller.add(value);
  });

  ref.onDispose(() => controller.close());
  return controller.stream;
});
