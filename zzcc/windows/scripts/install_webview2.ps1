# scripts/install_webview2.ps1
$ErrorActionPreference = "Stop"

$webview2Url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
$installerPath = "$env:TEMP\MicrosoftEdgeWebview2Setup.exe"

try {
    Write-Host "下载 WebView2 运行时..."
    Invoke-WebRequest -Uri $webview2Url -OutFile $installerPath
    
    Write-Host "安装 WebView2 运行时..."
    Start-Process -FilePath $installerPath -ArgumentList "/silent /install" -Wait
    
    Write-Host "WebView2 运行时安装完成"
    Remove-Item $installerPath
} catch {
    Write-Host "安装失败: $_"
    exit 1
}