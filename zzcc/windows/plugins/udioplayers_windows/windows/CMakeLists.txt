# 添加新的源文件
add_library(audioplayers_windows_plugin SHARED
  "src/audio_player.cpp"
  "src/audio_player.h"
  "src/audioplayers_windows_plugin.cpp"
  "src/thread_safe_event_sink.cpp"
  "src/thread_safe_event_sink.h"
)

# 链接必要的库
target_link_libraries(audioplayers_windows_plugin PRIVATE
    flutter flutter_wrapper_plugin
    user32.lib
)