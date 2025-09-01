"""
配置管理模块

管理系统配置参数和设置
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv
import json


class Config:
    """配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置
        
        Args:
            config_file: 配置文件路径，如果为None则使用默认配置
        """
        # 加载环境变量
        load_dotenv()
        
        # 默认配置
        self._defaults = {
            # 向量存储配置
            'embedding_model': 'all-MiniLM-L6-v2',
            'collection_name': 'c_code_symbols',
            'chroma_data_dir': './data/chroma',
            
            # 索引配置
            'index_metadata_dir': './data/metadata',
            'supported_extensions': ['.c', '.h', '.cpp', '.hpp', '.cc', '.cxx'],
            'max_file_size_mb': 100,  # 针对大型项目放宽文件大小限制

            # 性能配置 - 针对16GB内存和2小时分析时间优化
            'max_workers': 12,
            'timeout_seconds': 7200,  # 2小时
            'batch_size': 20,
            'memory_threshold_gb': 8,  # 8GB内存阈值
            
            # API配置
            'api_host': '127.0.0.1',
            'api_port': 8000,
            'api_workers': 1,
            
            # 日志配置
            'log_level': 'INFO',
            'log_file': './logs/indexer.log',
            
            # 搜索配置
            'default_search_limit': 20,
            'max_search_limit': 100,
            'similarity_threshold': 0.5,
            
            # CLDK配置 - 针对大型项目优化
            'cldk_timeout': 7200,  # 2小时超时
            'cldk_max_memory': '12GB',  # 增加内存限制
        }
        
        # 从环境变量覆盖配置
        self._load_from_env()
        
        # 从配置文件覆盖配置
        if config_file:
            self._load_from_file(config_file)
    
    def _load_from_env(self):
        """从环境变量加载配置"""
        env_mappings = {
            'EMBEDDING_MODEL': 'embedding_model',
            'COLLECTION_NAME': 'collection_name',
            'CHROMA_DATA_DIR': 'chroma_data_dir',
            'INDEX_METADATA_DIR': 'index_metadata_dir',
            'API_HOST': 'api_host',
            'API_PORT': 'api_port',
            'API_WORKERS': 'api_workers',
            'LOG_LEVEL': 'log_level',
            'LOG_FILE': 'log_file',
            'DEFAULT_SEARCH_LIMIT': 'default_search_limit',
            'MAX_SEARCH_LIMIT': 'max_search_limit',
            'SIMILARITY_THRESHOLD': 'similarity_threshold',
        }
        
        for env_key, config_key in env_mappings.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                # 类型转换
                if config_key in ['api_port', 'api_workers', 'default_search_limit', 'max_search_limit']:
                    try:
                        self._defaults[config_key] = int(env_value)
                    except ValueError:
                        pass
                elif config_key in ['similarity_threshold']:
                    try:
                        self._defaults[config_key] = float(env_value)
                    except ValueError:
                        pass
                else:
                    self._defaults[config_key] = env_value
    
    def _load_from_file(self, config_file: str):
        """从配置文件加载配置"""
        try:
            config_path = Path(config_file)
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                
                # 更新配置
                for key, value in file_config.items():
                    if key in self._defaults:
                        self._defaults[key] = value
        except Exception as e:
            print(f"加载配置文件失败: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        return self._defaults.get(key, default)
    
    def set(self, key: str, value: Any):
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
        """
        self._defaults[key] = value
    
    def update(self, config_dict: Dict[str, Any]):
        """
        批量更新配置
        
        Args:
            config_dict: 配置字典
        """
        self._defaults.update(config_dict)
    
    def save_to_file(self, config_file: str):
        """
        保存配置到文件
        
        Args:
            config_file: 配置文件路径
        """
        try:
            config_path = Path(config_file)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self._defaults, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置文件失败: {e}")
    
    def get_data_dir(self) -> Path:
        """获取数据目录路径"""
        data_dir = Path(self.get('chroma_data_dir'))
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    
    def get_metadata_dir(self) -> Path:
        """获取元数据目录路径"""
        metadata_dir = Path(self.get('index_metadata_dir'))
        metadata_dir.mkdir(parents=True, exist_ok=True)
        return metadata_dir
    
    def get_metadata_path(self, project_path: Path) -> Path:
        """
        获取项目元数据文件路径
        
        Args:
            project_path: 项目路径
            
        Returns:
            元数据文件路径
        """
        # 生成项目标识符
        project_id = str(project_path).replace(':', '_').replace('\\', '_').replace('/', '_')
        metadata_file = f"{project_id}_metadata.json"
        return self.get_metadata_dir() / metadata_file
    
    def get_log_dir(self) -> Path:
        """获取日志目录路径"""
        log_file = Path(self.get('log_file'))
        log_dir = log_file.parent
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir
    
    def is_supported_file(self, file_path: Path) -> bool:
        """
        检查文件是否支持索引
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否支持
        """
        if not file_path.is_file():
            return False
        
        # 检查扩展名
        supported_extensions = self.get('supported_extensions', [])
        if file_path.suffix.lower() not in supported_extensions:
            return False
        
        # 检查文件大小
        try:
            max_size_mb = self.get('max_file_size_mb', 10)
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > max_size_mb:
                return False
        except Exception:
            return False
        
        return True
    
    def get_supported_files(self, directory: Path) -> list:
        """
        获取目录下所有支持的文件
        
        Args:
            directory: 目录路径
            
        Returns:
            支持的文件列表
        """
        supported_files = []
        
        if not directory.is_dir():
            return supported_files
        
        # 递归遍历目录
        for file_path in directory.rglob('*'):
            if self.is_supported_file(file_path):
                supported_files.append(file_path)
        
        return supported_files
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self._defaults.copy()
    
    def __getattr__(self, name: str) -> Any:
        """支持点号访问配置"""
        if name in self._defaults:
            return self._defaults[name]
        raise AttributeError(f"配置项 '{name}' 不存在")
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"Config({len(self._defaults)} items)" 