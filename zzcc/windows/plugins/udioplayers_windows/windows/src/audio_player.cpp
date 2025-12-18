#include "audio_player.h"
#include "thread_safe_event_sink.h"

AudioPlayer::AudioPlayer(flutter::PluginRegistrarWindows* registrar, const std::string& playerId)
    : registrar_(registrar), player_id_(playerId) {}

void AudioPlayer::SetEventSink(std::unique_ptr<flutter::EventSink<flutter::EncodableValue>>&& sink) {
    thread_safe_sink_ = std::make_unique<ThreadSafeEventSink>(sink.release(), nullptr);
}

void AudioPlayer::EmitEvent(const flutter::EncodableMap& event) {
    if (thread_safe_sink_) {
        thread_safe_sink_->Success(flutter::EncodableValue(event));
    }
}

// 在事件触发的地方调用 EmitEvent
void AudioPlayer::OnPositionChanged() {
    flutter::EncodableMap event = {
        {flutter::EncodableValue("event"), flutter::EncodableValue("position")},
        {flutter::EncodableValue("position"), flutter::EncodableValue(current_position_)}
    };
    EmitEvent(event);
}