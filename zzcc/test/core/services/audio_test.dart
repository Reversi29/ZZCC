import 'package:flutter_test/flutter_test.dart';
import 'package:audioplayers/audioplayers.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late AudioPlayer audioPlayer;

  setUp(() {
    audioPlayer = AudioPlayer();
  });

  tearDown(() {
    audioPlayer.dispose();
  });

  group('AudioPlayer Basic Tests', () {
    test('Initial state should be stopped', () {
      expect(audioPlayer.state, PlayerState.stopped);
    });

    test('Play from asset should change state', () async {
      await audioPlayer.play(DeviceFileSource(r'f:\github\zzcc\资源\音视频\96猫 (クロネコ) - 嘘の火花 (谎言的火花).flac'));
      expect(audioPlayer.state, PlayerState.playing);
    });

    test('Pause should change state', () async {
      await audioPlayer.play(DeviceFileSource(r'f:\github\zzcc\资源\音视频\96猫 (クロネコ) - 嘘の火花 (谎言的火花).flac'));
      await audioPlayer.pause();
      expect(audioPlayer.state, PlayerState.paused);
    });

    test('Stop should reset state', () async {
      await audioPlayer.play(DeviceFileSource(r'f:\github\zzcc\资源\音视频\96猫 (クロネコ) - 嘘の火花 (谎言的火花).flac'));
      await audioPlayer.stop();
      expect(audioPlayer.state, PlayerState.stopped);
    });
  });

  group('AudioPlayer Volume Tests', () {
    test('Volume should be adjustable', () async {
      await audioPlayer.setVolume(0.5);
      // 新版通过监听volume属性获取当前音量
      expect(audioPlayer.volume, 0.5);
    });
  });
}
