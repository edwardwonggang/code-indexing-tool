"""
性能优化工具

提供多种性能优化机制：
- 并行文件处理
- 内存优化
- 缓存机制
- 批量处理
- 向量化优化
"""
from __future__ import annotations

import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from functools import wraps, lru_cache
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Iterator, Union
import multiprocessing as mp
from dataclasses import dataclass
import gc
import psutil

from loguru import logger


@dataclass
class PerformanceMetrics:
    """性能指标"""
    start_time: float
    end_time: Optional[float] = None
    cpu_usage_start: float = 0.0
    cpu_usage_end: float = 0.0
    memory_usage_start: float = 0.0
    memory_usage_end: float = 0.0
    files_processed: int = 0
    symbols_extracted: int = 0
    
    @property
    def duration(self) -> float:
        """执行时长"""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time
    
    @property
    def throughput(self) -> float:
        """处理吞吐量（文件数/秒）"""
        if self.duration > 0:
            return self.files_processed / self.duration
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "duration": self.duration,
            "cpu_usage_start": self.cpu_usage_start,
            "cpu_usage_end": self.cpu_usage_end,
            "memory_usage_start": self.memory_usage_start,
            "memory_usage_end": self.memory_usage_end,
            "files_processed": self.files_processed,
            "symbols_extracted": self.symbols_extracted,
            "throughput": self.throughput
        }


class PerformanceOptimizer:
    """性能优化器"""
    
    def __init__(self, max_workers: Optional[int] = None, use_processes: bool = False):
        """
        初始化性能优化器
        
        Args:
            max_workers: 最大工作线程/进程数
            use_processes: 是否使用进程池（CPU密集型任务）
        """
        self.cpu_count = mp.cpu_count()
        # 针对16GB内存优化：增加并发数
        self.max_workers = max_workers or min(self.cpu_count * 2, 16)
        self.use_processes = use_processes

        # 内存监控 - 针对16GB内存优化
        self.process = psutil.Process()
        self.memory_threshold = 8 * 1024 * 1024 * 1024  # 8GB阈值 (16GB的50%)
        
        # 缓存管理
        self._cache = {}
        self._cache_hits = 0
        self._cache_misses = 0
        
        logger.info(f"性能优化器初始化: {self.max_workers} workers, "
                   f"{'processes' if use_processes else 'threads'}, "
                   f"CPU cores: {self.cpu_count}")

    def process_files_parallel(
        self,
        files: List[Path],
        processor_func: Callable[[Path], Any],
        batch_size: int = 30,  # 针对大型项目减小批大小
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[Any]:
        """
        并行处理文件列表
        
        Args:
            files: 文件路径列表
            processor_func: 处理函数
            batch_size: 批处理大小
            progress_callback: 进度回调函数
        
        Returns:
            处理结果列表
        """
        metrics = PerformanceMetrics(
            start_time=time.time(),
            cpu_usage_start=self.process.cpu_percent(),
            memory_usage_start=self.process.memory_info().rss / 1024 / 1024
        )
        
        results = []
        total_files = len(files)
        
        logger.info(f"开始并行处理 {total_files} 个文件，批大小: {batch_size}")
        
        try:
            # 分批处理，避免内存占用过高
            for i in range(0, total_files, batch_size):
                batch = files[i:i + batch_size]
                batch_results = self._process_batch(batch, processor_func)
                results.extend(batch_results)
                
                # 更新进度
                processed = min(i + batch_size, total_files)
                if progress_callback:
                    progress_callback(processed, total_files)
                
                # 内存检查和清理
                self._check_and_cleanup_memory()
                
                logger.debug(f"处理进度: {processed}/{total_files} "
                           f"({processed/total_files*100:.1f}%)")
        
        except Exception as e:
            logger.error(f"并行处理失败: {e}")
            raise
        
        finally:
            # 记录性能指标
            metrics.end_time = time.time()
            metrics.cpu_usage_end = self.process.cpu_percent()
            metrics.memory_usage_end = self.process.memory_info().rss / 1024 / 1024
            metrics.files_processed = total_files
            
            logger.info(f"并行处理完成: {metrics.duration:.2f}s, "
                       f"吞吐量: {metrics.throughput:.1f} files/s, "
                       f"内存峰值: {metrics.memory_usage_end:.1f}MB")
        
        return results

    def _process_batch(self, batch: List[Path], processor_func: Callable[[Path], Any]) -> List[Any]:
        """处理单个批次"""
        if self.use_processes:
            # 进程池处理（CPU密集型）
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(processor_func, file_path): file_path 
                          for file_path in batch}
                
                results = []
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result is not None:
                            results.append(result)
                    except Exception as e:
                        file_path = futures[future]
                        logger.warning(f"处理文件失败 {file_path}: {e}")
                
                return results
        else:
            # 线程池处理（I/O密集型）
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(processor_func, file_path): file_path 
                          for file_path in batch}
                
                results = []
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result is not None:
                            results.append(result)
                    except Exception as e:
                        file_path = futures[future]
                        logger.warning(f"处理文件失败 {file_path}: {e}")
                
                return results

    def process_symbols_batch(
        self, 
        symbols: List[Dict[str, Any]], 
        batch_size: int = 1000
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        批量处理符号，减少内存占用
        
        Args:
            symbols: 符号列表
            batch_size: 批处理大小
        
        Yields:
            符号批次
        """
        for i in range(0, len(symbols), batch_size):
            yield symbols[i:i + batch_size]

    def optimize_vector_storage(
        self, 
        documents: List[str], 
        metadatas: List[Dict[str, Any]], 
        ids: List[str],
        chunk_size: int = 500
    ) -> Iterator[tuple]:
        """
        优化向量存储的批量插入
        
        Args:
            documents: 文档列表
            metadatas: 元数据列表
            ids: ID列表
            chunk_size: 分块大小
        
        Yields:
            (文档块, 元数据块, ID块) 元组
        """
        total_docs = len(documents)
        logger.info(f"优化向量存储：{total_docs} 个文档，分块大小：{chunk_size}")
        
        for i in range(0, total_docs, chunk_size):
            end_idx = min(i + chunk_size, total_docs)
            
            doc_chunk = documents[i:end_idx]
            metadata_chunk = metadatas[i:end_idx]
            id_chunk = ids[i:end_idx]
            
            # 内存优化：清理较长的文档内容
            optimized_docs = []
            for doc in doc_chunk:
                if len(doc) > 2000:  # 超过2000字符的文档进行截断
                    optimized_docs.append(doc[:2000] + "...")
                else:
                    optimized_docs.append(doc)
            
            yield optimized_docs, metadata_chunk, id_chunk
            
            # 强制垃圾回收
            if i % (chunk_size * 5) == 0:
                gc.collect()

    def cache_result(self, key: str, value: Any, ttl: int = 3600):
        """缓存结果"""
        expires_at = time.time() + ttl
        self._cache[key] = {"value": value, "expires_at": expires_at}

    def get_cached_result(self, key: str) -> Optional[Any]:
        """获取缓存结果"""
        if key in self._cache:
            cached = self._cache[key]
            if time.time() < cached["expires_at"]:
                self._cache_hits += 1
                return cached["value"]
            else:
                # 过期的缓存
                del self._cache[key]
        
        self._cache_misses += 1
        return None

    def clear_cache(self):
        """清理缓存"""
        self._cache.clear()
        gc.collect()

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total_requests if total_requests > 0 else 0.0
        
        return {
            "cache_size": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate
        }

    def _check_and_cleanup_memory(self):
        """检查和清理内存"""
        memory_usage = self.process.memory_info().rss
        
        if memory_usage > self.memory_threshold:
            logger.warning(f"内存使用过高: {memory_usage / 1024 / 1024:.1f}MB，执行清理")
            
            # 清理缓存
            cache_size_before = len(self._cache)
            self._cache.clear()
            
            # 强制垃圾回收
            gc.collect()
            
            memory_after = self.process.memory_info().rss
            logger.info(f"内存清理完成: {memory_after / 1024 / 1024:.1f}MB "
                       f"(节省 {(memory_usage - memory_after) / 1024 / 1024:.1f}MB), "
                       f"清理缓存 {cache_size_before} 项")

    def measure_performance(self, operation_name: str = "operation"):
        """性能测量装饰器"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                start_memory = self.process.memory_info().rss / 1024 / 1024
                
                try:
                    result = func(*args, **kwargs)
                    success = True
                except Exception as e:
                    logger.error(f"{operation_name} 执行失败: {e}")
                    success = False
                    raise
                finally:
                    end_time = time.time()
                    end_memory = self.process.memory_info().rss / 1024 / 1024
                    duration = end_time - start_time
                    
                    logger.info(f"{operation_name} 性能指标: "
                               f"耗时 {duration:.2f}s, "
                               f"内存 {start_memory:.1f}MB -> {end_memory:.1f}MB "
                               f"({'成功' if success else '失败'})")
                
                return result
            return wrapper
        return decorator

    def get_optimal_batch_size(self, total_items: int, item_size_bytes: int = 1024) -> int:
        """
        根据可用内存计算最优批次大小
        
        Args:
            total_items: 总项目数
            item_size_bytes: 单个项目的大小（字节）
        
        Returns:
            推荐的批次大小
        """
        available_memory = psutil.virtual_memory().available
        safe_memory = available_memory * 0.3  # 使用30%的可用内存
        
        optimal_batch = int(safe_memory / item_size_bytes)
        
        # 限制在合理范围内
        optimal_batch = max(10, min(optimal_batch, 1000))
        
        logger.debug(f"计算最优批次大小: {optimal_batch} "
                    f"(可用内存: {available_memory / 1024 / 1024:.1f}MB)")
        
        return optimal_batch

    def enable_memory_profiling(self, interval: float = 10.0):
        """启用内存监控"""
        def monitor_memory():
            while True:
                memory_info = self.process.memory_info()
                cpu_percent = self.process.cpu_percent()
                
                logger.debug(f"内存监控: RSS={memory_info.rss / 1024 / 1024:.1f}MB, "
                           f"VMS={memory_info.vms / 1024 / 1024:.1f}MB, "
                           f"CPU={cpu_percent:.1f}%")
                
                time.sleep(interval)
        
        monitor_thread = threading.Thread(target=monitor_memory, daemon=True)
        monitor_thread.start()
        logger.info(f"内存监控已启用，间隔 {interval}s")


# 全局性能优化器实例
_global_optimizer: Optional[PerformanceOptimizer] = None

def get_performance_optimizer() -> PerformanceOptimizer:
    """获取全局性能优化器实例"""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = PerformanceOptimizer()
    return _global_optimizer

def parallel_map(func: Callable, items: List[Any], max_workers: Optional[int] = None) -> List[Any]:
    """并行映射函数"""
    optimizer = get_performance_optimizer()
    if max_workers:
        original_workers = optimizer.max_workers
        optimizer.max_workers = max_workers
    
    try:
        if isinstance(items[0], Path):
            return optimizer.process_files_parallel(items, func)
        else:
            # 对于非文件类型，使用简单的线程池
            with ThreadPoolExecutor(max_workers=optimizer.max_workers) as executor:
                return list(executor.map(func, items))
    finally:
        if max_workers:
            optimizer.max_workers = original_workers

def cached(ttl: int = 3600):
    """缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            key = f"{func.__name__}:{hash((args, tuple(sorted(kwargs.items()))))}"
            
            optimizer = get_performance_optimizer()
            cached_result = optimizer.get_cached_result(key)
            
            if cached_result is not None:
                return cached_result
            
            result = func(*args, **kwargs)
            optimizer.cache_result(key, result, ttl)
            return result
        return wrapper
    return decorator 