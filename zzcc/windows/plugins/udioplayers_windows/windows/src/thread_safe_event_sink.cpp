#include "thread_safe_event_sink.h"
#include <flutter/plugin_registrar_windows.h>

ThreadSafeEventSink::ThreadSafeEventSink(flutter::EventSink<flutter::EncodableValue>* sink, HWND message_window)
    : sink_(sink), message_window_(message_window) {
    // Create a hidden window for message processing
    WNDCLASS wc = {};
    wc.lpfnWndProc = MessageWindowProc;
    wc.hInstance = GetModuleHandle(nullptr);
    wc.lpszClassName = L"FlutterEventDispatcher";
    RegisterClass(&wc);
    
    message_window_ = CreateWindow(
        L"FlutterEventDispatcher", L"Flutter Event Dispatcher", 0, 0, 0, 0, 0,
        HWND_MESSAGE, nullptr, GetModuleHandle(nullptr), this
    );
}

ThreadSafeEventSink::~ThreadSafeEventSink() {
    if (message_window_) {
        DestroyWindow(message_window_);
        message_window_ = nullptr;
    }
}

void ThreadSafeEventSink::Success(const flutter::EncodableValue& event) {
    std::lock_guard<std::mutex> lock(mutex_);
    EventData data;
    data.type = EventData::SUCCESS;
    data.success_value = event;
    event_queue_.push(data);
    PostEventToMainThread(data);
}

void ThreadSafeEventSink::Error(const std::string& error_code, const std::string& error_message) {
    std::lock_guard<std::mutex> lock(mutex_);
    EventData data;
    data.type = EventData::ERROR;
    data.error_code = error_code;
    data.error_message = error_message;
    event_queue_.push(data);
    PostEventToMainThread(data);
}

void ThreadSafeEventSink::EndOfStream() {
    std::lock_guard<std::mutex> lock(mutex_);
    EventData data;
    data.type = EventData::END_OF_STREAM;
    event_queue_.push(data);
    PostEventToMainThread(data);
}

void ThreadSafeEventSink::PostEventToMainThread(const EventData& event) {
    if (!message_window_) return;
    
    // Allocate memory for event data
    EventData* event_copy = new EventData(event);
    
    // Post message to window
    PostMessage(message_window_, WM_DISPATCH_EVENT, 0, reinterpret_cast<LPARAM>(event_copy));
}

void ThreadSafeEventSink::ProcessEvents() {
    std::lock_guard<std::mutex> lock(mutex_);
    while (!event_queue_.empty()) {
        DispatchEvent(event_queue_.front());
        event_queue_.pop();
    }
}

void ThreadSafeEventSink::DispatchEvent(const EventData& event) {
    if (!sink_) return;
    
    switch (event.type) {
        case EventData::SUCCESS:
            sink_->Success(event.success_value);
            break;
        case EventData::ERROR:
            sink_->Error(event.error_code, event.error_message);
            break;
        case EventData::END_OF_STREAM:
            sink_->EndOfStream();
            break;
    }
}

LRESULT CALLBACK ThreadSafeEventSink::MessageWindowProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    if (msg == WM_DISPATCH_EVENT) {
        ThreadSafeEventSink* self = reinterpret_cast<ThreadSafeEventSink*>(GetWindowLongPtr(hwnd, GWLP_USERDATA));
        if (self) {
            EventData* event = reinterpret_cast<EventData*>(lParam);
            self->DispatchEvent(*event);
            delete event;
        }
        return 0;
    } else if (msg == WM_CREATE) {
        CREATESTRUCT* create = reinterpret_cast<CREATESTRUCT*>(lParam);
        ThreadSafeEventSink* self = reinterpret_cast<ThreadSafeEventSink*>(create->lpCreateParams);
        SetWindowLongPtr(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
        return 0;
    }
    return DefWindowProc(hwnd, msg, wParam, lParam);
}