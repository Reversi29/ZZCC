class LrcParser {
  static Map<Duration, String> parseLrc(String lrcString) {
    final lines = lrcString.split('\n');
    final lyrics = <Duration, String>{};
    
    final timeRegExp = RegExp(r'\[(\d+):(\d+).(\d+)\]');
    
    for (var line in lines) {
      final matches = timeRegExp.allMatches(line);
      if (matches.isEmpty) continue;
      
      final text = line.replaceAll(timeRegExp, '').trim();
      if (text.isEmpty) continue;
      
      for (var match in matches) {
        final minutes = int.parse(match.group(1)!);
        final seconds = int.parse(match.group(2)!);
        final milliseconds = int.parse(match.group(3)!);
        final time = Duration(
          minutes: minutes,
          seconds: seconds,
          milliseconds: milliseconds * 10, // 因为LRC的毫秒是两位数，代表百分之一秒
        );
        
        lyrics[time] = text;
      }
    }
    
    return lyrics;
  }
}