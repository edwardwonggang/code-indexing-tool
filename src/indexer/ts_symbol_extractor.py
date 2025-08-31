"""
基于 Tree-sitter 与 Lizard 的无编译 C 代码符号提取器

- Tree-sitter: 解析语法结构（函数、结构体、变量、typedef、宏、枚举）
- Lizard: 计算函数圈复杂度（CCN）

输出结构尽量与原 clang 提取器保持一致，以兼容后续索引流程。
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import hashlib

from loguru import logger
from tree_sitter import Parser
from tree_sitter_languages import get_language
import lizard


class TSSymbolExtractor:
    """基于 Tree-sitter 的 C 语言符号提取器（无编译依赖）"""

    def __init__(self) -> None:
        """初始化Tree-sitter符号提取器（基于官方最佳实践）"""
        try:
            # 优先使用预编译的 parser 提供器，避免语言ABI不匹配
            from tree_sitter_languages import get_parser
            self.parser = get_parser("c")
            self.language = None
            logger.info("Tree-sitter C 解析器初始化完成（get_parser）")
        except Exception:
            # 回退：直接使用底层API（可能与已安装的二进制不兼容）
            self.language = get_language("c")
            self.parser = Parser()
            self.parser.set_language(self.language)
            logger.info("Tree-sitter C 解析器初始化完成（set_language）")
        
        # 解析状态管理
        self._name_to_ids: Dict[str, List[str]] = {}  # 符号名到ID映射
        self._call_edges_name: List[Tuple[str, str]] = []  # 调用关系（名称）
        self._include_edges: List[Tuple[str, str]] = []   # 包含关系
        
        # 官方推荐的查询优化配置
        self.query_options = {
            "max_start_depth": 1000,    # 最大起始深度
            "timeout_micros": 1000000,  # 查询超时（微秒）
        }
        
        # Tree-sitter节点类型优先级（基于官方文档）
        self.node_type_priority = {
            "function_definition": 1,    # 函数定义（最高优先级）
            "function_declarator": 2,    # 函数声明器
            "struct_specifier": 3,       # 结构体定义
            "enum_specifier": 4,         # 枚举定义
            "type_definition": 5,        # typedef定义
            "declaration": 6,            # 一般声明
            "preproc_def": 7,           # 宏定义
            "preproc_include": 8,       # 包含指令
        }
        
        # 支持的文件扩展名（官方C语言语法支持）
        self.supported_extensions = {".c", ".h", ".cpp", ".cxx", ".cc", ".hpp", ".hxx"}

    def extract_from_analysis(self, _analysis, project_path: Path) -> List[Dict[str, Any]]:
        """与旧接口保持兼容：忽略 analysis，直接从源码提取。"""
        return self.extract_project(project_path)

    def extract_project(self, project_path: Path) -> List[Dict[str, Any]]:
        """提取项目符号（基于官方推荐的文件过滤和处理流程）"""
        # 重置状态
        self._name_to_ids.clear()
        self._call_edges_name.clear()
        self._include_edges.clear()

        symbols: List[Dict[str, Any]] = []
        
        # 智能文件发现（基于Tree-sitter官方支持的扩展名）
        c_files = []
        for ext in self.supported_extensions:
            c_files.extend(project_path.rglob(f"*{ext}"))
        
        # 文件过滤（排除不需要的文件，基于最佳实践）
        excluded_patterns = {
            "build", "debug", "release", ".git", ".svn", 
            "node_modules", "vendor", "third_party", "external",
            "__pycache__", ".pytest_cache", "cmake_install",
            "*.min.c", "*.generated.c"  # 排除生成文件
        }
        
        filtered_files = []
        for file_path in c_files:
            # 检查是否包含排除的路径组件
            if not any(excluded in str(file_path).lower() for excluded in excluded_patterns):
                # 检查文件大小（避免处理过大的文件）
                try:
                    if file_path.stat().st_size < 10 * 1024 * 1024:  # 10MB限制
                        filtered_files.append(file_path)
                except OSError:
                    continue  # 跳过无法访问的文件
        
        logger.info(f"Tree-sitter 开始解析 {len(filtered_files)} 个文件（从 {len(c_files)} 个文件中过滤）")

        # 预先用 lizard 计算每个文件的函数复杂度（并行优化）
        file_to_ccn: Dict[Path, Dict[str, int]] = {}
        
        def analyze_complexity(file_path: Path) -> Tuple[Path, Dict[str, int]]:
            """分析单个文件的复杂度（支持错误处理和超时）"""
            try:
                analysis = lizard.analyze_file(str(file_path))
                ccn_map = {
                    func.name: func.cognitive_complexity or func.cyclomatic_complexity 
                    for func in analysis.function_list
                }
                return file_path, ccn_map
            except Exception as e:
                logger.debug(f"Lizard分析失败 {file_path}: {e}")
                return file_path, {}
        
        # 并行计算复杂度（使用过滤后的文件列表）
        from ..utils.performance_optimizer import parallel_map
        complexity_results = parallel_map(analyze_complexity, filtered_files)
        for file_path, ccn_map in complexity_results:
            file_to_ccn[file_path] = ccn_map

        # 优化的并行解析函数
        def parse_single_file(file_path: Path) -> List[Dict[str, Any]]:
            """解析单个文件（包含错误处理和性能优化）"""
            try:
                # 使用 Windows 兼容的文件读取
                from ..utils.windows_compat import WindowsCompatibility
                source_bytes = WindowsCompatibility.safe_read_bytes(file_path)
                if not source_bytes:
                    return []
                
                # Tree-sitter解析（使用官方推荐的错误处理）
                try:
                    tree = self.parser.parse(source_bytes)
                    if tree.root_node.has_error:
                        logger.debug(f"Tree-sitter解析包含错误 {file_path}")
                        # 即使有错误也继续解析，Tree-sitter可以处理部分错误
                    
                    return self._extract_from_tree(
                        project_path, file_path, source_bytes, tree, 
                        file_to_ccn.get(file_path, {})
                    )
                except Exception as parse_error:
                    logger.warning(f"Tree-sitter解析失败 {file_path}: {parse_error}")
                    return []
                    
            except Exception as e:
                logger.warning(f"解析文件 {file_path} 失败: {e}")
                return []
        
        # 并行解析所有过滤后的文件
        file_results = parallel_map(parse_single_file, filtered_files)
        for file_symbols in file_results:
            symbols.extend(file_symbols)

        # 解析完成后，将 (caller_id, callee_name) 解析为 (caller_id, callee_id)
        resolved_edges: List[Tuple[str, str]] = []
        for caller_id, callee_name in self._call_edges_name:
            target_ids = self._name_to_ids.get(callee_name, [])
            for tid in target_ids:
                resolved_edges.append((caller_id, tid))
        self._call_edges = resolved_edges

        logger.info(f"Tree-sitter 符号提取完成，共 {len(symbols)} 个，调用边 {len(self._call_edges)} 条，include {len(self._include_edges)} 条")
        return symbols

    def _extract_from_tree(
        self,
        project_path: Path,
        file_path: Path,
        source: bytes,
        tree,
        ccn_map: Dict[str, int],
    ) -> List[Dict[str, Any]]:
        symbols: List[Dict[str, Any]] = []
        # 使用 Windows 兼容的路径处理
        from ..utils.windows_compat import normalize_path
        rel_path = normalize_path(file_path.relative_to(project_path))

        def node_text(node) -> str:
            return source[node.start_byte: node.end_byte].decode(errors="ignore")

        # 先处理include
        self._extract_includes(tree.root_node, rel_path, node_text)

        # DFS 遍历
        to_visit = [tree.root_node]
        visited = set()
        while to_visit:
            node = to_visit.pop()
            if node.id in visited:
                continue
            visited.add(node.id)

            kind = node.type
            try:
                if kind == "function_definition":
                    symbol = self._extract_function(node, rel_path, node_text, ccn_map)
                    if symbol:
                        symbols.append(symbol)
                        # 建立名称映射
                        self._name_to_ids.setdefault(symbol['name'], []).append(symbol['id'])
                        # 扫描函数体中的调用
                        self._scan_function_calls(node, symbol['id'], node_text)
                elif kind == "struct_specifier":
                    symbol = self._extract_struct(node, rel_path, node_text)
                    if symbol:
                        symbols.append(symbol)
                elif kind == "enum_specifier":
                    symbol = self._extract_enum(node, rel_path, node_text)
                    if symbol:
                        symbols.append(symbol)
                elif kind == "type_definition":
                    symbol = self._extract_typedef(node, rel_path, node_text)
                    if symbol:
                        symbols.append(symbol)
                elif kind == "preproc_def":
                    symbol = self._extract_macro(node, rel_path, node_text)
                    if symbol:
                        symbols.append(symbol)
                elif kind == "declaration":
                    if self._is_file_scope_declaration(node):
                        symbol = self._extract_variable(node, rel_path, node_text)
                        if symbol:
                            symbols.append(symbol)
            except Exception as e:
                logger.debug(f"节点处理失败({kind}): {e}")

            for i in range(node.named_child_count):
                to_visit.append(node.named_child(i))

        return symbols

    def _extract_includes(self, root, file_path: str, node_text) -> None:
        to_visit = [root]
        visited = set()
        while to_visit:
            n = to_visit.pop()
            if n.id in visited:
                continue
            visited.add(n.id)
            if n.type == 'preproc_include':
                text = node_text(n)
                # 解析 #include <...> 或 "..."
                inc = None
                if '"' in text:
                    try:
                        inc = text.split('"')[1]
                    except Exception:
                        inc = None
                elif '<' in text and '>' in text:
                    try:
                        inc = text.split('<')[1].split('>')[0]
                    except Exception:
                        inc = None
                if inc:
                    self._include_edges.append((file_path, inc))
            for i in range(n.named_child_count):
                to_visit.append(n.named_child(i))

    def _scan_function_calls(self, func_node, caller_id: str, node_text) -> None:
        # 在函数体内查找 call_expression
        to_visit = []
        # 函数体通常是最后一个命名子节点 compound_statement
        for i in range(func_node.named_child_count):
            ch = func_node.named_child(i)
            if ch.type == 'compound_statement':
                to_visit.append(ch)
        visited = set()
        while to_visit:
            n = to_visit.pop()
            if n.id in visited:
                continue
            visited.add(n.id)
            if n.type == 'call_expression':
                # call_expression 的第一个命名子结点通常是函数标识符或后缀表达式
                callee_name = self._extract_callee_name(n, node_text)
                if callee_name:
                    self._call_edges_name.append((caller_id, callee_name))
            for i in range(n.named_child_count):
                to_visit.append(n.named_child(i))

    def _extract_callee_name(self, call_node, node_text) -> Optional[str]:
        # 形如: identifier(args) | field_expression(args) | pointer_expression(args)
        # 仅提取简单的 identifier 名称，复杂场景可扩展
        for i in range(call_node.named_child_count):
            ch = call_node.named_child(i)
            if ch.type in ('identifier',):
                return self._clean_ws(node_text(ch))
            if ch.type in ('field_expression', 'pointer_expression', 'parenthesized_expression'):
                # 深入找最里层的 identifier
                name = self._find_identifier(ch, node_text)
                if name:
                    return name
        return None

    # --------------------------
    # 各类符号提取
    # --------------------------

    def _extract_function(self, node, file_path: str, node_text, ccn_map: Dict[str, int]) -> Optional[Dict[str, Any]]:
        # 结构: function_definition(declaration_specifiers?, declarator, compound_statement)
        decl_spec = None
        declarator = None
        for i in range(node.named_child_count):
            ch = node.named_child(i)
            if ch.type in ("declaration_specifiers", "storage_class_specifier", "type_qualifier", "type_specifier"):
                decl_spec = ch
            if ch.type == "declarator":
                declarator = ch
        if declarator is None:
            return None

        func_name = self._find_identifier(declarator, node_text)
        if not func_name:
            return None

        return_type = self._guess_return_type_text(decl_spec, node_text)
        param_text, params = self._extract_params(declarator, node_text)
        signature = f"{return_type} {func_name}({param_text})".strip()

        line_number = node.start_point[0] + 1
        complexity = self._complexity_from_lizard(func_name, ccn_map)

        return {
            'id': self._generate_id('function', func_name, file_path, line_number),
            'name': func_name,
            'type': 'function',
            'file_path': file_path,
            'line_number': line_number,
            'declaration': signature,
            'return_type': return_type,
            'parameters': param_text,
            'parameter_list': params,
            'is_static': self._has_storage_class(decl_spec, node_text, 'static'),
            'is_inline': self._has_storage_class(decl_spec, node_text, 'inline'),
            'complexity': self._complexity_bucket(complexity),
            'description': f"函数 {func_name} 返回 {return_type}"
        }

    def _extract_struct(self, node, file_path: str, node_text) -> Optional[Dict[str, Any]]:
        # struct_specifier: 'struct' identifier? field_declaration_list?
        name = self._find_identifier(node, node_text) or ""
        if not name:
            # 匿名结构体不收录为独立符号
            return None
        line_number = node.start_point[0] + 1

        members: List[Dict[str, str]] = []
        field_list = self._find_child_by_type(node, "field_declaration_list")
        if field_list is not None:
            for i in range(field_list.named_child_count):
                field = field_list.named_child(i)
                if field.type == "field_declaration":
                    t = self._find_child_by_types(field, ["type_specifier", "type_qualifier", "sized_type_specifier"]) or field
                    decl = self._find_child_by_type(field, "field_declarator") or field
                    t_text = self._clean_ws(node_text(t))
                    n_text = self._find_identifier_text(decl, node_text) or ""
                    if n_text:
                        members.append({"name": n_text, "type": t_text})

        declaration = f"struct {name}"
        if members:
            member_decls = [f"  {m['type']} {m['name']};" for m in members]
            declaration += " {\n" + "\n".join(member_decls) + "\n}"

        return {
            'id': self._generate_id('structure', name, file_path, line_number),
            'name': name,
            'type': 'structure',
            'file_path': file_path,
            'line_number': line_number,
            'declaration': declaration,
            'members': members,
            'member_count': len(members),
            'description': f"结构体 {name} 包含 {len(members)} 个成员"
        }

    def _extract_enum(self, node, file_path: str, node_text) -> Optional[Dict[str, Any]]:
        name = self._find_identifier(node, node_text) or ""
        if not name:
            return None
        line_number = node.start_point[0] + 1

        values: List[Dict[str, Any]] = []
        enum_list = self._find_child_by_type(node, "enumerator_list")
        if enum_list is not None:
            for i in range(enum_list.named_child_count):
                en = enum_list.named_child(i)
                if en.type == "enumerator":
                    en_name = self._find_identifier(en, node_text) or ""
                    values.append({"name": en_name, "value": None})

        return {
            'id': self._generate_id('enum', name, file_path, line_number),
            'name': name,
            'type': 'enum',
            'file_path': file_path,
            'line_number': line_number,
            'declaration': f"enum {name}",
            'values': values,
            'description': f"枚举 {name} 包含 {len(values)} 个值"
        }

    def _extract_typedef(self, node, file_path: str, node_text) -> Optional[Dict[str, Any]]:
        # type_definition: 'typedef' type declarator ';'
        name = self._find_identifier(node, node_text) or ""
        if not name:
            return None
        line_number = node.start_point[0] + 1
        underlying = self._guess_typedef_underlying(node, node_text)
        return {
            'id': self._generate_id('typedef', name, file_path, line_number),
            'name': name,
            'type': 'typedef',
            'file_path': file_path,
            'line_number': line_number,
            'declaration': f"typedef {underlying} {name}",
            'underlying_type': underlying,
            'description': f"类型定义 {name} -> {underlying}"
        }

    def _extract_macro(self, node, file_path: str, node_text) -> Optional[Dict[str, Any]]:
        # preproc_def: '#define' identifier ...
        text = self._clean_ws(node_text(node))
        parts = text.split()
        if len(parts) >= 2:
            name = parts[1]
        else:
            return None
        line_number = node.start_point[0] + 1
        return {
            'id': self._generate_id('macro', name, file_path, line_number),
            'name': name,
            'type': 'macro',
            'file_path': file_path,
            'line_number': line_number,
            'declaration': text,
            'description': f"宏定义 {name}"
        }

    def _extract_variable(self, node, file_path: str, node_text) -> Optional[Dict[str, Any]]:
        # declaration: declaration_specifiers init_declarator_list ';'
        t = self._find_child_by_types(node, ["type_specifier", "type_qualifier", "sized_type_specifier"]) or node
        decl_list = self._find_child_by_type(node, "init_declarator_list") or node
        var_type = self._clean_ws(node_text(t))
        name = self._find_identifier_text(decl_list, node_text) or ""
        if not name:
            return None
        line_number = node.start_point[0] + 1
        return {
            'id': self._generate_id('variable', name, file_path, line_number),
            'name': name,
            'type': 'variable',
            'file_path': file_path,
            'line_number': line_number,
            'declaration': f"{var_type} {name}",
            'data_type': var_type,
            'is_static': False,
            'is_const': ('const' in var_type),
            'description': f"变量 {name} 类型为 {var_type}"
        }

    # --------------------------
    # 工具方法
    # --------------------------

    def _find_child_by_type(self, node, type_name: str):
        for i in range(node.named_child_count):
            ch = node.named_child(i)
            if ch.type == type_name:
                return ch
        return None

    def _find_child_by_types(self, node, types: List[str]):
        for i in range(node.named_child_count):
            ch = node.named_child(i)
            if ch.type in types:
                return ch
        return None

    def _find_identifier(self, node, node_text) -> Optional[str]:
        # 深度优先查找第一个 identifier
        stack = [node]
        visited = set()
        while stack:
            n = stack.pop()
            if n.id in visited:
                continue
            visited.add(n.id)
            if n.type == 'identifier':
                return self._clean_ws(node_text(n))
            for i in range(n.named_child_count):
                stack.append(n.named_child(i))
        return None

    def _find_identifier_text(self, node, node_text) -> Optional[str]:
        return self._find_identifier(node, node_text)

    def _guess_return_type_text(self, decl_spec, node_text) -> str:
        if decl_spec is None:
            return "void"
        text = self._clean_ws(node_text(decl_spec))
        # 去掉存储类说明符等
        tokens = [t for t in text.split() if t not in ("static", "inline", "extern", "register", "auto")]
        return " ".join(tokens) if tokens else "void"

    def _extract_params(self, declarator, node_text) -> Tuple[str, List[Dict[str, str]]]:
        # declarator 内部包含 parameter_list
        param_list = self._find_child_by_type(declarator, "parameter_list")
        if param_list is None:
            return "", []
        params: List[Dict[str, str]] = []
        parts: List[str] = []
        for i in range(param_list.named_child_count):
            p = param_list.named_child(i)
            if p.type == "parameter_declaration":
                p_type_node = self._find_child_by_types(p, ["type_specifier", "type_qualifier", "sized_type_specifier"]) or p
                p_name = self._find_identifier(p, node_text) or ""
                p_type = self._clean_ws(node_text(p_type_node))
                parts.append((p_type + (" " + p_name if p_name else "")).strip())
                params.append({"name": p_name or f"param{len(params)}", "type": p_type})
        return ", ".join(parts), params

    def _has_storage_class(self, decl_spec, node_text, keyword: str) -> bool:
        if decl_spec is None:
            return False
        text = node_text(decl_spec)
        return keyword in text

    def _complexity_from_lizard(self, func_name: str, ccn_map: Dict[str, int]) -> int:
        return int(ccn_map.get(func_name, 0) or 0)

    def _complexity_bucket(self, ccn: int) -> str:
        if ccn <= 5:
            return "low"
        if ccn <= 10:
            return "medium"
        return "high"

    # 新增: 根据 typedef 语法节点猜测底层类型
    def _guess_typedef_underlying(self, node, node_text) -> str:
        """简单地根据文本猜测 typedef 的底层类型。

        处理常见场景：
        1. typedef struct {...} Foo;
        2. typedef unsigned long size_t;
        3. typedef int INT, *PINT; （仅返回第一个声明部分）
        """
        text = self._clean_ws(node_text(node))
        # 去掉前缀 typedef 与尾部分号
        if text.startswith("typedef"):
            text = text[len("typedef"):].strip()
        if text.endswith(";"):
            text = text[:-1].strip()
        # 仅取第一个逗号前内容
        text = text.split(",")[0].strip()
        # 通常最后一个 token 是别名，移除它得到底层类型
        tokens = text.split()
        if len(tokens) >= 2:
            underlying = " ".join(tokens[:-1])
        else:
            underlying = text
        return underlying

    @staticmethod
    def _clean_ws(s: str) -> str:
        return " ".join(s.replace("\n", " ").replace("\t", " ").split())

    def _is_file_scope_declaration(self, node) -> bool:
        # 粗略判断：父节点是 translation_unit
        return node.parent is not None and node.parent.type == 'translation_unit'

    def _generate_id(self, symbol_type: str, name: str, file_path: str, line_number: int = 0) -> str:
        import uuid
        unique_suffix = str(uuid.uuid4())[:8]
        content = f"{symbol_type}:{name}:{file_path}:{line_number}:{unique_suffix}"
        return hashlib.md5(content.encode()).hexdigest()[:16] 

    # 对外关系访问
    def get_call_relations(self) -> List[Tuple[str, str]]:
        """返回 (caller_id, callee_id) 列表。需先调用 extract_project。"""
        return getattr(self, '_call_edges', [])

    def get_include_relations(self) -> List[Tuple[str, str]]:
        """返回 (file_path, included_path) 列表。需先调用 extract_project。"""
        return list(self._include_edges) 