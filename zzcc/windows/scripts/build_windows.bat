@echo off
setlocal

set BUILD_DIR=%~dp0..\..\build\windows\x64\runner\Debug
set NATIVE_DIR=%~dp0..\..\native\windows

if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"

:: 检查依赖库是否存在
if not exist "%NATIVE_DIR%\libtorrent.dll" (
    echo 依赖库不存在，开始下载...
    powershell -ExecutionPolicy Bypass -File "%~dp0..\..\scripts\download_dependencies.ps1"
)

:: 复制库文件
if exist "%NATIVE_DIR%\*.dll" (
    copy /Y "%NATIVE_DIR%\*.dll" "%BUILD_DIR%"
)

:: 运行 CMake
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release

endlocal