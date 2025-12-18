import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/scheduler.dart';

class AudioEventHandler {
  final AudioPlayer player;
  final void Function(Duration)? onDurationChanged;
  final void Function(Duration)? onPositionChanged;
  final void Function(PlayerState)? onPlayerStateChanged;
  final void Function()? onPlayerComplete;

  AudioEventHandler({
    required this.player,
    this.onDurationChanged,
    this.onPositionChanged,
    this.onPlayerStateChanged,
    this.onPlayerComplete,
  }) {
    // 使用更简洁的线程安全监听器
    _setupThreadSafeListeners();
  }

  void _setupThreadSafeListeners() {
    player.onDurationChanged.listen((duration) {
      _runOnMainThread(() => onDurationChanged?.call(duration));
    });
    
    player.onPositionChanged.listen((position) {
      _runOnMainThread(() => onPositionChanged?.call(position));
    });
    
    player.onPlayerStateChanged.listen((state) {
      _runOnMainThread(() => onPlayerStateChanged?.call(state));
    });
    
    player.onPlayerComplete.listen((_) {
      _runOnMainThread(() => onPlayerComplete?.call());
    });
  }

  void _runOnMainThread(void Function() action) {
    if (SchedulerBinding.instance.schedulerPhase == SchedulerPhase.idle) {
      SchedulerBinding.instance.addPostFrameCallback((_) => action());
    } else {
      action();
    }
    // // 使用 SchedulerBinding 确保在主线程执行
    // SchedulerBinding.instance.scheduleTask(
    //   action,
    //   Priority.animation,
    // );
  }
}