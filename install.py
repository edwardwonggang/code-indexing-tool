#!/usr/bin/env python3
"""
C代码索引工具 - 自动安装脚本
适用于多平台的Python安装脚本
"""

import os
import sys
import subprocess
import platform
import shutil
from pathlib import Path


def run_command(cmd, shell=False, check=True):
    """运行命令并返回结果"""
    try:
        # Windows编码兼容性
        encoding = 'utf-8' if platform.system() != 'Windows' else 'gbk'
        
        if isinstance(cmd, str):
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, 
                                  check=check, encoding=encoding, errors='replace')
        else:
            result = subprocess.run(cmd, capture_output=True, text=True, check=check, 
                                  shell=shell, encoding=encoding, errors='replace')
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout if e.stdout else "", e.stderr if e.stderr else ""
    except Exception as e:
        return False, "", str(e)


def check_command_exists(cmd):
    """检查命令是否存在"""
    return shutil.which(cmd) is not None


def check_python_version():
    """检查Python版本"""
    version = sys.version_info
    print(f"📍 Python版本: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print("❌ 需要Python 3.10或更高版本")
        return False
    return True


def install_python_dependencies():
    """安装Python依赖"""
    print("🐍 安装Python依赖...")
    
    # 升级pip
    print("⬆️ 升级pip...")
    success, stdout, stderr = run_command([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    if not success:
        print(f"❌ pip升级失败: {stderr}")
        return False
    
    # 安装依赖
    print("📦 安装项目依赖...")
    requirements_file = Path(__file__).parent / "requirements.txt"
    if not requirements_file.exists():
        print("❌ requirements.txt文件不存在")
        return False
    
    success, stdout, stderr = run_command([sys.executable, "-m", "pip", "install", "-r", str(requirements_file)])
    if not success:
        print(f"❌ 依赖安装失败: {stderr}")
        return False
    
    print("✅ Python依赖安装完成")
    return True


def add_to_path_windows(path_to_add):
    """在Windows上添加路径到系统PATH"""
    try:
        import winreg
        
        # 读取当前系统PATH
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as key:
            current_path, _ = winreg.QueryValueEx(key, "PATH")
        
        # 检查路径是否已存在
        if path_to_add.lower() in current_path.lower():
            print(f"✅ 路径已存在于PATH中: {path_to_add}")
            return True
        
        # 添加新路径
        new_path = current_path + ";" + path_to_add
        
        # 写入注册表
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
        
        # 更新当前进程的环境变量
        os.environ['PATH'] = os.environ.get('PATH', '') + ";" + path_to_add
        
        print(f"✅ 已添加到系统PATH: {path_to_add}")
        return True
    except Exception as e:
        print(f"❌ 添加PATH失败: {e}")
        print(f"⚠️ 请手动将 {path_to_add} 添加到系统PATH")
        return False


def refresh_path_windows():
    """刷新Windows PATH环境变量"""
    try:
        # 广播环境变量更改消息
        import ctypes
        from ctypes import wintypes
        
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        
        result = ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
            ctypes.byref(wintypes.DWORD())
        )
        
        if result:
            print("✅ 环境变量已刷新")
        else:
            print("⚠️ 环境变量刷新可能未完成，建议重启终端")
            
    except Exception as e:
        print(f"⚠️ 环境变量刷新失败: {e}")


def install_windows_tools():
    """安装Windows工具"""
    print("🔧 安装Windows外部工具...")
    
    # 检查Chocolatey
    if not check_command_exists("choco"):
        print("❌ 需要先安装Chocolatey")
        print("请以管理员身份运行PowerShell并执行:")
        print("Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))")
        return False
    
    tools = [
        ("universal-ctags", "ctags"),
        ("llvm", "clangd"),
        ("cppcheck", "cppcheck"),  # C/C++静态分析工具
        ("msys2", None)  # msys2需要特殊处理
    ]
    
    paths_to_add = []
    
    for package, command in tools:
        if command and check_command_exists(command):
            print(f"✅ {package}已安装")
            continue
        
        print(f"📌 安装{package}...")
        success, stdout, stderr = run_command(f"choco install {package} -y")
        if success:
            print(f"✅ {package}安装完成")
            
            # 收集需要添加到PATH的路径
            if package == "llvm":
                paths_to_add.append(r"C:\Program Files\LLVM\bin")
            elif package == "cppcheck":
                paths_to_add.append(r"C:\Program Files\Cppcheck")
        else:
            print(f"❌ {package}安装失败: {stderr}")
    
    # 特殊处理cscope (通过MSYS2)
    if not check_command_exists("cscope"):
        print("📌 在MSYS2中安装cscope...")
        msys2_paths = [
            r"C:\tools\msys64\usr\bin\bash.exe",
            r"C:\msys64\usr\bin\bash.exe"
        ]
        
        bash_path = None
        for path in msys2_paths:
            if Path(path).exists():
                bash_path = path
                break
        
        if bash_path:
            success, stdout, stderr = run_command([bash_path, "-lc", "pacman -S --noconfirm cscope"])
            if success:
                print("✅ Cscope安装完成")
                
                # 添加MSYS2路径
                msys2_bin = str(Path(bash_path).parent)
                paths_to_add.append(msys2_bin)
            else:
                print(f"❌ Cscope安装失败: {stderr}")
        else:
            print("❌ 找不到MSYS2 bash")
    
    # 自动添加所有路径到系统PATH
    if paths_to_add:
        print("🔄 更新系统PATH环境变量...")
        for path in paths_to_add:
            if Path(path).exists():
                add_to_path_windows(path)
        
        # 刷新环境变量
        refresh_path_windows()
        
        # 立即更新当前会话的PATH
        print("🔄 刷新当前会话PATH...")
        for path in paths_to_add:
            if Path(path).exists() and path not in os.environ.get('PATH', ''):
                os.environ['PATH'] = os.environ.get('PATH', '') + ";" + path
        print("✅ 当前会话PATH已更新")
    
    return True


def install_linux_tools():
    """安装Linux工具"""
    print("🔧 安装Linux外部工具...")
    
    # 检测Linux发行版
    if Path("/etc/debian_version").exists():
        # Debian/Ubuntu
        packages = "universal-ctags cscope clang-tools"
        cmd = f"sudo apt-get update && sudo apt-get install -y {packages}"
    elif Path("/etc/redhat-release").exists():
        # RedHat/CentOS/Fedora
        packages = "ctags cscope clang-tools-extra"
        cmd = f"sudo yum install -y {packages}"
    else:
        print("❌ 不支持的Linux发行版，请手动安装: ctags, cscope, clangd")
        return False
    
    print(f"📌 执行: {cmd}")
    success, stdout, stderr = run_command(cmd, shell=True)
    if success:
        print("✅ Linux工具安装完成")
    else:
        print(f"❌ Linux工具安装失败: {stderr}")
    
    return success


def install_macos_tools():
    """安装macOS工具"""
    print("🔧 安装macOS外部工具...")
    
    # 检查Homebrew
    if not check_command_exists("brew"):
        print("❌ 需要先安装Homebrew")
        print("请执行: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
        return False
    
    packages = ["universal-ctags", "cscope", "llvm"]
    for package in packages:
        print(f"📌 安装{package}...")
        success, stdout, stderr = run_command(f"brew install {package}")
        if success:
            print(f"✅ {package}安装完成")
        else:
            print(f"❌ {package}安装失败: {stderr}")
    
    return True


def verify_installation():
    """验证安装"""
    print("🔍 验证安装...")
    
    all_good = True
    
    # 检查Python包
    print("📌 检查Python包...")
    packages = [
        ("tree_sitter", "Tree-sitter"),
        ("tree_sitter_languages", "Tree-sitter Languages"),
        ("pygls.client", "pygls"),
        ("chromadb", "ChromaDB"),
        ("sentence_transformers", "SentenceTransformers")
    ]
    
    for module, name in packages:
        try:
            __import__(module)
            print(f"✅ {name}: 已安装")
        except ImportError:
            print(f"❌ {name}: 未安装")
            all_good = False
    
    # 检查外部工具
    print("📌 检查外部工具...")
    tools = [
        ("ctags", "CTags"),
        ("cscope", "Cscope"),
        ("clangd", "Clangd")
    ]
    
    # Windows特定工具
    if platform.system() == "Windows":
        tools.append(("cppcheck", "Cppcheck"))
        tools.append(("codeql", "CodeQL"))
        # LSP服务器检查
        tools.append(("pylsp", "Python LSP"))
        tools.append(("typescript-language-server", "TypeScript LSP"))
    else:
        
    
    for cmd, name in tools:
        if check_command_exists(cmd):
            # 获取版本信息
            success, stdout, stderr = run_command([cmd, "--version"], check=False)
            if success and stdout:
                version = stdout.split('\n')[0]
                print(f"✅ {name}: {version}")
            else:
                success, stdout, stderr = run_command([cmd, "-V"], check=False)
                if success and (stdout or stderr):
                    version = (stdout or stderr).split('\n')[0]
                    print(f"✅ {name}: {version}")
                else:
                    print(f"✅ {name}: 已安装")
        else:
            print(f"❌ {name}: 未找到")
            all_good = False
    
    return all_good


def main():
    """主函数"""
    print("🚀 C代码索引工具 - 自动安装脚本")
    print("=====================================")
    
    # 检查Python版本
    if not check_python_version():
        sys.exit(1)
    
    # 检查操作系统
    system = platform.system()
    print(f"📍 操作系统: {system}")
    
    # 安装Python依赖
    if not install_python_dependencies():
        print("❌ Python依赖安装失败")
        sys.exit(1)
    
    # 根据操作系统安装外部工具
    if system == "Windows":
        install_windows_tools()
    elif system == "Linux":
        install_linux_tools()
    elif system == "Darwin":  # macOS
        install_macos_tools()
    else:
        print(f"❌ 不支持的操作系统: {system}")
    
    # 验证安装
    print("\n🔍 最终验证...")
    if verify_installation():
        print("\n🎉 安装完成！")
        print("=====================================")
        print("✅ 所有组件已成功安装并验证")
        print("\n🚀 快速开始：")
        print("   python mcp_server_working.py")
        print("\n📖 详细文档：请查看 README.md")
    else:
        print("\n❌ 安装未完全成功")
        print("请检查上面的错误信息并手动解决")
        sys.exit(1)


if __name__ == "__main__":
    main() 