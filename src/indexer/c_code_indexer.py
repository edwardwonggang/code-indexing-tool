"""
C代码索引构建器

使用 Tree-sitter + Lizard 进行无编译代码分析，避免复杂的clang依赖。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

from loguru import logger

from ..storage.vector_store import VectorStore
from ..storage.graph_store import GraphStore
from ..storage.index_manager import IndexManager
from ..utils.config import Config
from .ts_symbol_extractor import TSSymbolExtractor  # 无编译主力
from .ctags_extractor import CTagsExtractor       # 备用
from .call_graph_extractor import CallGraphExtractor


class CCodeIndexer:
    """C代码索引构建器（Tree-sitter + Lizard）"""

    def __init__(self):
        """初始化索引构建器"""
        # 创建默认配置
        from ..utils.config import Config
        self.config = Config()
        
        # 向量存储
        self.vector_store = VectorStore()
        
        # 图存储
        self.graph_store = GraphStore()
        
        # 索引管理器
        self.index_manager = IndexManager(self.config)
        
        # 符号提取器 (TSSymbolExtractor)
        self.ts_symbol_extractor = TSSymbolExtractor()
        
        # TSQuery 提取器 (可选)
        try:
            from .ts_query_extractor import TSQueryExtractor
            self.ts_query_extractor = TSQueryExtractor()
        except Exception as e:
            logger.warning(f"TSQueryExtractor 不可用: {e}")
            self.ts_query_extractor = None
        
        # CTags 提取器
        try:
            from .ctags_extractor import CTagsExtractor
            self.ctags_extractor = CTagsExtractor()
        except Exception as e:
            logger.warning(f"CTagsExtractor 不可用: {e}")
            self.ctags_extractor = None
        
        # 调用图提取器
        from .call_graph_extractor import CallGraphExtractor
        self.call_graph_extractor = CallGraphExtractor()
        
        logger.info("C代码索引构建器（Tree-sitter + Lizard）初始化完成")

    def build_index(self, project_path: Path, force_rebuild: bool = False) -> Dict[str, Any]:
        """
        构建C代码索引
        
        Args:
            project_path: C项目根目录
            force_rebuild: 是否强制重建索引
            
        Returns:
            索引构建结果
        """
        start_time = time.time()
        logger.info(f"开始构建C代码索引: {project_path}")
        
        try:
            # 检查现有索引
            project_id = str(project_path.name)
            
            if not force_rebuild and self.index_manager.is_index_valid(project_id):
                logger.info("发现有效索引，使用缓存")
                cached_result = self.index_manager.get_index_metadata(project_id)
                if cached_result:
                    return cached_result
            
            # 1. 提取符号
            symbols = self._extract_symbols(project_path)
            
            # 2. 提取调用图
            call_graph = self._extract_call_graph(project_path, symbols)
            
            # 3. 构建向量索引
            self._build_vector_index(symbols)
            
            # 4. 构建图索引
            graph_data = self._build_graph_index(symbols, call_graph)
            
            # 统计文件
            source_files = list(project_path.rglob("*.c")) + list(project_path.rglob("*.h"))
            
            # 构建结果
            result = {
                "status": "success",
                "project_id": project_id,
                "project_path": str(project_path),
                "total_files": len(source_files),
                "total_symbols": len(symbols),
                "metadata": {
                    "analyzers_used": self._get_used_analyzers(),
                    "build_time": time.time() - start_time,
                    "timestamp": time.time(),
                    "cscope_analysis": getattr(self, '_cscope_analysis_result', {})
                },
                "call_graph": call_graph,
                "graph_data": graph_data
            }
            
            # 保存索引元数据
            self.index_manager.save_index_metadata(project_id, result)
            
            logger.info(f"索引构建完成，耗时 {time.time() - start_time:.2f} 秒")
            return result
            
        except Exception as e:
            logger.error(f"构建索引失败: {e}")
            return {
                "status": "error",
                "message": str(e),
                "project_path": str(project_path),
                "total_files": 0,
                "total_symbols": 0,
                "metadata": {
                    "analyzers_used": [],
                    "error": True
                }
            }

    def _get_used_analyzers(self) -> List[str]:
        """获取已使用的分析器列表"""
        analyzers = []
        
        # Tree-sitter always used
        analyzers.append("tree-sitter")
        
        # CTags
        try:
            from .ctags_extractor import CTagsExtractor
            analyzers.append("ctags")
        except:
            pass
        
        # Cscope
        if hasattr(self, '_cscope_analysis_result') and self._cscope_analysis_result:
            if self._cscope_analysis_result.get('status') == 'success':
                analyzers.append("cscope")
        
        # Clangd LSP (if available)
        try:
            from .clangd_lsp_client import ClangdLSPClient
            analyzers.append("clangd")
        except:
            pass
            
        return analyzers

    def _extract_symbols(self, project_path: Path) -> List[Dict[str, Any]]:
        """从项目中提取符号（多种方法）"""
        all_symbols = []
        symbol_names_seen = set()
        
        # 1. Tree-sitter高级查询（优先）
        try:
            if self.ts_query_extractor:
                ts_query_symbols = self.ts_query_extractor.extract_project(project_path)
                all_symbols.extend(ts_query_symbols)
                for sym in ts_query_symbols:
                    symbol_names_seen.add(f"{sym.get('name', '')}:{sym.get('file_path', '')}")
                logger.info(f"Tree-sitter Queries 提取了 {len(ts_query_symbols)} 个符号")
            else:
                logger.info("Tree-sitter Query 不可用，跳过高级查询")
        except Exception as e:
            logger.warning(f"Tree-sitter查询失败: {e}")
        
        # 2. Tree-sitter + Lizard 基础解析（回退）
        try:
            ts_symbols = self.ts_symbol_extractor.extract_project(project_path)
            # 去重合并
            before_count = len(all_symbols)
            for sym in ts_symbols:
                sym_key = f"{sym.get('name', '')}:{sym.get('file_path', '')}"
                if sym_key not in symbol_names_seen:
                    all_symbols.append(sym)
                    symbol_names_seen.add(sym_key)
            logger.info(f"Tree-sitter + Lizard 额外提取了 {len(all_symbols) - before_count} 个符号")
        except Exception as e:
            logger.warning(f"Tree-sitter + Lizard 符号提取失败: {e}")
        
        # 3. CTags（精确补充）
        try:
            ctags_symbols = self.ctags_extractor.extract_project(project_path)
            # 去重合并
            before_count = len(all_symbols)
            for sym in ctags_symbols:
                sym_key = f"{sym.get('name', '')}:{sym.get('file_path', '')}"
                if sym_key not in symbol_names_seen:
                    all_symbols.append(sym)
                    symbol_names_seen.add(sym_key)
            logger.info(f"CTags 额外提取了 {len(all_symbols) - before_count} 个符号")
        except Exception as e:
            logger.warning(f"CTags 符号提取失败: {e}")
        
        # 4. Cscope（调用关系和引用分析）
        try:
            from .cscope_analyzer import CscopeAnalyzer
            cscope_analyzer = CscopeAnalyzer()
            if cscope_analyzer.cscope_available:
                cscope_result = cscope_analyzer.analyze_project(project_path)
                if cscope_result.get('status') == 'success':
                    cscope_symbols = cscope_result.get('symbols', [])
                    # 去重合并
                    before_count = len(all_symbols)
                    for sym in cscope_symbols:
                        sym_key = f"{sym.get('function_name', '')}:{sym.get('file_path', '')}"
                        if sym_key not in symbol_names_seen:
                            # 标准化cscope符号格式
                            standardized_sym = {
                                'name': sym.get('function_name', ''),
                                'type': sym.get('type', 'function'),
                                'file_path': sym.get('file_path', ''),
                                'line_number': sym.get('line_number', 0),
                                'source': 'cscope'
                            }
                            all_symbols.append(standardized_sym)
                            symbol_names_seen.add(sym_key)
                    logger.info(f"Cscope 额外提取了 {len(all_symbols) - before_count} 个符号")
                    
                    # 保存cscope分析结果到元数据
                    self._cscope_analysis_result = cscope_result
                else:
                    logger.warning(f"Cscope分析失败: {cscope_result.get('message', 'unknown')}")
            else:
                logger.info("Cscope不可用，跳过Cscope分析")
        except Exception as e:
            logger.warning(f"Cscope 符号提取失败: {e}")

        # 5. 可选：Clangd LSP（如果可用）
        try:
            from .clangd_lsp_client import ClangdLSPClient
            lsp_client = ClangdLSPClient()
            lsp_symbols = lsp_client.extract_symbols(project_path)
            # 去重合并
            before_count = len(all_symbols)
            for sym in lsp_symbols:
                sym_key = f"{sym.get('name', '')}:{sym.get('file_path', '')}"
                if sym_key not in symbol_names_seen:
                    all_symbols.append(sym)
                    symbol_names_seen.add(sym_key)
            logger.info(f"Clangd LSP 额外提取了 {len(all_symbols) - before_count} 个符号")
        except Exception as e:
            logger.debug(f"Clangd LSP 不可用: {e}")
        
        if not all_symbols:
            raise RuntimeError("所有符号提取方法都失败了，无法构建索引")
        
        logger.info(f"总共提取了 {len(all_symbols)} 个符号")
        return all_symbols

    def _extract_call_graph(self, project_path: Path, symbols: List[Dict[str, Any]]) -> Dict[str, Any]:
        """提取调用图"""
        try:
            call_graph = self.call_graph_extractor.extract_call_graph(project_path, symbols)
            logger.info(f"提取了 {len(call_graph.get('edges', []))} 条调用关系")
            return call_graph
        except Exception as e:
            logger.warning(f"调用图提取失败: {e}")
            return {"nodes": [], "edges": []}

    def _build_vector_index(self, symbols: List[Dict[str, Any]]) -> None:
        """构建向量索引"""
        try:
            # 准备文档
            documents = []
            metadatas = []
            ids = []
            
            for symbol in symbols:
                # 创建文档内容
                doc_content = self._create_document_content(symbol)
                documents.append(doc_content)
                
                # 创建元数据
                metadata = {
                    "id": symbol.get("id", ""),
                    "name": symbol.get("name", ""),
                    "type": symbol.get("type", ""),
                    "file_path": symbol.get("file_path", ""),
                    "line_number": symbol.get("line_number", 0)
                }
                metadatas.append(metadata)
                ids.append(symbol.get("id", f"sym_{len(ids)}"))
            
            # 添加到向量存储
            self.vector_store.add_documents(documents, metadatas, ids)
            logger.info(f"构建向量索引完成，共 {len(documents)} 个文档")
            
        except Exception as e:
            logger.error(f"向量索引构建失败: {e}")
            raise

    def _build_graph_index(self, symbols: List[Dict[str, Any]], call_graph: Dict[str, Any]) -> None:
        """构建图索引"""
        try:
            # 添加符号节点
            for symbol in symbols:
                symbol_id = symbol.get('id', f"{symbol.get('name', 'unknown')}_{symbol.get('file_path', '')}")
                self.graph_store.add_symbol(symbol_id, symbol)
            
            # 添加调用关系边
            for edge in call_graph.get("edges", []):
                self.graph_store.add_call_relation(
                    edge.get("caller", ""),
                    edge.get("callee", ""),
                    edge.get("metadata", {})
                )
            
            logger.info("图索引构建完成")
            
        except Exception as e:
            logger.error(f"图索引构建失败: {e}")
            raise

    def _create_document_content(self, symbol: Dict[str, Any]) -> str:
        """为符号创建文档内容"""
        parts = [
            f"符号名称: {symbol.get('name', '')}",
            f"类型: {symbol.get('type', '')}",
            f"文件: {symbol.get('file_path', '')}",
            f"描述: {symbol.get('description', '')}",
        ]
        
        # 添加额外信息
        if symbol.get('declaration'):
            parts.append(f"声明: {symbol['declaration']}")
        
        if symbol.get('parameters'):
            parts.append(f"参数: {symbol['parameters']}")
            
        if symbol.get('return_type'):
            parts.append(f"返回类型: {symbol['return_type']}")
        
        return " | ".join(filter(None, parts))

    def _create_index_metadata(self, project_path: Path, symbols: List[Dict[str, Any]], call_graph: Dict[str, Any]) -> Dict[str, Any]:
        """创建索引元数据"""
        return {
            "project_path": str(project_path),
            "symbols_count": len(symbols),
            "call_edges_count": len(call_graph.get("edges", [])),
            "index_version": "1.0",
            "build_timestamp": time.time(),
            "extraction_methods": ["tree-sitter", "lizard", "ctags"],
            "symbol_types": list(set(s.get("type", "") for s in symbols)),
            "file_count": len(set(s.get("file_path", "") for s in symbols))
        }

    def _load_existing_index(self, project_path: Path) -> Dict[str, Any]:
        """加载现有索引"""
        try:
            metadata = self.index_manager.load_index_metadata(project_path)
            
            return {
                "status": "loaded",
                "project_path": str(project_path),
                "symbols_count": metadata.get("symbols_count", 0),
                "call_edges_count": metadata.get("call_edges_count", 0),
                "build_time": 0,
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"加载现有索引失败: {e}")
            raise

    def search_symbols(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索符号"""
        try:
            return self.vector_store.search(query, limit)
        except Exception as e:
            logger.error(f"符号搜索失败: {e}")
            return []

    def get_call_relations(self, symbol_id: str) -> Dict[str, Any]:
        """获取调用关系"""
        try:
            return self.graph_store.get_call_relations(symbol_id)
        except Exception as e:
            logger.error(f"获取调用关系失败: {e}")
            return {"callers": [], "callees": []}

    def get_project_stats(self, project_path: str) -> Dict[str, Any]:
        """获取项目统计信息"""
        try:
            project_path = Path(project_path)
            metadata = self.index_manager.load_index_metadata(project_path)
            
            return {
                "project_path": str(project_path),
                "symbols_count": metadata.get("symbols_count", 0),
                "call_edges_count": metadata.get("call_edges_count", 0),
                "symbol_types": metadata.get("symbol_types", []),
                "file_count": metadata.get("file_count", 0),
                "last_build": metadata.get("build_timestamp", 0)
            }
            
        except Exception as e:
            logger.error(f"获取项目统计失败: {e}")
            return {} 