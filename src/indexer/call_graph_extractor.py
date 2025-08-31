"""
调用图构建器

封装自 Tree-sitter 提取函数调用关系与 include 关系，供索引器使用。
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Dict
from loguru import logger

class CallGraphExtractor:
    def extract_call_graph(self, project_path: Path, symbols: List = None) -> Dict[str, List]:
        """提取调用图和包含关系"""
        calls, includes = self.build(project_path)
        return {
            "nodes": symbols or [],
            "edges": [{"caller": caller, "callee": callee, "type": "call"} for caller, callee in calls],
            "includes": [{"from": from_file, "to": to_file, "type": "include"} for from_file, to_file in includes]
        }
    
    def build(self, project_path: Path) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        try:
            from .ts_symbol_extractor import TSSymbolExtractor
            ext = TSSymbolExtractor()
            ext.extract_project(project_path)
            calls = ext.get_call_relations()
            includes = ext.get_include_relations()
            return calls, includes
        except Exception as e:
            logger.warning(f"CallGraph 提取失败: {e}")
            return [], [] 