# 设置变量
$BUILD_DIR = "$PSScriptRoot\..\..\build\windows\x64\runner\Debug"
$NATIVE_DIR = "$PSScriptRoot\..\..\native\windows"
$PROJECT_DIR = "$PSScriptRoot\..\.."  # 项目根目录
$VCPKG_MANIFEST_DIR = "$PSScriptRoot\.."  # vcpkg.json 所在目录
$HOSTS_FILE = "$env:windir\System32\drivers\etc\hosts"

# 读取 vcpkg 路径
$vcpkgPathFile = "$PSScriptRoot\vcpkg_path.txt"
$vcpkgPath = if (Test-Path $vcpkgPathFile) { Get-Content $vcpkgPathFile -Raw } else { "windows/vcpkg" }

# 检查路径是否有效
$validVcpkg = $false
if (Test-Path $vcpkgPath) {
    $bootstrapFile = Join-Path $vcpkgPath "bootstrap-vcpkg.bat"
    if (Test-Path $bootstrapFile) {
        $validVcpkg = $true
        Write-Host "Using existing vcpkg installation at $vcpkgPath"
    }
}

# 如果路径无效，使用镜像克隆新的 vcpkg
if (-not $validVcpkg) {
    $defaultVcpkgPath = "$PSScriptRoot\..\vcpkg"
    Write-Host "vcpkg installation not found, cloning new instance to $defaultVcpkgPath"
    
    # 读取镜像列表
    $mirrors = @()
    $mirrorsFile = "$PSScriptRoot\mirrors.txt"
    if (Test-Path $mirrorsFile) {
        $mirrors = Get-Content $mirrorsFile | Where-Object { $_ -notmatch '^\s*#' -and $_ -ne '' }
    } else {
        $mirrors = @("https://github.com/microsoft/vcpkg")
    }
    
    # 尝试使用镜像加速克隆
    $cloned = $false
    foreach ($mirror in $mirrors) {
        try {
            # 处理镜像URL格式
            $mirrorUrl = $mirror.Trim()
            if ($mirrorUrl -notmatch "^https?://") {
                $mirrorUrl = "https://$mirrorUrl"
            }
            
            # 确保URL以.git结尾
            $repoUrl = if ($mirrorUrl.EndsWith(".git")) {
                $mirrorUrl
            } elseif ($mirrorUrl.EndsWith("/")) {
                $mirrorUrl + "microsoft/vcpkg.git"
            } else {
                $mirrorUrl + "/microsoft/vcpkg.git"
            }
            
            Write-Host "Trying to clone from mirror: $repoUrl"
            git clone $repoUrl $defaultVcpkgPath
            
            if ($? -and (Test-Path $defaultVcpkgPath)) {
                $cloned = $true
                break
            }
        } catch {
            Write-Host "Clone from mirror $mirror failed: $_"
        }
    }
    
    # 如果所有镜像都失败，尝试原始地址
    if (-not $cloned) {
        try {
            Write-Host "All mirrors failed, trying original repository"
            git clone https://github.com/microsoft/vcpkg.git $defaultVcpkgPath
        } catch {
            Write-Error "Clone failed: $_"
            exit 1
        }
    }
    
    # 更新路径
    $vcpkgPath = $defaultVcpkgPath
    $vcpkgPath | Out-File $vcpkgPathFile -Encoding UTF8
}

# 尝试修改 hosts 文件以加速下载
try {
    Write-Host "Attempting to modify hosts file to accelerate downloads"
    
    # 检查 hosts 文件是否可写
    if (-not (Test-Path $HOSTS_FILE)) {
        Write-Host "Hosts file not found at $HOSTS_FILE"
    } else {
        # 获取当前时间戳
        $timestamp = Get-Date -Format "yyyyMMddHHmmss"
        $backupHosts = "$HOSTS_FILE.$timestamp.bak"
        
        # 创建备份
        Copy-Item -Path $HOSTS_FILE -Destination $backupHosts -Force
        Write-Host "Created hosts file backup: $backupHosts"
        
        # 读取镜像列表
        $mirrors = @()
        $mirrorsFile = "$PSScriptRoot\mirrors.txt"
        if (Test-Path $mirrorsFile) {
            $mirrors = Get-Content $mirrorsFile | Where-Object { $_ -notmatch '^\s*#' -and $_ -ne '' }
        } else {
            Write-Host "No mirrors.txt found, using default mirrors"
            $mirrors = @("gh.ddlc.top", "github.com.cnpmjs.org", "hub.fastgit.org")
        }
        
        # 解析镜像的IP地址
        $mirrorIps = @()
        foreach ($mirror in $mirrors) {
            try {
                $ip = Resolve-DnsName $mirror -Type A | Select-Object -ExpandProperty IPAddress -First 1
                if ($ip) {
                    Write-Host "Resolved $mirror => $ip"
                    $mirrorIps += $ip
                }
            } catch {
                Write-Host "Failed to resolve $mirror: $_"
            }
        }
        
        # 添加映射到 hosts 文件
        $hostsContent = Get-Content $HOSTS_FILE -Raw
        $newLines = @()
        
        foreach ($ip in $mirrorIps) {
            $newLines += "$ip github.com"
            $newLines += "$ip raw.githubusercontent.com"
            $newLines += "$ip objects.githubusercontent.com"
            $newLines += "$ip codeload.github.com"
        }
        
        # 添加注释和映射
        $hostsContent = "# Added by zzcc build script at $(Get-Date)`r`n" + 
                        ($newLines -join "`r`n") + 
                        "`r`n`r`n" + $hostsContent
        
        Set-Content -Path $HOSTS_FILE -Value $hostsContent -Encoding UTF8
        Write-Host "Hosts file updated with GitHub mirrors"
    }
} catch {
    Write-Host "Failed to modify hosts file: $_"
    Write-Host "Downloads may be slower without hosts modification"
}

# 构建 vcpkg（如果尚未构建）
$vcpkgExe = Join-Path $vcpkgPath "vcpkg.exe"
if (-not (Test-Path $vcpkgExe)) {
    Write-Host "Building vcpkg..."
    Push-Location $vcpkgPath
    Start-Process ".\bootstrap-vcpkg.bat" -Wait
    Pop-Location
}

# 使用 manifest 模式安装依赖
Write-Host "Installing dependencies using manifest mode..."
Push-Location $VCPKG_MANIFEST_DIR  # 切换到 vcpkg.json 所在目录
Start-Process $vcpkgExe -ArgumentList "install" -Wait
Pop-Location

# 尝试恢复原始 hosts 文件
try {
    if ($backupHosts -and (Test-Path $backupHosts)) {
        Write-Host "Restoring original hosts file"
        Copy-Item -Path $backupHosts -Destination $HOSTS_FILE -Force
        Remove-Item $backupHosts
    }
} catch {
    Write-Host "Failed to restore hosts file: $_"
    Write-Host "Please check $backupHosts and restore manually if needed"
}

# 复制 DLL 文件
if (-not (Test-Path $NATIVE_DIR)) {
    New-Item -ItemType Directory -Path $NATIVE_DIR | Out-Null
}

Write-Host "Copying DLL files..."
$dllSourceDir = Join-Path $vcpkgPath "installed\x64-windows\bin"
if (Test-Path $dllSourceDir) {
    $dllFiles = Get-ChildItem -Path $dllSourceDir -Filter "*.dll"
    foreach ($dll in $dllFiles) {
        Copy-Item -Path $dll.FullName -Destination $NATIVE_DIR -Force
    }
}

# 复制 debug DLL 文件
$dllDebugSourceDir = Join-Path $vcpkgPath "installed\x64-windows\debug\bin"
if (Test-Path $dllDebugSourceDir) {
    $dllDebugFiles = Get-ChildItem -Path $dllDebugSourceDir -Filter "*.dll"
    foreach ($dll in $dllDebugFiles) {
        Copy-Item -Path $dll.FullName -Destination $NATIVE_DIR -Force
    }
}

Write-Host "Dependency setup completed!"