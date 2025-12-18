#pragma once
#include <flutter/encodable_value.h>
#include <flutter/event_channel.h>
#include <flutter/method_channel.h>
#include <flutter/plugin_registrar_windows.h>
#include <flutter/standard_method_codec.h>
#include <Windows.h>
#include <memory>
#include <string>
#include "thread_safe_event_sink.h"

class AudioPlayer {
public:
    AudioPlayer(flutter::PluginRegistrarWindows* registrar, const std::string& playerId);
    ~AudioPlayer();

    void SetEventSink(std::unique_ptr<flutter::EventSink<flutter::EncodableValue>>&& sink);

    // ... 其他方法 ...

private:
    void EmitEvent(const flutter::EncodableMap& event);

    std::string player_id_;
    std::unique_ptr<ThreadSafeEventSink> thread_safe_sink_;
    flutter::PluginRegistrarWindows* registrar_;
};