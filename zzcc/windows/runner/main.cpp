#include <flutter/dart_project.h>
#include <flutter/flutter_view_controller.h>
#include <windows.h>

#include "flutter_window.h"
#include "utils.h"

int APIENTRY wWinMain(_In_ HINSTANCE instance, _In_opt_ HINSTANCE prev,
                      _In_ wchar_t *command_line, _In_ int show_command) {
  // CopyDllFiles();

  // Attach to console when present (e.g., 'flutter run') or create a
  // new console when running with a debugger.
  if (!::AttachConsole(ATTACH_PARENT_PROCESS) && ::IsDebuggerPresent()) {
    CreateAndAttachConsole();
  }

  // Initialize COM, so that it is available for use in the library and/or
  // plugins.
  ::CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);

  flutter::DartProject project(L"data");

  std::vector<std::string> command_line_arguments =
      GetCommandLineArguments();

  project.set_dart_entrypoint_arguments(std::move(command_line_arguments));

  FlutterWindow window(project);
  Win32Window::Point origin(10, 10);
  Win32Window::Size size(1280, 720);
  if (!window.Create(L"zzcc", origin, size)) {
    return EXIT_FAILURE;
  }
  window.SetQuitOnClose(true);

  ::MSG msg;
  while (::GetMessage(&msg, nullptr, 0, 0)) {
    ::TranslateMessage(&msg);
    ::DispatchMessage(&msg);
  }

  ::CoUninitialize();
  return EXIT_SUCCESS;
}

extern "C" __declspec(dllexport) void CopyDllFiles() {
    // 获取当前可执行文件路径
    wchar_t exePath[MAX_PATH];
    GetModuleFileNameW(NULL, exePath, MAX_PATH);
    
    // 提取目录路径
    std::wstring::size_type pos = std::wstring(exePath).find_last_of(L"\\/");
    std::wstring exeDir = std::wstring(exePath).substr(0, pos);
    
    // 源 DLL 文件路径
    std::wstring srcDll = exeDir + L"\\..\\native\\windows\\torrent-rasterbar.dll";
    
    // 目标 DLL 文件路径
    std::wstring destDll = exeDir + L"\\torrent-rasterbar.dll";
    
    // 复制文件
    CopyFileW(srcDll.c_str(), destDll.c_str(), FALSE);
}