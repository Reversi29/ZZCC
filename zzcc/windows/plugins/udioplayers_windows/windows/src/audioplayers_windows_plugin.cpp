#include "audioplayers_windows_plugin.h"
#include "audio_player.h"
#include <flutter/method_channel.h>
#include <flutter/plugin_registrar_windows.h>
#include <flutter/standard_method_codec.h>
#include <map>
#include <memory>

namespace {

class AudioplayersWindowsPlugin : public flutter::Plugin {
public:
    static void RegisterWithRegistrar(flutter::PluginRegistrarWindows *registrar);

    AudioplayersWindowsPlugin(flutter::PluginRegistrarWindows *registrar);
    virtual ~AudiolayersWindowsPlugin();

private:
    void HandleMethodCall(
        const flutter::MethodCall<flutter::EncodableValue> &method_call,
        std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result);

    flutter::PluginRegistrarWindows* registrar_;
    std::map<std::string, std::unique_ptr<AudioPlayer>> players_;
};

void AudioplayersWindowsPlugin::RegisterWithRegistrar(flutter::PluginRegistrarWindows *registrar) {
    auto channel = std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
        registrar->messenger(), "xyz.luan/audioplayers",
        &flutter::StandardMethodCodec::GetInstance());

    auto plugin = std::make_unique<AudiolayersWindowsPlugin>(registrar);

    channel->SetMethodCallHandler(
        [plugin_pointer = plugin.get()](const auto &call, auto result) {
            plugin_pointer->HandleMethodCall(call, std::move(result));
        });

    registrar->AddPlugin(std::move(plugin));
}

AudiolayersWindowsPlugin::AudiolayersWindowsPlugin(flutter::PluginRegistrarWindows *registrar)
    : registrar_(registrar) {}

void AudioplayersWindowsPlugin::HandleMethodCall(
    const flutter::MethodCall<flutter::EncodableValue> &method_call,
    std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
    
    if (method_call.method_name().compare("create") == 0) {
        // 解析 playerId
        auto player_id = std::get<std::string>(*method_call.arguments());
        
        // 创建播放器并设置事件通道
        auto player = std::make_unique<AudioPlayer>(registrar_, player_id);
        
        // 为每个播放器创建单独的事件通道
        auto event_channel = std::make_unique<flutter::EventChannel<flutter::EncodableValue>>(
            registrar_->messenger(), 
            "xyz.luan/audioplayers/events/" + player_id,
            &flutter::StandardMethodCodec::GetInstance()
        );
        
        event_channel->SetStreamHandler(
            std::make_unique<flutter::StreamHandlerFunctions<flutter::EncodableValue>>(
                [player_ptr = player.get()](const flutter::EncodableValue* arguments,
                                            std::unique_ptr<flutter::EventSink<flutter::EncodableValue>>&& sink)
                    -> std::unique_ptr<flutter::StreamHandlerError> {
                    player_ptr->SetEventSink(std::move(sink));
                    return nullptr;
                },
                [](const flutter::EncodableValue* arguments)
                    -> std::unique_ptr<flutter::StreamHandlerError> {
                    return nullptr;
                }));
        
        players_[player_id] = std::move(player);
        result->Success(nullptr);
    } 
    // 处理其他方法...
}
}  // namespace