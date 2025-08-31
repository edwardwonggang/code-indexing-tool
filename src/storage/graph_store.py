"""
调用图/关系图存储

- 保存函数调用关系（call -> callee）
- 保存文件包含关系（include -> included）
- 提供 callers/callees 查询与图导出
"""
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path
import json

class GraphStore:
    def __init__(self, persist_path: Optional[Path] = None) -> None:
        self.call_edges: Dict[str, Set[str]] = {}
        self.reverse_call_edges: Dict[str, Set[str]] = {}
        self.includes: Dict[str, Set[str]] = {}
        self.persist_path = persist_path

    def add_call(self, caller_symbol_id: str, callee_symbol_id: str) -> None:
        self.call_edges.setdefault(caller_symbol_id, set()).add(callee_symbol_id)
        self.reverse_call_edges.setdefault(callee_symbol_id, set()).add(caller_symbol_id)

    def add_include(self, file_path: str, included_path: str) -> None:
        self.includes.setdefault(file_path, set()).add(included_path)

    def add_symbol(self, symbol_id: str, symbol_data: dict) -> None:
        """添加符号到图存储（兼容性方法）"""
        # 这个方法主要用于兼容性，实际的符号数据存储在vector_store中
        # 这里可以存储符号的元数据或者建立符号ID的映射关系
        pass
    
    def add_call_relation(self, caller: str, callee: str, metadata: dict = None) -> None:
        """添加调用关系"""
        self.add_call(caller, callee)

    def get_callees(self, symbol_id: str, depth: int = 1) -> List[str]:
        result: Set[str] = set()
        frontier: Set[str] = {symbol_id}
        for _ in range(max(0, depth)):
            next_frontier: Set[str] = set()
            for s in frontier:
                for callee in self.call_edges.get(s, set()):
                    if callee not in result:
                        result.add(callee)
                        next_frontier.add(callee)
            frontier = next_frontier
        return list(result)

    def get_callers(self, symbol_id: str, depth: int = 1) -> List[str]:
        result: Set[str] = set()
        frontier: Set[str] = {symbol_id}
        for _ in range(max(0, depth)):
            next_frontier: Set[str] = set()
            for s in frontier:
                for caller in self.reverse_call_edges.get(s, set()):
                    if caller not in result:
                        result.add(caller)
                        next_frontier.add(caller)
            frontier = next_frontier
        return list(result)

    def export(self) -> Dict[str, List[Tuple[str, str]]]:
        return {
            "calls": [(u, v) for u, vs in self.call_edges.items() for v in vs],
            "includes": [(u, v) for u, vs in self.includes.items() for v in vs],
        }

    def save(self) -> None:
        if not self.persist_path:
            return
        data = {
            "call_edges": {k: list(v) for k, v in self.call_edges.items()},
            "reverse_call_edges": {k: list(v) for k, v in self.reverse_call_edges.items()},
            "includes": {k: list(v) for k, v in self.includes.items()},
        }
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self.persist_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> None:
        if not self.persist_path or not self.persist_path.exists():
            return
        data = json.loads(self.persist_path.read_text(encoding="utf-8"))
        self.call_edges = {k: set(v) for k, v in data.get("call_edges", {}).items()}
        self.reverse_call_edges = {k: set(v) for k, v in data.get("reverse_call_edges", {}).items()}
        self.includes = {k: set(v) for k, v in data.get("includes", {}).items()} 