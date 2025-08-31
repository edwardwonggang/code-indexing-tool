"""
索引管理器

提供索引的创建、加载、更新和删除功能
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger

from ..utils.config import Config


class IndexManager:
    """索引管理器，处理索引的生命周期管理"""
    
    def __init__(self, config: Config):
        """
        初始化索引管理器
        
        Args:
            config: 配置对象
        """
        self.config = config
        self.metadata_dir = Path(config.get_metadata_dir())
        self.data_dir = Path(config.get_data_dir())
        
        # 确保目录存在
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"IndexManager initialized: metadata={self.metadata_dir}, data={self.data_dir}")
    
    def create_index(self, project_path: str, index_name: Optional[str] = None) -> Dict[str, Any]:
        """
        创建新的索引
        
        Args:
            project_path: 项目路径
            index_name: 索引名称，如果不提供则使用项目名
            
        Returns:
            索引创建结果
        """
        project_path_obj = Path(project_path).resolve()
        
        if not index_name:
            index_name = project_path_obj.name
            
        # 检查索引是否已存在
        if self.index_exists(index_name):
            logger.warning(f"Index '{index_name}' already exists")
            return {"status": "exists", "index_name": index_name}
        
        # 创建索引元数据
        metadata = {
            "index_name": index_name,
            "project_path": str(project_path_obj),
            "created_at": self._get_current_timestamp(),
            "updated_at": self._get_current_timestamp(),
            "status": "created",
            "files_count": 0,
            "symbols_count": 0
        }
        
        self._save_metadata(index_name, metadata)
        logger.info(f"Created index '{index_name}' for project: {project_path}")
        
        return {"status": "created", "index_name": index_name, "metadata": metadata}
    
    def get_index_metadata(self, index_name: str) -> Optional[Dict[str, Any]]:
        """
        获取索引元数据
        
        Args:
            index_name: 索引名称
            
        Returns:
            索引元数据，如果不存在返回None
        """
        metadata_file = self.metadata_dir / f"{index_name}.json"
        
        if not metadata_file.exists():
            return None
            
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load metadata for '{index_name}': {e}")
            return None
    
    def update_index_metadata(self, index_name: str, updates: Dict[str, Any]) -> bool:
        """
        更新索引元数据
        
        Args:
            index_name: 索引名称
            updates: 要更新的字段
            
        Returns:
            更新是否成功
        """
        metadata = self.get_index_metadata(index_name)
        if not metadata:
            logger.error(f"Index '{index_name}' not found")
            return False
        
        # 更新字段
        metadata.update(updates)
        metadata["updated_at"] = self._get_current_timestamp()
        
        return self._save_metadata(index_name, metadata)
    
    def list_indexes(self) -> List[Dict[str, Any]]:
        """
        列出所有索引
        
        Returns:
            索引列表
        """
        indexes = []
        
        for metadata_file in self.metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    indexes.append(metadata)
            except Exception as e:
                logger.error(f"Failed to load metadata from {metadata_file}: {e}")
                
        return sorted(indexes, key=lambda x: x.get("updated_at", ""))
    
    def index_exists(self, index_name: str) -> bool:
        """
        检查索引是否存在
        
        Args:
            index_name: 索引名称
            
        Returns:
            索引是否存在
        """
        metadata_file = self.metadata_dir / f"{index_name}.json"
        return metadata_file.exists()
    
    def delete_index(self, index_name: str) -> bool:
        """
        删除索引
        
        Args:
            index_name: 索引名称
            
        Returns:
            删除是否成功
        """
        try:
            # 删除元数据文件
            metadata_file = self.metadata_dir / f"{index_name}.json"
            if metadata_file.exists():
                metadata_file.unlink()
                logger.info(f"Deleted metadata for index '{index_name}'")
            
            # 删除数据目录（如果存在特定于索引的数据）
            index_data_dir = self.data_dir / index_name
            if index_data_dir.exists():
                shutil.rmtree(index_data_dir)
                logger.info(f"Deleted data directory for index '{index_name}'")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete index '{index_name}': {e}")
            return False
    
    def get_index_statistics(self, index_name: str) -> Optional[Dict[str, Any]]:
        """
        获取索引统计信息
        
        Args:
            index_name: 索引名称
            
        Returns:
            统计信息
        """
        metadata = self.get_index_metadata(index_name)
        if not metadata:
            return None
        
        stats = {
            "index_name": index_name,
            "files_count": metadata.get("files_count", 0),
            "symbols_count": metadata.get("symbols_count", 0),
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at"),
            "status": metadata.get("status", "unknown")
        }
        
        return stats
    
    def _save_metadata(self, index_name: str, metadata: Dict[str, Any]) -> bool:
        """
        保存索引元数据
        
        Args:
            index_name: 索引名称
            metadata: 元数据
            
        Returns:
            保存是否成功
        """
        metadata_file = self.metadata_dir / f"{index_name}.json"
        
        try:
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Failed to save metadata for '{index_name}': {e}")
            return False
    
    def _get_current_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def clear_index(self, index_name: Optional[str] = None) -> bool:
        """
        清空索引数据
        
        Args:
            index_name: 要清空的索引名称，如果为None则清空所有索引
            
        Returns:
            清空是否成功
        """
        try:
            if index_name:
                # 清空特定索引
                if not self.index_exists(index_name):
                    logger.warning(f"Index '{index_name}' does not exist")
                    return False
                
                # 重置元数据中的计数器
                metadata = self.get_index_metadata(index_name)
                if metadata:
                    metadata.update({
                        "files_count": 0,
                        "symbols_count": 0,
                        "status": "cleared",
                        "updated_at": self._get_current_timestamp()
                    })
                    self._save_metadata(index_name, metadata)
                
                # 清空对应的数据目录
                index_data_dir = self.data_dir / index_name
                if index_data_dir.exists():
                    shutil.rmtree(index_data_dir)
                    index_data_dir.mkdir(parents=True, exist_ok=True)
                
                logger.info(f"Cleared index '{index_name}'")
                return True
            else:
                # 清空所有索引
                for metadata_file in self.metadata_dir.glob("*.json"):
                    index_name = metadata_file.stem
                    self.clear_index(index_name)
                
                logger.info("Cleared all indexes")
                return True
                
        except Exception as e:
            logger.error(f"Failed to clear index: {e}")
            return False

    def save_index_metadata(self, project_path: str, metadata: Dict[str, Any]) -> bool:
        """
        保存索引元数据（兼容性方法）
        
        Args:
            project_path: 项目路径
            metadata: 元数据
            
        Returns:
            保存是否成功
        """
        try:
            # 从项目路径获取索引名称
            project_path_obj = Path(project_path).resolve()
            index_name = project_path_obj.name
            
            # 检查索引是否存在，如果不存在就创建
            if not self.get_index_metadata(index_name):
                logger.info(f"索引 '{index_name}' 不存在，正在创建新索引")
                # 创建基础元数据
                base_metadata = {
                    "project_path": str(project_path_obj),
                    "created_at": self._get_current_timestamp(),
                }
                base_metadata.update(metadata)
                return self._save_metadata(index_name, base_metadata)
            else:
                # 更新现有索引元数据
                return self.update_index_metadata(index_name, metadata)
            
        except Exception as e:
            logger.error(f"Failed to save index metadata: {e}")
            return False

    def is_index_valid(self, project_path: str) -> bool:
        """
        检查索引是否有效（兼容性方法）
        
        Args:
            project_path: 项目路径
            
        Returns:
            索引是否有效
        """
        try:
            project_path_obj = Path(project_path).resolve()
            index_name = project_path_obj.name
            return self.index_exists(index_name)
            
        except Exception:
            return False

    def cleanup_orphaned_data(self) -> int:
        """
        清理孤立的数据文件
        
        Returns:
            清理的文件数量
        """
        cleaned_count = 0
        
        # 获取所有存在的索引名称
        existing_indexes = set()
        for metadata_file in self.metadata_dir.glob("*.json"):
            existing_indexes.add(metadata_file.stem)
        
        # 检查数据目录中的孤立目录
        if self.data_dir.exists():
            for data_dir in self.data_dir.iterdir():
                if data_dir.is_dir() and data_dir.name not in existing_indexes:
                    try:
                        shutil.rmtree(data_dir)
                        cleaned_count += 1
                        logger.info(f"Cleaned orphaned data directory: {data_dir.name}")
                    except Exception as e:
                        logger.error(f"Failed to clean {data_dir}: {e}")
        
        return cleaned_count 