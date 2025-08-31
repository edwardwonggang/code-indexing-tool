"""
日志配置工具

配置系统日志输出和格式
"""

import sys
from pathlib import Path
from loguru import logger
from typing import Optional


def setup_logger(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_console: bool = True,
    enable_file: bool = True
):
    """
    设置日志配置
    
    Args:
        log_level: 日志级别
        log_file: 日志文件路径
        enable_console: 是否启用控制台输出
        enable_file: 是否启用文件输出
    """
    # 移除默认处理器
    logger.remove()
    
    # 控制台输出
    if enable_console:
        logger.add(
            sys.stderr,
            level=log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                   "<level>{message}</level>",
            colorize=True
        )
    
    # 文件输出
    if enable_file and log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            str(log_path),
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | "
                   "{level: <8} | "
                   "{name}:{function}:{line} - "
                   "{message}",
            rotation="10 MB",
            retention="7 days",
            compression="zip"
        )
    
    logger.info(f"日志系统已初始化，级别: {log_level}")


def get_logger(name: str = __name__):
    """
    获取日志记录器
    
    Args:
        name: 记录器名称
        
    Returns:
        日志记录器
    """
    return logger.bind(name=name) 