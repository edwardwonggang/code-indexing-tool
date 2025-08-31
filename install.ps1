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

# 函数：安装Chocolatey
function Install-Chocolatey {
    Write-Host "📦 检查Chocolatey..." -ForegroundColor Yellow
    if (-not (Test-Command choco)) {
        Write-Host "⬇️ 安装Chocolatey..." -ForegroundColor Blue
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        refreshenv
    } else {
        Write-Host "✅ Chocolatey已安装" -ForegroundColor Green
    }
}

# 函数：安装Python依赖
function Install-PythonDependencies {
    Write-Host "🐍 安装Python依赖..." -ForegroundColor Yellow
    
    # 检查Python
    if (-not (Test-Command python)) {
        Write-Error "❌ Python未安装，请先安装Python 3.10+"
        return $false
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
        try {
            # 下载并安装CodeQL CLI
            $codeqlVersion = "2.15.4"
            $codeqlUrl = "https://github.com/github/codeql-cli-binaries/releases/download/v$codeqlVersion/codeql-win64.zip"
            $codeqlDir = "C:\tools\codeql"
            $codeqlZip = "$env:TEMP\codeql.zip"
            
            Write-Host "⬇️ 下载CodeQL CLI..." -ForegroundColor Blue
            Invoke-WebRequest -Uri $codeqlUrl -OutFile $codeqlZip
            
            Write-Host "📦 解压CodeQL..." -ForegroundColor Blue
            Expand-Archive -Path $codeqlZip -DestinationPath "C:\tools" -Force
            
            # 添加到PATH
            $env:PATH += ";$codeqlDir\codeql"
            [Environment]::SetEnvironmentVariable("PATH", $env:PATH, [EnvironmentVariableTarget]::Machine)
            
            # 清理临时文件
            Remove-Item $codeqlZip -Force
            
            # 下载CodeQL查询包
            Write-Host "⬇️ 下载CodeQL查询包..." -ForegroundColor Blue
            $codeqlQueriesDir = "$codeqlDir\codeql-queries"
            if (-not (Test-Path $codeqlQueriesDir)) {
                git clone https://github.com/github/codeql.git $codeqlQueriesDir --depth 1
            }
            
            Write-Host "✅ CodeQL安装完成" -ForegroundColor Green
        } catch {
            Write-Host "❌ CodeQL安装失败: $_" -ForegroundColor Red
        }
    } else {
        Write-Host "✅ CodeQL已安装" -ForegroundColor Green
    }
    
    # 安装其他LSP服务器
    Write-Host "📌 安装LSP服务器..." -ForegroundColor Blue
    
    # Python LSP服务器
    if (-not (Get-Command "pylsp" -ErrorAction SilentlyContinue)) {
        Write-Host "⬇️ 安装Python LSP服务器..." -ForegroundColor Blue
        try {
            pip install python-lsp-server[all] -q
            Write-Host "✅ Python LSP服务器安装完成" -ForegroundColor Green
        } catch {
            Write-Host "❌ Python LSP服务器安装失败: $_" -ForegroundColor Red
        }
    } else {
        Write-Host "✅ Python LSP服务器已安装" -ForegroundColor Green
    }
    
    # TypeScript/JavaScript LSP服务器
    if (-not (Get-Command "typescript-language-server" -ErrorAction SilentlyContinue)) {
        Write-Host "⬇️ 安装TypeScript LSP服务器..." -ForegroundColor Blue
        try {
            npm install -g typescript-language-server typescript
            Write-Host "✅ TypeScript LSP服务器安装完成" -ForegroundColor Green
        } catch {
            Write-Host "❌ TypeScript LSP服务器安装失败: $_" -ForegroundColor Red
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
            try {
                & $bashPath -lc "pacman -S --noconfirm cscope"
                
                # 自动添加到PATH
                $msys2BinPath = Split-Path $bashPath
                $currentPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
                if ($currentPath -notlike "*$msys2BinPath*") {
                    Write-Host "🔄 添加MSYS2到系统PATH..." -ForegroundColor Blue
                    [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$msys2BinPath", "Machine")
                    $env:PATH = "$env:PATH;$msys2BinPath"
                    Write-Host "✅ 已添加到系统PATH: $msys2BinPath" -ForegroundColor Green
                }
                Write-Host "✅ Cscope安装完成" -ForegroundColor Green
            } catch {
                Write-Host "❌ Cscope安装失败: $_" -ForegroundColor Red
            }
        } else {
            Write-Host "❌ 找不到MSYS2 bash" -ForegroundColor Red
        }
    } else {
        Write-Host "✅ Cscope已安装" -ForegroundColor Green
    }
}

# 函数：验证安装
function Test-Installation {
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

# 主安装流程
try {
    Write-Host "🔍 系统检查..." -ForegroundColor Yellow
    
    # 检查PowerShell版本
    $psVersion = $PSVersionTable.PSVersion
    Write-Host "📍 PowerShell版本: $psVersion" -ForegroundColor Cyan
    
    # 检查管理员权限
    if (-not (Test-AdminRights)) {
        Write-Host "⚠️ 建议以管理员身份运行以避免权限问题" -ForegroundColor Yellow
        if (-not $Force) {
            $response = Read-Host "继续安装? (y/N)"
            if ($response -ne 'y' -and $response -ne 'Y') {
                Write-Host "❌ 安装取消" -ForegroundColor Red
                exit 1
            }
        }
    }
    
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
    
    # 验证安装
    Write-Host "🔍 最终验证..." -ForegroundColor Yellow
    $installSuccess = Test-Installation
    
    if ($installSuccess) {
        Write-Host ""
        Write-Host "🎉 安装完成！" -ForegroundColor Green
        Write-Host "=====================================" -ForegroundColor Green
        Write-Host "✅ 所有组件已成功安装并验证" -ForegroundColor Green
        Write-Host ""
        Write-Host "🚀 快速开始：" -ForegroundColor Cyan
        Write-Host "   python mcp_server_working.py" -ForegroundColor White
        Write-Host ""
        Write-Host "📖 详细文档：请查看 README.md" -ForegroundColor Cyan
    } else {
        Write-Host ""
        Write-Host "❌ 安装未完全成功" -ForegroundColor Red
        Write-Host "请检查上面的错误信息并手动解决" -ForegroundColor Yellow
        exit 1
    }
    
} catch {
    Write-Host "❌ 安装过程中发生错误: $_" -ForegroundColor Red
    Write-Host "请检查错误信息并重试" -ForegroundColor Yellow
    exit 1
} 