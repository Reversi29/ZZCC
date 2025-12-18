@echo off
setlocal

:: 设置源目录和目标目录
set SOURCE_DIR=%~dp0..\native\windows
set TARGET_DIR=%~dp0..\build\windows\x64\runner\Debug
set CONFIG_FILE=%~dp0..\windows\zzcc_config.json

:: 创建目标目录（如果不存在）
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

del /s /q "%SOURCE_DIR%\*.bak*" 2>nul
:: 复制其他必要的DLL文件
copy /Y "%SOURCE_DIR%\*.dll" "%TARGET_DIR%"

:: 仅当配置文件不存在时才复制
if not exist "%TARGET_DIR%\zzcc_config.json" (
    if exist "%CONFIG_FILE%" (
        copy /Y "%CONFIG_FILE%" "%TARGET_DIR%"
    ) else (
        echo 错误: 配置文件不存在 %CONFIG_FILE%
    )
)

endlocal
::pause