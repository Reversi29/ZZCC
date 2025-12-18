import 'package:flutter/material.dart';

class LyricsDisplay extends StatefulWidget {
  final Map<Duration, String> lyrics;
  final Duration currentPosition;

  const LyricsDisplay({
    super.key,
    required this.lyrics,
    required this.currentPosition,
  });

  @override
  State<LyricsDisplay> createState() => _LyricsDisplayState();
}

class _LyricsDisplayState extends State<LyricsDisplay> {
  late List<MapEntry<Duration, String>> sortedLyrics;
  int? currentIndex;

  @override
  void initState() {
    super.initState();
    sortedLyrics = widget.lyrics.entries.toList()
      ..sort((a, b) => a.key.compareTo(b.key));
    _updateCurrentIndex();
  }

  @override
  void didUpdateWidget(covariant LyricsDisplay oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.lyrics != widget.lyrics) {
      sortedLyrics = widget.lyrics.entries.toList()
        ..sort((a, b) => a.key.compareTo(b.key));
    }
    _updateCurrentIndex();
  }

  void _updateCurrentIndex() {
    if (sortedLyrics.isEmpty) {
      currentIndex = null;
      return;
    }

    for (int i = 0; i < sortedLyrics.length; i++) {
      if (widget.currentPosition < sortedLyrics[i].key) {
        currentIndex = i - 1;
        return;
      }
    }
    currentIndex = sortedLyrics.length - 1;
  }

  @override
  Widget build(BuildContext context) {
    if (sortedLyrics.isEmpty) {
      return const Center(
        child: Text('暂无歌词'),
      );
    }

    return ListView.builder(
      itemCount: sortedLyrics.length,
      itemBuilder: (context, index) {
        final isCurrent = index == currentIndex;
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 8.0),
          child: Text(
            sortedLyrics[index].value,
            style: TextStyle(
              fontSize: isCurrent ? 20 : 16,
              fontWeight: isCurrent ? FontWeight.bold : FontWeight.normal,
              color: isCurrent ? Colors.blue : Colors.black,
            ),
            textAlign: TextAlign.center,
          ),
        );
      },
    );
  }
}