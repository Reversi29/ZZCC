#pragma once
#include <flutter/event_sink.h>
#include <flutter/encodable_value.h>
#include <Windows.h>
#include <memory>
#include <mutex>
#include <queue>
#include <functional>
#include <thread>

class ThreadSafeEventSink {
public:
    ThreadSafeEventSink(flutter::EventSink<flutter::EncodableValue>* sink, HWND message_window);
    ~ThreadSafeEventSink();

    void Success(const flutter::EncodableValue& event);
    void Error(const std::string& error_code, const std::string& error_message);
    void EndOfStream();

private:
    struct EventData {
        enum EventType { SUCCESS, ERROR, END_OF_STREAM };
        EventType type;
        flutter::EncodableValue success_value;
        std::string error_code;
        std::string error_message;
    };

    void PostEventToMainThread(const EventData& event);
    void ProcessEvents();
    void DispatchEvent(const EventData& event);
    static LRESULT CALLBACK MessageWindowProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam);

    flutter::EventSink<flutter::EncodableValue>* sink_;
    HWND message_window_;
    std::mutex mutex_;
    std::queue<EventData> event_queue_;
    static const UINT WM_DISPATCH_EVENT = WM_USER + 100;
};