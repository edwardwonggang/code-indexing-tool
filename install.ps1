# C代码索引工具 - 自动安装脚本
# 适用于Windows 10/11 + PowerShell

param(
    [switch]$SkipPython,
    [switch]$SkipTools,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host "🚀 C代码索引工具 - 自动安装脚本" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green

# 函数：检查管理员权限
function Test-AdminRights {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# 函数：检查命令是否存在
function Test-Command {
    param($Command)
    $null = Get-Command $Command -ErrorAction SilentlyContinue
    return $?
}

# 函数：刷新环境变量
function Update-Environment {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    Write-Host "🔄 环境变量已刷新" -ForegroundColor Blue
}

# 函数：重试执行命令
function Invoke-WithRetry {
    param(
        [scriptblock]$ScriptBlock,
        [int]$MaxRetries = 3,
        [int]$DelaySeconds = 5
    )
    
    for ($i = 1; $i -le $MaxRetries; $i++) {
        try {
            Write-Host "🔄 尝试第 $i 次..." -ForegroundColor Yellow
            & $ScriptBlock
            return $true
        } catch {
            Write-Host "❌ 第 $i 次尝试失败: $_" -ForegroundColor Red
            if ($i -lt $MaxRetries) {
                Write-Host "⏳ 等待 ${DelaySeconds} 秒后重试..." -ForegroundColor Yellow
                Start-Sleep $DelaySeconds
            }
        }
    }
    return $false
}

# 函数：检查前置依赖
function Test-Prerequisites {
    Write-Host "🔍 检查前置依赖..." -ForegroundColor Yellow
    
    $missing = @()
    
    # 检查PowerShell版本
    if ($PSVersionTable.PSVersion.Major -lt 5) {
        $missing += "PowerShell 5.0+"
    }
    
    # 检查.NET Framework
    try {
        $dotNetVersion = Get-ItemProperty "HKLM:SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full\" -Name Release -ErrorAction Stop
        if ($dotNetVersion.Release -lt 461808) {
            $missing += ".NET Framework 4.7.2+"
        }
    } catch {
        $missing += ".NET Framework 4.7.2+"
    }
    
    if ($missing.Count -gt 0) {
        Write-Host "❌ 缺少前置依赖:" -ForegroundColor Red
        $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
        return $false
    }
    
    Write-Host "✅ 前置依赖检查通过" -ForegroundColor Green
    return $true
}

# 函数：安装Chocolatey
function Install-Chocolatey {
    Write-Host "📦 检查Chocolatey..." -ForegroundColor Yellow
    if (-not (Test-Command choco)) {
        Write-Host "⬇️ 安装Chocolatey..." -ForegroundColor Blue
        
        $success = Invoke-WithRetry -ScriptBlock {
            Set-ExecutionPolicy Bypass -Scope Process -Force
            [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
            Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        }
        
        if ($success) {
            Update-Environment
            Write-Host "✅ Chocolatey安装完成" -ForegroundColor Green
        } else {
            throw "Chocolatey安装失败"
        }
    } else {
        Write-Host "✅ Chocolatey已安装" -ForegroundColor Green
    }
}

# 函数：安装Python依赖
function Install-PythonDependencies {
    Write-Host "🐍 安装Python依赖..." -ForegroundColor Yellow
    
    # 检查Python
    if (-not (Test-Command python)) {
        Write-Host "⬇️ 尝试通过Chocolatey安装Python..." -ForegroundColor Blue
        try {
            choco install python -y
            Update-Environment
            if (-not (Test-Command python)) {
                Write-Error "❌ Python安装失败，请手动安装Python 3.10+"
                return $false
            }
        } catch {
            Write-Error "❌ Python自动安装失败，请手动安装Python 3.10+"
            return $false
        }
    }
    
    # 检查pip
    if (-not (Test-Command pip)) {
        Write-Host "⬇️ 安装pip..." -ForegroundColor Blue
        try {
            python -m ensurepip --upgrade
            Update-Environment
        } catch {
            Write-Error "❌ pip安装失败"
            return $false
        }
    }
    
    $pythonVersion = python --version 2>&1
    Write-Host "📍 Python版本: $pythonVersion" -ForegroundColor Cyan
    
    # 升级pip
    Write-Host "⬆️ 升级pip..." -ForegroundColor Blue
    python -m pip install --upgrade pip
    
    # 安装依赖
    Write-Host "📦 安装项目依赖..." -ForegroundColor Blue
    try {
        python -m pip install -r requirements.txt
        Write-Host "✅ Python依赖安装完成" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "❌ Python依赖安装失败: $_" -ForegroundColor Red
        return $false
    }
}

# 函数：安装外部工具
function Install-ExternalTools {
    Write-Host "🔧 安装外部工具..." -ForegroundColor Yellow
    
    # 安装Universal CTags
    Write-Host "📌 安装Universal CTags..." -ForegroundColor Blue
    if (-not (Test-Command ctags)) {
        try {
            choco install universal-ctags -y
            Write-Host "✅ Universal CTags安装完成" -ForegroundColor Green
        } catch {
            Write-Host "❌ Universal CTags安装失败: $_" -ForegroundColor Red
        }
    } else {
        Write-Host "✅ Universal CTags已安装" -ForegroundColor Green
    }
    
    # 安装LLVM (包含clangd)
    Write-Host "📌 安装LLVM (clangd)..." -ForegroundColor Blue
    if (-not (Test-Command clangd)) {
        try {
            choco install llvm -y
            Write-Host "✅ LLVM (clangd)安装完成" -ForegroundColor Green
        } catch {
            Write-Host "❌ LLVM安装失败: $_" -ForegroundColor Red
        }
    } else {
        Write-Host "✅ LLVM (clangd)已安装" -ForegroundColor Green
    }
    
    # 安装Cppcheck (C/C++静态分析)
    Write-Host "📌 安装Cppcheck..." -ForegroundColor Blue
    if (-not (Test-Command cppcheck)) {
        try {
            choco install cppcheck -y
            Write-Host "✅ Cppcheck安装完成" -ForegroundColor Green
        } catch {
            Write-Host "❌ Cppcheck安装失败: $_" -ForegroundColor Red
        }
    } else {
        Write-Host "✅ Cppcheck已安装" -ForegroundColor Green
    }
    
    # 安装CodeQL (GitHub高级代码分析)
    Write-Host "📌 安装CodeQL..." -ForegroundColor Blue
    if (-not (Test-Command codeql)) {
        $success = Invoke-WithRetry -ScriptBlock {
            # 下载并安装CodeQL CLI
            $codeqlVersion = "2.15.4"
            $codeqlUrl = "https://github.com/github/codeql-cli-binaries/releases/download/v$codeqlVersion/codeql-win64.zip"
            $codeqlDir = "C:\tools\codeql"
            $codeqlZip = "$env:TEMP\codeql.zip"
            
            # 创建目录
            if (-not (Test-Path "C:\tools")) {
                New-Item -Path "C:\tools" -ItemType Directory -Force
            }
            
            Write-Host "⬇️ 下载CodeQL CLI..." -ForegroundColor Blue
            # 使用更强大的下载方法
            $webClient = New-Object System.Net.WebClient
            $webClient.DownloadFile($codeqlUrl, $codeqlZip)
            
            Write-Host "📦 解压CodeQL..." -ForegroundColor Blue
            Expand-Archive -Path $codeqlZip -DestinationPath "C:\tools" -Force
            
            # 添加到PATH
            $codeqlBinPath = "$codeqlDir\codeql"
            $currentPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
            if ($currentPath -notlike "*$codeqlBinPath*") {
                [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$codeqlBinPath", "Machine")
                $env:PATH = "$env:PATH;$codeqlBinPath"
            }
            
            # 清理临时文件
            Remove-Item $codeqlZip -Force -ErrorAction SilentlyContinue
            
            # 验证安装
            Update-Environment
            if (-not (Test-Command codeql)) {
                throw "CodeQL命令验证失败"
            }
        }
        
        if ($success) {
            # 下载CodeQL查询包（可选，不影响主要功能）
            try {
                Write-Host "⬇️ 下载CodeQL查询包..." -ForegroundColor Blue
                $codeqlQueriesDir = "C:\tools\codeql\codeql-queries"
                if (-not (Test-Path $codeqlQueriesDir) -and (Test-Command git)) {
                    git clone https://github.com/github/codeql.git $codeqlQueriesDir --depth 1
                }
            } catch {
                Write-Host "⚠️ CodeQL查询包下载失败，但不影响主要功能" -ForegroundColor Yellow
            }
            Write-Host "✅ CodeQL安装完成" -ForegroundColor Green
        } else {
            Write-Host "❌ CodeQL安装失败" -ForegroundColor Red
        }
    } else {
        Write-Host "✅ CodeQL已安装" -ForegroundColor Green
    }
    
    # 安装其他LSP服务器
    Write-Host "📌 安装LSP服务器..." -ForegroundColor Blue
    
    # 检查并安装Node.js（npm的前置依赖）
    if (-not (Test-Command npm)) {
        Write-Host "⬇️ 安装Node.js..." -ForegroundColor Blue
        try {
            choco install nodejs -y
            Update-Environment
        } catch {
            Write-Host "❌ Node.js安装失败" -ForegroundColor Red
        }
    }
    
    # Python LSP服务器
    if (-not (Get-Command "pylsp" -ErrorAction SilentlyContinue)) {
        Write-Host "⬇️ 安装Python LSP服务器..." -ForegroundColor Blue
        $success = Invoke-WithRetry -ScriptBlock {
            pip install python-lsp-server[all] --upgrade
        }
        if ($success) {
            Write-Host "✅ Python LSP服务器安装完成" -ForegroundColor Green
        } else {
            Write-Host "❌ Python LSP服务器安装失败" -ForegroundColor Red
        }
    } else {
        Write-Host "✅ Python LSP服务器已安装" -ForegroundColor Green
    }
    
    # TypeScript/JavaScript LSP服务器
    if (-not (Get-Command "typescript-language-server" -ErrorAction SilentlyContinue)) {
        Write-Host "⬇️ 安装TypeScript LSP服务器..." -ForegroundColor Blue
        $success = Invoke-WithRetry -ScriptBlock {
            if (Test-Command npm) {
                npm install -g typescript-language-server typescript
            } else {
                throw "npm不可用"
            }
        }
        if ($success) {
            Update-Environment
            Write-Host "✅ TypeScript LSP服务器安装完成" -ForegroundColor Green
        } else {
            Write-Host "❌ TypeScript LSP服务器安装失败" -ForegroundColor Red
        }
    } else {
        Write-Host "✅ TypeScript LSP服务器已安装" -ForegroundColor Green
    }
    
    # 安装MSYS2 (用于cscope)
    Write-Host "📌 检查MSYS2..." -ForegroundColor Blue
    if (-not (Test-Command cscope)) {
        if (-not (Test-Path "C:\msys64") -and -not (Test-Path "C:\tools\msys64")) {
            Write-Host "⬇️ 安装MSYS2..." -ForegroundColor Blue
            try {
                choco install msys2 -y
                Write-Host "✅ MSYS2安装完成" -ForegroundColor Green
            } catch {
                Write-Host "❌ MSYS2安装失败: $_" -ForegroundColor Red
                return $false
            }
        }
        
        # 安装cscope
        Write-Host "📌 在MSYS2中安装cscope..." -ForegroundColor Blue
        $msys2Paths = @("C:\msys64\usr\bin\bash.exe", "C:\tools\msys64\usr\bin\bash.exe")
        $bashPath = $null
        
        foreach ($path in $msys2Paths) {
            if (Test-Path $path) {
                $bashPath = $path
                break
            }
        }
        
        if ($bashPath) {
            $success = Invoke-WithRetry -ScriptBlock {
                # 更新MSYS2包管理器
                & $bashPath -lc "pacman -Sy --noconfirm"
                # 安装cscope
                & $bashPath -lc "pacman -S --noconfirm cscope"
            }
            
            if ($success) {
                # 自动添加到PATH
                $msys2BinPath = Split-Path $bashPath
                $currentPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
                if ($currentPath -notlike "*$msys2BinPath*") {
                    Write-Host "🔄 添加MSYS2到系统PATH..." -ForegroundColor Blue
                    [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$msys2BinPath", "Machine")
                    $env:PATH = "$env:PATH;$msys2BinPath"
                    Write-Host "✅ 已添加到系统PATH: $msys2BinPath" -ForegroundColor Green
                }
                
                # 验证cscope安装
                Update-Environment
                if (Test-Command cscope) {
                    Write-Host "✅ Cscope安装完成" -ForegroundColor Green
                } else {
                    throw "Cscope安装验证失败"
                }
            } else {
                Write-Host "❌ Cscope安装失败" -ForegroundColor Red
            }
        } else {
            Write-Host "❌ 找不到MSYS2 bash" -ForegroundColor Red
        }
    } else {
        Write-Host "✅ Cscope已安装" -ForegroundColor Green
    }
}

# 函数：验证安装
function Verify-Installation {
    Write-Host "🔍 验证安装..." -ForegroundColor Yellow
    
    $allGood = $true
    
    # 检查Python包
    Write-Host "📌 检查Python包..." -ForegroundColor Blue
    try {
        python -c "import tree_sitter; print('✅ Tree-sitter: 已安装')" -ErrorAction Stop
        python -c "import tree_sitter_languages; print('✅ Tree-sitter Languages: 已安装')" -ErrorAction Stop
        python -c "from pygls.client import LanguageClient; print('✅ pygls: 已安装')" -ErrorAction Stop
        python -c "import chromadb; print('✅ ChromaDB: 已安装')" -ErrorAction Stop
    } catch {
        Write-Host "❌ Python包检查失败: $_" -ForegroundColor Red
        $allGood = $false
    }
    
    # 检查外部工具
    Write-Host "📌 检查外部工具..." -ForegroundColor Blue
    
    if (Test-Command ctags) {
        $ctagsVersion = ctags --version 2>&1 | Select-Object -First 1
        Write-Host "✅ CTags: $ctagsVersion" -ForegroundColor Green
    } else {
        Write-Host "❌ CTags未找到" -ForegroundColor Red
        $allGood = $false
    }
    
    if (Test-Command cscope) {
        $cscopeVersion = cscope -V 2>&1 | Select-Object -First 1
        Write-Host "✅ Cscope: $cscopeVersion" -ForegroundColor Green
    } else {
        Write-Host "❌ Cscope未找到" -ForegroundColor Red
        $allGood = $false
    }
    
    if (Test-Command clangd) {
        $clangdVersion = clangd --version 2>&1 | Select-Object -First 1
        Write-Host "✅ Clangd: $clangdVersion" -ForegroundColor Green
    } else {
        Write-Host "❌ Clangd未找到" -ForegroundColor Red
        $allGood = $false
    }
    
    if (Test-Command codeql) {
        $codeqlVersion = codeql version 2>&1 | Select-Object -First 1
        Write-Host "✅ CodeQL: $codeqlVersion" -ForegroundColor Green
    } else {
        Write-Host "❌ CodeQL未找到" -ForegroundColor Red
        $allGood = $false
    }
    
    if (Test-Command pylsp) {
        Write-Host "✅ Python LSP服务器已安装" -ForegroundColor Green
    } else {
        Write-Host "❌ Python LSP服务器未找到" -ForegroundColor Red
        $allGood = $false
    }
    
    if (Test-Command typescript-language-server) {
        Write-Host "✅ TypeScript LSP服务器已安装" -ForegroundColor Green
    } else {
        Write-Host "❌ TypeScript LSP服务器未找到" -ForegroundColor Red
        $allGood = $false
    }
    
    if (Test-Command cppcheck) {
        $cppcheckVersion = cppcheck --version 2>&1 | Select-Object -First 1
        Write-Host "✅ Cppcheck: $cppcheckVersion" -ForegroundColor Green
    } else {
        Write-Host "❌ Cppcheck未找到" -ForegroundColor Red
        $allGood = $false
    }
    
    return $allGood
}

# 主程序开始
Write-Host ""

# 检查前置依赖
if (-not (Test-Prerequisites)) {
    Write-Error "❌ 前置依赖检查失败，请先安装必需的软件"
    exit 1
}

Write-Host "🔍 检查管理员权限..." -ForegroundColor Yellow
if (-not (Test-AdminRights)) {
    Write-Error "❌ 需要管理员权限才能安装工具。请以管理员身份运行PowerShell。"
    exit 1
}

try {
    
    # 安装Chocolatey
    if (-not $SkipTools) {
        Install-Chocolatey
    }
    
    # 安装Python依赖
    if (-not $SkipPython) {
        $pythonSuccess = Install-PythonDependencies
        if (-not $pythonSuccess) {
            Write-Host "❌ Python依赖安装失败，请检查错误信息" -ForegroundColor Red
            exit 1
        }
    }
    
    # 安装外部工具
    if (-not $SkipTools) {
        Install-ExternalTools
        
        # 自动添加常用工具路径到PATH
        Write-Host "🔄 更新系统PATH环境变量..." -ForegroundColor Blue
        $pathsToAdd = @(
            "C:\Program Files\LLVM\bin",
            "C:\Program Files\Cppcheck"
        )
        
        $currentPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
        $pathUpdated = $false
        
        foreach ($newPath in $pathsToAdd) {
            if ((Test-Path $newPath) -and ($currentPath -notlike "*$newPath*")) {
                Write-Host "➕ 添加到PATH: $newPath" -ForegroundColor Cyan
                $currentPath += ";$newPath"
                $env:PATH += ";$newPath"
                $pathUpdated = $true
            }
        }
        
        if ($pathUpdated) {
            [Environment]::SetEnvironmentVariable("PATH", $currentPath, "Machine")
            Write-Host "✅ PATH环境变量已更新" -ForegroundColor Green
        }
        
        # 刷新环境变量
        Write-Host "🔄 刷新环境变量..." -ForegroundColor Blue
        refreshenv
    }
    
    # 最终环境变量刷新
    Write-Host "🔄 刷新环境变量..." -ForegroundColor Blue
    Update-Environment
    
    # 运行最终验证
    Write-Host ""
    Write-Host "🔍 运行最终验证..." -ForegroundColor Yellow
    
    # 等待一下让系统稳定
    Start-Sleep 2
    
    if (Verify-Installation) {
        Write-Host ""
        Write-Host "🎉 安装完成！所有工具都已成功安装。" -ForegroundColor Green
        Write-Host ""
        Write-Host "📋 安装的工具列表:" -ForegroundColor Cyan
        Write-Host "  ✅ CodeQL - GitHub高级代码分析" -ForegroundColor Green
        Write-Host "  ✅ Cppcheck - C/C++静态分析" -ForegroundColor Green
        Write-Host "  ✅ Python LSP - Python语言服务器" -ForegroundColor Green
        Write-Host "  ✅ TypeScript LSP - JS/TS语言服务器" -ForegroundColor Green
        Write-Host "  ✅ Clangd LSP - C/C++语言服务器" -ForegroundColor Green
        Write-Host "  ✅ Universal CTags - 符号提取" -ForegroundColor Green
        Write-Host "  ✅ Cscope - 调用关系分析" -ForegroundColor Green
        Write-Host ""
        Write-Host "🚀 下一步: 运行 'python mcp_server_working.py' 启动MCP服务器" -ForegroundColor Cyan
        Write-Host "💡 提示：重启PowerShell窗口以确保所有环境变量生效。" -ForegroundColor Blue
    } else {
        Write-Host ""
        Write-Host "⚠️ 安装完成，但某些工具验证失败。" -ForegroundColor Yellow
        Write-Host "🔧 解决方案:" -ForegroundColor Cyan
        Write-Host "  1. 重启PowerShell窗口" -ForegroundColor White
        Write-Host "  2. 运行 'python install.py' 重新验证" -ForegroundColor White
        Write-Host "  3. 手动检查失败的工具安装" -ForegroundColor White
    }
    
} catch {
    Write-Host "❌ 安装过程中发生错误: $_" -ForegroundColor Red
    Write-Host "请检查错误信息并重试" -ForegroundColor Yellow
    exit 1
} 