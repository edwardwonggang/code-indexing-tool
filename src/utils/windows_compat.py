"""
Windows 兼容性工具

处理 Windows 系统特有的问题：
- 路径分隔符统一
- 长路径支持
- 文件编码检测和处理
- 权限问题
- 进程启动和管理
"""
from __future__ import annotations

import os
import sys
import subprocess
import tempfile
from pathlib import Path, PurePath
from typing import Optional, Union, List, Dict, Any
import chardet
from loguru import logger


class WindowsCompatibility:
    """Windows 兼容性工具类"""
    
    @staticmethod
    def is_windows() -> bool:
        """检查是否为 Windows 系统"""
        return sys.platform.startswith('win')
    
    @staticmethod
    def normalize_path(path: Union[str, Path]) -> str:
        """
        标准化路径
        - 统一使用正斜杠
        - 处理长路径问题
        - 解决 Windows 路径限制
        """
        if isinstance(path, Path):
            path = str(path)
        
        # 转换为正斜杠
        normalized = path.replace('\\', '/')
        
        # Windows 长路径支持
        if WindowsCompatibility.is_windows():
            # 如果是绝对路径且长度可能超限，添加长路径前缀
            if os.path.isabs(normalized) and len(normalized) > 200:
                if normalized.startswith('/'):
                    normalized = '\\\\?\\' + normalized[1:].replace('/', '\\')
                else:
                    normalized = '\\\\?\\' + normalized.replace('/', '\\')
        
        return normalized
    
    @staticmethod
    def safe_path_length(path: Union[str, Path]) -> bool:
        """检查路径长度是否安全"""
        path_str = str(path)
        if WindowsCompatibility.is_windows():
            # Windows 标准路径限制是 260 字符
            return len(path_str) < 250  # 留一些余量
        return True
    
    @staticmethod
    def create_short_path_if_needed(long_path: Path, base_dir: Optional[Path] = None) -> Path:
        """如果路径过长，创建短路径替代"""
        if WindowsCompatibility.safe_path_length(long_path):
            return long_path
        
        # 创建基于哈希的短路径
        import hashlib
        path_hash = hashlib.md5(str(long_path).encode()).hexdigest()[:8]
        
        if base_dir is None:
            base_dir = Path(tempfile.gettempdir()) / "codeindex_short_paths"
        
        base_dir.mkdir(parents=True, exist_ok=True)
        short_path = base_dir / f"path_{path_hash}"
        
        # 创建符号链接或复制文件
        try:
            if long_path.is_file():
                if not short_path.exists():
                    # Windows 可能不支持符号链接，回退到复制
                    if WindowsCompatibility.is_windows():
                        import shutil
                        shutil.copy2(long_path, short_path)
                    else:
                        short_path.symlink_to(long_path)
            elif long_path.is_dir():
                if not short_path.exists():
                    if WindowsCompatibility.is_windows():
                        import shutil
                        shutil.copytree(long_path, short_path)
                    else:
                        short_path.symlink_to(long_path)
        except Exception as e:
            logger.warning(f"创建短路径失败: {e}")
            return long_path
        
        return short_path
    
    @staticmethod
    def detect_file_encoding(file_path: Path) -> str:
        """
        检测文件编码
        Windows 上文件编码可能不一致
        """
        try:
            # 先尝试读取文件头
            with open(file_path, 'rb') as f:
                raw_data = f.read(10240)  # 读取前10KB
            
            # 使用 chardet 检测编码
            result = chardet.detect(raw_data)
            encoding = result.get('encoding', 'utf-8')
            confidence = result.get('confidence', 0.0)
            
            # 如果置信度低，使用默认编码
            if confidence < 0.7:
                if WindowsCompatibility.is_windows():
                    encoding = 'gbk'  # Windows 中文系统常用编码
                else:
                    encoding = 'utf-8'
            
            # 标准化编码名称
            encoding_map = {
                'gb2312': 'gbk',
                'gb18030': 'gbk',
                'iso-8859-1': 'latin1',
                'ascii': 'utf-8'
            }
            encoding = encoding_map.get(encoding.lower(), encoding)
            
            logger.debug(f"检测到文件编码: {file_path} -> {encoding} (置信度: {confidence:.2f})")
            return encoding
            
        except Exception as e:
            logger.warning(f"编码检测失败 {file_path}: {e}")
            return 'utf-8'
    
    @staticmethod
    def safe_read_text(file_path: Path) -> str:
        """
        安全读取文本文件
        自动处理编码问题
        """
        encoding = WindowsCompatibility.detect_file_encoding(file_path)
        
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            # 如果检测的编码失败，尝试其他编码
            fallback_encodings = ['utf-8', 'gbk', 'latin1', 'cp1252']
            for enc in fallback_encodings:
                try:
                    return file_path.read_text(encoding=enc)
                except UnicodeDecodeError:
                    continue
            
            # 最后手段：忽略错误
            logger.warning(f"无法正确解码文件 {file_path}，使用错误忽略模式")
            return file_path.read_text(encoding='utf-8', errors='ignore')
    
    @staticmethod
    def safe_read_bytes(file_path: Path) -> bytes:
        """安全读取二进制文件"""
        try:
            return file_path.read_bytes()
        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")
            return b""
    
    @staticmethod
    def run_command_with_encoding(
        cmd: List[str], 
        cwd: Optional[Path] = None,
        timeout: Optional[float] = None,
        encoding: Optional[str] = None
    ) -> subprocess.CompletedProcess:
        """
        运行命令并处理编码问题
        Windows 下命令输出编码可能不一致
        """
        if encoding is None:
            if WindowsCompatibility.is_windows():
                # Windows 系统尝试使用系统默认编码
                encoding = 'gbk'
            else:
                encoding = 'utf-8'
        
        try:
            # 首先尝试指定编码
            result = subprocess.run(
                cmd,
                cwd=cwd,
                timeout=timeout,
                capture_output=True,
                text=True,
                encoding=encoding,
                errors='replace'  # 替换无法解码的字符
            )
            return result
            
        except UnicodeDecodeError:
            # 如果编码失败，回退到字节模式
            logger.warning(f"命令输出编码问题，使用字节模式: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=cwd,
                timeout=timeout,
                capture_output=True,
                text=False
            )
            
            # 手动解码输出
            try:
                stdout = result.stdout.decode(encoding, errors='replace')
                stderr = result.stderr.decode(encoding, errors='replace')
            except:
                stdout = result.stdout.decode('utf-8', errors='replace')
                stderr = result.stderr.decode('utf-8', errors='replace')
            
            # 创建新的 CompletedProcess 对象
            return subprocess.CompletedProcess(
                args=result.args,
                returncode=result.returncode,
                stdout=stdout,
                stderr=stderr
            )
    
    @staticmethod
    def get_temp_dir() -> Path:
        """获取临时目录，处理权限问题"""
        temp_dirs = [
            Path(tempfile.gettempdir()),
            Path.home() / 'AppData' / 'Local' / 'Temp' if WindowsCompatibility.is_windows() else Path('/tmp'),
            Path.cwd() / 'temp'
        ]
        
        for temp_dir in temp_dirs:
            try:
                temp_dir.mkdir(parents=True, exist_ok=True)
                # 测试写权限
                test_file = temp_dir / f"test_{os.getpid()}.tmp"
                test_file.write_text("test")
                test_file.unlink()
                return temp_dir
            except Exception:
                continue
        
        raise RuntimeError("无法找到可用的临时目录")
    
    @staticmethod
    def fix_file_permissions(file_path: Path):
        """修复文件权限问题"""
        if not WindowsCompatibility.is_windows():
            try:
                # Unix/Linux 系统设置权限
                os.chmod(file_path, 0o644)
            except Exception as e:
                logger.warning(f"设置文件权限失败 {file_path}: {e}")
    
    @staticmethod
    def is_admin() -> bool:
        """检查是否有管理员权限"""
        if WindowsCompatibility.is_windows():
            try:
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin()
            except Exception:
                return False
        else:
            return os.geteuid() == 0
    
    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """获取系统信息"""
        info = {
            "platform": sys.platform,
            "is_windows": WindowsCompatibility.is_windows(),
            "python_version": sys.version,
            "is_admin": WindowsCompatibility.is_admin(),
            "temp_dir": str(WindowsCompatibility.get_temp_dir())
        }
        
        if WindowsCompatibility.is_windows():
            try:
                import platform
                info.update({
                    "windows_version": platform.win32_ver(),
                    "processor": platform.processor(),
                })
            except Exception:
                pass
        
        return info
    
    @staticmethod
    def setup_console_encoding():
        """设置控制台编码（Windows）"""
        if WindowsCompatibility.is_windows():
            try:
                # 设置控制台输出编码为 UTF-8
                import locale
                import codecs
                
                # 尝试设置 UTF-8 编码
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8')
                    sys.stderr.reconfigure(encoding='utf-8')
                
                logger.debug("Windows 控制台编码设置完成")
            except Exception as e:
                logger.warning(f"设置控制台编码失败: {e}")


# 全局函数，便于使用
def normalize_path(path: Union[str, Path]) -> str:
    """标准化路径的便捷函数"""
    return WindowsCompatibility.normalize_path(path)

def safe_read_text(file_path: Path) -> str:
    """安全读取文本文件的便捷函数"""
    return WindowsCompatibility.safe_read_text(file_path)

def run_command_safe(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """安全运行命令的便捷函数"""
    # 特殊处理MSYS2工具路径
    if sys.platform == "win32" and cmd:
        if cmd[0] == 'cscope':
            # 检查多个可能的cscope路径
            possible_paths = [
                r'C:\tools\msys64\usr\bin\cscope.exe',
                r'C:\msys64\usr\bin\cscope.exe',
                r'C:\msys32\usr\bin\cscope.exe',
                r'C:\cygwin64\bin\cscope.exe',
                r'C:\cygwin\bin\cscope.exe'
            ]
            
            # 先尝试找到实际存在的cscope路径
            cscope_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    cscope_path = path
                    break
            
            if cscope_path:
                cmd = [cscope_path] + cmd[1:]
            # 如果都没找到，保持原命令不变，让系统PATH处理
    
    # 设置编码参数，确保正确处理MSYS2输出
    encoding = kwargs.pop('encoding', None)
    if encoding is None:
        if sys.platform == "win32":
            # Windows下MSYS2工具通常输出UTF-8
            encoding = 'utf-8'
        else:
            encoding = 'utf-8'
    
    return WindowsCompatibility.run_command_with_encoding(cmd, encoding=encoding, **kwargs)

# 模块初始化时设置编码
if WindowsCompatibility.is_windows():
    WindowsCompatibility.setup_console_encoding() 