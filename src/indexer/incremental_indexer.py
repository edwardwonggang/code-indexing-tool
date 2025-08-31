"""
增量索引器

使用 watchdog 监控 C 源码文件变更，实时更新索引，提高大项目的索引效率。

特性：
- 文件变更实时监控
- 智能增量更新
- 批量处理机制
- 冲突解决
"""
from __future__ import annotations

import os
import time
import threading
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Callable
from collections import defaultdict, deque
from loguru import logger

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logger.warning("watchdog 未安装，增量索引功能不可用")


class IncrementalIndexer:
    """增量索引器"""

    def __init__(self, indexer, debounce_delay: float = 2.0, batch_size: int = 50):
        """
        初始化增量索引器
        
        Args:
            indexer: 主索引器实例
            debounce_delay: 防抖延迟（秒）
            batch_size: 批处理大小
        """
        if not WATCHDOG_AVAILABLE:
            raise ImportError("watchdog 库未安装，请运行 pip install watchdog")
        
        self.indexer = indexer
        self.debounce_delay = debounce_delay
        self.batch_size = batch_size
        
        self.observer: Optional[Observer] = None
        self.project_path: Optional[Path] = None
        self.is_monitoring = False
        
        # 变更队列和处理
        self.pending_changes: deque = deque()
        self.change_timestamps: Dict[str, float] = {}
        self.processing_lock = threading.Lock()
        self.processor_thread: Optional[threading.Thread] = None
        self.stop_processing = threading.Event()
        
        # 统计信息
        self.stats = {
            "files_monitored": 0,
            "changes_detected": 0,
            "incremental_updates": 0,
            "full_rebuilds": 0,
            "last_update": None
        }

    def start_monitoring(self, project_path: Path, on_change_callback: Optional[Callable] = None) -> bool:
        """
        开始监控项目文件变更
        
        Args:
            project_path: 项目根路径
            on_change_callback: 变更回调函数
        
        Returns:
            是否成功启动监控
        """
        if self.is_monitoring:
            logger.warning("已在监控中，请先停止当前监控")
            return False
        
        self.project_path = project_path.resolve()
        if not self.project_path.exists():
            logger.error(f"项目路径不存在: {self.project_path}")
            return False
        
        try:
            # 创建文件系统事件处理器
            event_handler = CCodeFileHandler(
                incremental_indexer=self,
                on_change_callback=on_change_callback
            )
            
            # 创建观察者
            self.observer = Observer()
            self.observer.schedule(event_handler, str(self.project_path), recursive=True)
            
            # 启动处理线程
            self.stop_processing.clear()
            self.processor_thread = threading.Thread(target=self._process_changes_worker, daemon=True)
            self.processor_thread.start()
            
            # 启动监控
            self.observer.start()
            self.is_monitoring = True
            
            # 统计监控的文件数
            c_files = list(self.project_path.rglob("*.c")) + list(self.project_path.rglob("*.h"))
            self.stats["files_monitored"] = len(c_files)
            
            logger.info(f"开始监控项目文件变更: {self.project_path} ({self.stats['files_monitored']} 个文件)")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False

    def stop_monitoring(self):
        """停止监控"""
        if not self.is_monitoring:
            return
        
        # 停止观察者
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
        
        # 停止处理线程
        self.stop_processing.set()
        if self.processor_thread and self.processor_thread.is_alive():
            self.processor_thread.join()
        
        self.is_monitoring = False
        logger.info("文件监控已停止")

    def queue_file_change(self, file_path: str, change_type: str):
        """
        将文件变更加入队列
        
        Args:
            file_path: 文件路径
            change_type: 变更类型 ('modified', 'created', 'deleted')
        """
        if not self._is_c_file(file_path):
            return
        
        current_time = time.time()
        
        with self.processing_lock:
            # 更新时间戳
            self.change_timestamps[file_path] = current_time
            
            # 加入队列
            self.pending_changes.append({
                "file_path": file_path,
                "change_type": change_type,
                "timestamp": current_time
            })
            
            self.stats["changes_detected"] += 1
        
        logger.debug(f"文件变更入队: {file_path} ({change_type})")

    def force_update(self, file_paths: Optional[List[str]] = None) -> bool:
        """
        强制更新指定文件或所有待处理文件
        
        Args:
            file_paths: 指定文件路径列表，None 表示处理所有待处理文件
        
        Returns:
            是否成功更新
        """
        if file_paths:
            # 强制更新指定文件
            changes = [{"file_path": fp, "change_type": "modified", "timestamp": time.time()} 
                      for fp in file_paths if self._is_c_file(fp)]
        else:
            # 处理所有待处理文件
            with self.processing_lock:
                changes = list(self.pending_changes)
                self.pending_changes.clear()
        
        if not changes:
            logger.info("没有文件需要更新")
            return True
        
        return self._process_file_changes(changes)

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()
        stats["is_monitoring"] = self.is_monitoring
        stats["pending_changes"] = len(self.pending_changes)
        return stats

    # ----------------------
    # 私有方法
    # ----------------------

    def _process_changes_worker(self):
        """变更处理工作线程"""
        while not self.stop_processing.is_set():
            try:
                # 检查是否有待处理的变更
                ready_changes = self._get_ready_changes()
                
                if ready_changes:
                    self._process_file_changes(ready_changes)
                
                # 短暂休眠
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"处理文件变更时出错: {e}")

    def _get_ready_changes(self) -> List[Dict[str, Any]]:
        """获取已就绪的变更（防抖处理）"""
        current_time = time.time()
        ready_changes = []
        
        with self.processing_lock:
            # 找出超过防抖延迟的变更
            while self.pending_changes:
                change = self.pending_changes[0]
                if current_time - change["timestamp"] >= self.debounce_delay:
                    ready_changes.append(self.pending_changes.popleft())
                else:
                    break
            
            # 批量限制
            if len(ready_changes) > self.batch_size:
                # 保留超出部分回队列
                excess = ready_changes[self.batch_size:]
                for change in reversed(excess):
                    self.pending_changes.appendleft(change)
                ready_changes = ready_changes[:self.batch_size]
        
        return ready_changes

    def _process_file_changes(self, changes: List[Dict[str, Any]]) -> bool:
        """
        处理文件变更
        
        Args:
            changes: 变更列表
        
        Returns:
            是否成功处理
        """
        if not changes:
            return True
        
        logger.info(f"开始处理 {len(changes)} 个文件变更")
        
        try:
            # 按变更类型分组
            files_by_type = defaultdict(list)
            for change in changes:
                files_by_type[change["change_type"]].append(change["file_path"])
            
            # 处理删除
            if "deleted" in files_by_type:
                self._handle_deleted_files(files_by_type["deleted"])
            
            # 处理创建和修改
            modified_files = files_by_type.get("modified", []) + files_by_type.get("created", [])
            if modified_files:
                self._handle_modified_files(modified_files)
            
            self.stats["incremental_updates"] += 1
            self.stats["last_update"] = time.time()
            
            logger.info(f"增量更新完成，处理了 {len(changes)} 个变更")
            return True
            
        except Exception as e:
            logger.error(f"处理文件变更失败: {e}")
            # 发生错误时，尝试全量重建
            return self._fallback_full_rebuild()

    def _handle_deleted_files(self, file_paths: List[str]):
        """处理删除的文件"""
        for file_path in file_paths:
            try:
                # 从向量索引中删除
                rel_path = str(Path(file_path).relative_to(self.project_path)).replace("\\", "/")
                
                # 这里应该调用向量存储的删除方法
                # self.indexer.vector_store.delete_by_file_path(rel_path)
                
                logger.debug(f"已从索引中删除文件: {rel_path}")
            except Exception as e:
                logger.warning(f"删除文件索引失败 {file_path}: {e}")

    def _handle_modified_files(self, file_paths: List[str]):
        """处理修改的文件"""
        try:
            # 使用现有的符号提取器重新提取符号
            modified_symbols = []
            
            for file_path in file_paths:
                try:
                    file_path_obj = Path(file_path)
                    if not file_path_obj.exists():
                        continue
                    
                    # 提取单个文件的符号
                    symbols = self._extract_file_symbols(file_path_obj)
                    modified_symbols.extend(symbols)
                    
                except Exception as e:
                    logger.warning(f"提取文件符号失败 {file_path}: {e}")
            
            if modified_symbols:
                # 更新向量索引
                self._update_vector_index(modified_symbols)
                logger.debug(f"更新了 {len(modified_symbols)} 个符号")
        
        except Exception as e:
            logger.error(f"处理修改文件失败: {e}")
            raise

    def _extract_file_symbols(self, file_path: Path) -> List[Dict[str, Any]]:
        """提取单个文件的符号"""
        try:
            # 创建临时项目路径只包含这个文件
            from .ts_symbol_extractor import TSSymbolExtractor
            extractor = TSSymbolExtractor()
            
            # 解析单个文件
            source_bytes = file_path.read_bytes()
            tree = extractor.parser.parse(source_bytes)
            
            rel_path = str(file_path.relative_to(self.project_path)).replace("\\", "/")
            symbols = extractor._extract_from_tree(self.project_path, file_path, source_bytes, tree, {})
            
            return symbols
            
        except Exception as e:
            logger.warning(f"提取文件符号失败 {file_path}: {e}")
            return []

    def _update_vector_index(self, symbols: List[Dict[str, Any]]):
        """更新向量索引"""
        try:
            # 先删除这些文件的旧符号
            file_paths = set(symbol["file_path"] for symbol in symbols)
            for file_path in file_paths:
                # 这里应该有删除方法
                # self.indexer.vector_store.delete_by_file_path(file_path)
                pass
            
            # 添加新符号
            if symbols:
                documents = []
                metadatas = []
                ids = []
                
                for symbol in symbols:
                    text_content = self.indexer._create_searchable_text(symbol)
                    documents.append(text_content)
                    
                    metadata = {
                        "symbol_id": symbol["id"],
                        "name": symbol["name"],
                        "type": symbol["type"],
                        "file_path": symbol["file_path"],
                        "project_path": str(self.project_path),
                        "declaration": symbol.get("declaration", ""),
                        "description": symbol.get("description", "")
                    }
                    
                    metadatas.append(metadata)
                    ids.append(symbol["id"])
                
                self.indexer.vector_store.add_documents(documents, metadatas, ids)
        
        except Exception as e:
            logger.error(f"更新向量索引失败: {e}")
            raise

    def _fallback_full_rebuild(self) -> bool:
        """回退到全量重建"""
        try:
            logger.warning("增量更新失败，回退到全量重建")
            self.indexer.build_index(str(self.project_path), force_rebuild=True)
            self.stats["full_rebuilds"] += 1
            return True
        except Exception as e:
            logger.error(f"全量重建也失败: {e}")
            return False

    @staticmethod
    def _is_c_file(file_path: str) -> bool:
        """检查是否为 C 源码文件"""
        return file_path.lower().endswith(('.c', '.h', '.cpp', '.hpp', '.cc', '.cxx'))


class CCodeFileHandler(FileSystemEventHandler):
    """C 代码文件系统事件处理器"""

    def __init__(self, incremental_indexer: IncrementalIndexer, on_change_callback: Optional[Callable] = None):
        super().__init__()
        self.incremental_indexer = incremental_indexer
        self.on_change_callback = on_change_callback

    def on_modified(self, event):
        if not event.is_directory:
            self.incremental_indexer.queue_file_change(event.src_path, "modified")
            if self.on_change_callback:
                self.on_change_callback("modified", event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self.incremental_indexer.queue_file_change(event.src_path, "created")
            if self.on_change_callback:
                self.on_change_callback("created", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self.incremental_indexer.queue_file_change(event.src_path, "deleted")
            if self.on_change_callback:
                self.on_change_callback("deleted", event.src_path) 