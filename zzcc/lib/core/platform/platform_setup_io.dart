// lib/core/platform/platform_setup_io.dart
//
// Native platform setup — Windows console handler only.
// Non-Windows platforms use this file (web uses stub).

import 'dart:ffi';
import 'dart:io';

typedef _SetConsoleCtrlHandlerNative = Int32 Function(
    Pointer<NativeFunction<Int32 Function(Int32)>>, Int32);
typedef _SetConsoleCtrlHandlerDart = int Function(
    Pointer<NativeFunction<Int32 Function(Int32)>>, int);

void _cleanup() {
  // nothing to clean up on non-Windows
}

int _exitHandler(int ctrlType) {
  _cleanup();
  exit(0);
}

void setupExitHandler() {
  if (!Platform.isWindows) return;

  final kernel32 = DynamicLibrary.open('kernel32.dll');
  final setConsoleCtrlHandler = kernel32.lookupFunction<
      _SetConsoleCtrlHandlerNative,
      _SetConsoleCtrlHandlerDart>('SetConsoleCtrlHandler');

  final handler = Pointer.fromFunction<Int32 Function(Int32)>(_exitHandler, 0);
  setConsoleCtrlHandler(handler, 1);
}
