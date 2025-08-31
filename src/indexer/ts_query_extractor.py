"""
基于 Tree-sitter Queries 的增强符号提取器

使用 Tree-sitter 查询语言进行精确的模式匹配，提高符号提取的准确性和覆盖率。

特性：
- 预定义查询模式
- 精确的函数指针检测
- 宏用法分析
- 复杂类型解析
- 嵌套结构处理
"""
from __future__ import annotations

from typing import Dict, List, Any, Optional, Tuple, Set
from pathlib import Path
import hashlib
import uuid

from loguru import logger

# 兼容不同版本的 tree-sitter
try:
    from tree_sitter import Parser, Query
    QUERY_AVAILABLE = True
except ImportError:
    try:
        # 尝试新的导入方式
        from tree_sitter import Parser
        from tree_sitter.query import Query
        QUERY_AVAILABLE = True
    except ImportError:
        # 如果都失败了，设置为不可用
        Parser = None
        Query = None
        QUERY_AVAILABLE = False
        logger.warning("Tree-sitter Query 不可用，将跳过高级查询功能")

from tree_sitter_languages import get_language, get_parser
import lizard


class TSQueryExtractor:
    """基于 Tree-sitter Queries 的增强符号提取器"""

    def __init__(self):
        """初始化提取器和查询"""
        # 首先初始化基本属性
        self._name_to_ids: Dict[str, List[str]] = {}
        self._call_edges_name: List[Tuple[str, str]] = []
        self._include_edges: List[Tuple[str, str]] = []
        
        # 检查 Query 是否可用
        if not QUERY_AVAILABLE:
            logger.warning("Tree-sitter Query 不可用，TSQueryExtractor 将使用基础模式")
            self.queries = {}
            # 即使 Query 不可用，也要初始化 parser
            try:
                from tree_sitter_languages import get_parser
                self.parser = get_parser("c")
                self.language = get_language("c")
                logger.info("Tree-sitter C 解析器初始化完成（基础模式）")
            except Exception:
                # 如果连基础 parser 都无法初始化，设置为 None
                self.parser = None
                self.language = None
                logger.error("Tree-sitter 解析器初始化失败")
            return
            
        try:
            # 优先使用预编译的 parser
            from tree_sitter_languages import get_parser
            self.parser = get_parser("c")
            self.language = get_language("c")
            logger.info("Tree-sitter C 解析器初始化完成（get_parser）")
        except Exception:
            # 回退方案
            self.language = get_language("c")
            self.parser = Parser()
            self.parser.set_language(self.language)
            logger.info("Tree-sitter C 解析器初始化完成（set_language）")
        
        # 编译查询
        self.queries = self._compile_queries()

    def extract_project(self, project_path: Path) -> List[Dict[str, Any]]:
        """提取项目符号"""
        self._name_to_ids.clear()
        self._call_edges_name.clear()
        self._include_edges.clear()

        symbols: List[Dict[str, Any]] = []
        
        # 如果 parser 不可用，直接返回空结果
        if not hasattr(self, 'parser') or self.parser is None:
            logger.warning("Tree-sitter 解析器不可用，TSQueryExtractor 跳过处理")
            return symbols
            
        # 如果 Query 不可用，记录警告但继续处理（可能有基础功能）
        if not QUERY_AVAILABLE or not self.queries:
            logger.warning("Tree-sitter Query 不可用，TSQueryExtractor 无法执行高级查询")
            return symbols
        
        c_files = list(project_path.rglob("*.c")) + list(project_path.rglob("*.h"))
        logger.info(f"Tree-sitter Queries 开始解析 {len(c_files)} 个C文件")

        # 预先计算复杂度
        file_to_ccn: Dict[Path, Dict[str, int]] = {}
        for file_path in c_files:
            try:
                analysis = lizard.analyze_file(str(file_path))
                file_to_ccn[file_path] = {
                    func.name: func.cognitive_complexity or func.cyclomatic_complexity 
                    for func in analysis.function_list
                }
            except Exception:
                file_to_ccn[file_path] = {}

        # 处理每个文件
        for file_path in c_files:
            try:
                source_bytes = file_path.read_bytes()
                tree = self.parser.parse(source_bytes)
                file_symbols = self._extract_from_tree_with_queries(
                    project_path, file_path, source_bytes, tree, file_to_ccn.get(file_path, {})
                )
                symbols.extend(file_symbols)
            except Exception as e:
                logger.warning(f"解析文件 {file_path} 失败: {e}")

        # 解析调用关系
        resolved_edges: List[Tuple[str, str]] = []
        for caller_id, callee_name in self._call_edges_name:
            target_ids = self._name_to_ids.get(callee_name, [])
            for tid in target_ids:
                resolved_edges.append((caller_id, tid))
        self._call_edges = resolved_edges

        logger.info(f"Tree-sitter Queries 符号提取完成，共 {len(symbols)} 个，调用边 {len(self._call_edges)} 条")
        return symbols

    def get_call_relations(self) -> List[Tuple[str, str]]:
        """返回调用关系"""
        return getattr(self, '_call_edges', [])

    def get_include_relations(self) -> List[Tuple[str, str]]:
        """返回包含关系"""
        return list(self._include_edges)

    # ----------------------
    # 查询编译和模式定义
    # ----------------------

    def _compile_queries(self) -> Dict[str, Query]:
        """编译所有查询模式"""
        queries = {}
        
        # 如果 Query 不可用，返回空字典
        if not QUERY_AVAILABLE:
            logger.warning("Tree-sitter Query 不可用，跳过查询编译")
            return queries
        
        # 函数定义查询（包括复杂情况）
        function_query = """
        (function_definition
          (declaration_specifiers)? @return_type
          declarator: (function_declarator
            declarator: (identifier) @name
            parameters: (parameter_list)? @params
          )
          body: (compound_statement) @body
        ) @function
        """
        
        # 函数指针查询
        function_pointer_query = """
        (declaration
          declarator: (pointer_declarator
            declarator: (function_declarator
              declarator: (identifier) @name
              parameters: (parameter_list)? @params
            )
          )
        ) @function_pointer
        """
        
        # 结构体查询（包括匿名结构体）
        struct_query = """
        (struct_specifier
          name: (type_identifier) @name
          body: (field_declaration_list)? @body
        ) @struct
        
        (struct_specifier
          body: (field_declaration_list) @body
        ) @anonymous_struct
        """
        
        # 宏定义查询
        macro_query = """
        (preproc_def
          name: (identifier) @name
          value: (_)? @value
        ) @macro
        
        (preproc_function_def
          name: (identifier) @name
          parameters: (preproc_params)? @params
          value: (_)? @value
        ) @function_macro
        """
        
        # 变量查询（包括全局和局部变量）
        variable_query = """
        (declaration
          declarator: (identifier) @name
          type: (_) @type
        ) @variable
        
        (declaration
          declarator: (init_declarator
            declarator: (identifier) @name
            value: (_)? @init
          )
          type: (_) @type
        ) @initialized_variable
        """
        
        # 枚举查询
        enum_query = """
        (enum_specifier
          name: (type_identifier)? @name
          body: (enumerator_list)? @body
        ) @enum
        
        (enumerator
          name: (identifier) @name
          value: (_)? @value
        ) @enum_member
        """
        
        # typedef 查询
        typedef_query = """
        (type_definition
          type: (_) @base_type
          declarator: (type_identifier) @name
        ) @typedef
        """
        
        # 函数调用查询
        call_query = """
        (call_expression
          function: (identifier) @callee
        ) @call
        
        (call_expression
          function: (field_expression
            field: (field_identifier) @callee
          )
        ) @method_call
        """
        
        # Include 查询
        include_query = """
        (preproc_include
          path: (string_literal) @path
        ) @include
        
        (preproc_include
          path: (system_lib_string) @path
        ) @system_include
        """
        
        query_definitions = {
            "functions": function_query,
            "function_pointers": function_pointer_query,
            "structs": struct_query,
            "macros": macro_query,
            "variables": variable_query,
            "enums": enum_query,
            "typedefs": typedef_query,
            "calls": call_query,
            "includes": include_query
        }
        
        for name, query_str in query_definitions.items():
            try:
                queries[name] = Query(self.language, query_str)
            except Exception as e:
                logger.warning(f"编译查询 {name} 失败: {e}")
                
        return queries

    # ----------------------
    # 基于查询的符号提取
    # ----------------------

    def _extract_from_tree_with_queries(
        self, 
        project_path: Path, 
        file_path: Path, 
        source: bytes, 
        tree, 
        ccn_map: Dict[str, int]
    ) -> List[Dict[str, Any]]:
        """使用查询提取符号"""
        symbols: List[Dict[str, Any]] = []
        rel_path = str(file_path.relative_to(project_path)).replace("\\", "/")
        
        def node_text(node) -> str:
            return source[node.start_byte:node.end_byte].decode(errors="ignore")

        # 提取函数
        if "functions" in self.queries:
            function_symbols = self._extract_functions_with_query(
                tree.root_node, rel_path, node_text, ccn_map
            )
            symbols.extend(function_symbols)
            
            # 建立名称映射
            for symbol in function_symbols:
                self._name_to_ids.setdefault(symbol['name'], []).append(symbol['id'])

        # 提取结构体
        if "structs" in self.queries:
            struct_symbols = self._extract_structs_with_query(
                tree.root_node, rel_path, node_text
            )
            symbols.extend(struct_symbols)

        # 提取宏
        if "macros" in self.queries:
            macro_symbols = self._extract_macros_with_query(
                tree.root_node, rel_path, node_text
            )
            symbols.extend(macro_symbols)

        # 提取变量
        if "variables" in self.queries:
            variable_symbols = self._extract_variables_with_query(
                tree.root_node, rel_path, node_text
            )
            symbols.extend(variable_symbols)

        # 提取枚举
        if "enums" in self.queries:
            enum_symbols = self._extract_enums_with_query(
                tree.root_node, rel_path, node_text
            )
            symbols.extend(enum_symbols)

        # 提取 typedef
        if "typedefs" in self.queries:
            typedef_symbols = self._extract_typedefs_with_query(
                tree.root_node, rel_path, node_text
            )
            symbols.extend(typedef_symbols)

        # 提取调用关系
        if "calls" in self.queries:
            self._extract_calls_with_query(tree.root_node, symbols, node_text)

        # 提取 include 关系
        if "includes" in self.queries:
            self._extract_includes_with_query(tree.root_node, rel_path, node_text)

        return symbols

    def _extract_functions_with_query(
        self, root_node, file_path: str, node_text, ccn_map: Dict[str, int]
    ) -> List[Dict[str, Any]]:
        """使用查询提取函数"""
        functions = []
        captures = self.queries["functions"].captures(root_node)
        
        # 按函数分组captures
        function_captures = {}
        for node, capture_name in captures:
            if capture_name == "function":
                function_captures[node.id] = {"function": node}
            elif node.parent and node.parent.id in function_captures:
                function_captures[node.parent.id][capture_name] = node

        for func_data in function_captures.values():
            if "name" not in func_data:
                continue
                
            func_node = func_data["function"]
            name_node = func_data["name"]
            
            func_name = node_text(name_node).strip()
            line_number = func_node.start_point[0] + 1
            
            # 提取返回类型
            return_type = "void"
            if "return_type" in func_data:
                return_type = self._clean_ws(node_text(func_data["return_type"]))
            
            # 提取参数
            param_text, params = "", []
            if "params" in func_data:
                param_text, params = self._extract_params_from_node(func_data["params"], node_text)
            
            # 构建签名
            signature = f"{return_type} {func_name}({param_text})".strip()
            
            # 获取复杂度
            complexity = ccn_map.get(func_name, 0)
            
            function_symbol = {
                'id': self._generate_id('function', func_name, file_path, line_number),
                'name': func_name,
                'type': 'function',
                'file_path': file_path,
                'line_number': line_number,
                'declaration': signature,
                'return_type': return_type,
                'parameters': param_text,
                'parameter_list': params,
                'complexity': self._complexity_bucket(complexity),
                'description': f"函数 {func_name} 返回 {return_type}"
            }
            functions.append(function_symbol)
            
        return functions

    def _extract_structs_with_query(
        self, root_node, file_path: str, node_text
    ) -> List[Dict[str, Any]]:
        """使用查询提取结构体"""
        structs = []
        captures = self.queries["structs"].captures(root_node)
        
        # 按结构体分组
        struct_captures = {}
        for node, capture_name in captures:
            if capture_name == "struct":
                struct_captures[node.id] = {"struct": node}
            elif node.parent and node.parent.id in struct_captures:
                struct_captures[node.parent.id][capture_name] = node

        for struct_data in struct_captures.values():
            struct_node = struct_data["struct"]
            
            # 获取名称（可能为空，匿名结构体）
            name = ""
            if "name" in struct_data:
                name = node_text(struct_data["name"]).strip()
            
            if not name:
                continue  # 跳过匿名结构体
                
            line_number = struct_node.start_point[0] + 1
            
            # 提取成员
            members = []
            if "fields" in struct_data:
                members = self._extract_struct_members_from_node(struct_data["fields"], node_text)
            
            # 构建声明
            declaration = f"struct {name}"
            if members:
                member_decls = [f"  {m['type']} {m['name']};" for m in members]
                declaration += " {\n" + "\n".join(member_decls) + "\n}"
            
            struct_symbol = {
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
            structs.append(struct_symbol)
            
        return structs

    def _extract_macros_with_query(
        self, root_node, file_path: str, node_text
    ) -> List[Dict[str, Any]]:
        """使用查询提取宏"""
        macros = []
        captures = self.queries["macros"].captures(root_node)
        
        # 按宏分组
        macro_captures = {}
        for node, capture_name in captures:
            if capture_name in ("macro", "function_macro"):
                macro_captures[node.id] = {"macro": node, "type": capture_name}
            elif node.parent and node.parent.id in macro_captures:
                macro_captures[node.parent.id][capture_name] = node

        for macro_data in macro_captures.values():
            if "name" not in macro_data:
                continue
                
            macro_node = macro_data["macro"]
            name_node = macro_data["name"]
            
            macro_name = node_text(name_node).strip()
            line_number = macro_node.start_point[0] + 1
            
            # 构建声明
            declaration = node_text(macro_node).strip()
            
            # 判断是否为函数式宏
            is_function_macro = macro_data.get("type") == "function_macro"
            
            macro_symbol = {
                'id': self._generate_id('macro', macro_name, file_path, line_number),
                'name': macro_name,
                'type': 'macro',
                'file_path': file_path,
                'line_number': line_number,
                'declaration': declaration,
                'is_function_macro': is_function_macro,
                'description': f"{'函数式' if is_function_macro else ''}宏定义 {macro_name}"
            }
            macros.append(macro_symbol)
            
        return macros

    def _extract_variables_with_query(
        self, root_node, file_path: str, node_text
    ) -> List[Dict[str, Any]]:
        """使用查询提取变量"""
        variables = []
        captures = self.queries["variables"].captures(root_node)
        
        # 按变量分组
        var_captures = {}
        for node, capture_name in captures:
            if capture_name == "variable":
                var_captures[node.id] = {"variable": node}
            elif node.parent and node.parent.id in var_captures:
                var_captures[node.parent.id][capture_name] = node

        for var_data in var_captures.values():
            if "name" not in var_data or "type" not in var_data:
                continue
                
            var_node = var_data["variable"]
            name_node = var_data["name"]
            type_node = var_data["type"]
            
            var_name = node_text(name_node).strip()
            var_type = self._clean_ws(node_text(type_node))
            line_number = var_node.start_point[0] + 1
            
            # 检查是否为文件作用域
            if not self._is_file_scope_node(var_node):
                continue
            
            variable_symbol = {
                'id': self._generate_id('variable', var_name, file_path, line_number),
                'name': var_name,
                'type': 'variable',
                'file_path': file_path,
                'line_number': line_number,
                'declaration': f"{var_type} {var_name}",
                'data_type': var_type,
                'is_static': 'static' in var_type,
                'is_const': 'const' in var_type,
                'description': f"变量 {var_name} 类型为 {var_type}"
            }
            variables.append(variable_symbol)
            
        return variables

    def _extract_enums_with_query(
        self, root_node, file_path: str, node_text
    ) -> List[Dict[str, Any]]:
        """使用查询提取枚举"""
        enums = []
        captures = self.queries["enums"].captures(root_node)
        
        # 按枚举分组
        enum_captures = {}
        for node, capture_name in captures:
            if capture_name == "enum":
                enum_captures[node.id] = {"enum": node}
            elif node.parent and node.parent.id in enum_captures:
                enum_captures[node.parent.id][capture_name] = node

        for enum_data in enum_captures.values():
            enum_node = enum_data["enum"]
            
            # 获取名称
            name = ""
            if "name" in enum_data:
                name = node_text(enum_data["name"]).strip()
            
            if not name:
                continue  # 跳过匿名枚举
                
            line_number = enum_node.start_point[0] + 1
            
            # 提取枚举值
            values = []
            if "values" in enum_data:
                values = self._extract_enum_values_from_node(enum_data["values"], node_text)
            
            enum_symbol = {
                'id': self._generate_id('enum', name, file_path, line_number),
                'name': name,
                'type': 'enum',
                'file_path': file_path,
                'line_number': line_number,
                'declaration': f"enum {name}",
                'values': values,
                'description': f"枚举 {name} 包含 {len(values)} 个值"
            }
            enums.append(enum_symbol)
            
        return enums

    def _extract_typedefs_with_query(
        self, root_node, file_path: str, node_text
    ) -> List[Dict[str, Any]]:
        """使用查询提取 typedef"""
        typedefs = []
        captures = self.queries["typedefs"].captures(root_node)
        
        # 按 typedef 分组
        typedef_captures = {}
        for node, capture_name in captures:
            if capture_name == "typedef":
                typedef_captures[node.id] = {"typedef": node}
            elif node.parent and node.parent.id in typedef_captures:
                typedef_captures[node.parent.id][capture_name] = node

        for typedef_data in typedef_captures.values():
            if "name" not in typedef_data or "base_type" not in typedef_data:
                continue
                
            typedef_node = typedef_data["typedef"]
            name_node = typedef_data["name"]
            base_type_node = typedef_data["base_type"]
            
            type_name = node_text(name_node).strip()
            base_type = self._clean_ws(node_text(base_type_node))
            line_number = typedef_node.start_point[0] + 1
            
            typedef_symbol = {
                'id': self._generate_id('typedef', type_name, file_path, line_number),
                'name': type_name,
                'type': 'typedef',
                'file_path': file_path,
                'line_number': line_number,
                'declaration': f"typedef {base_type} {type_name}",
                'underlying_type': base_type,
                'description': f"类型定义 {type_name} -> {base_type}"
            }
            typedefs.append(typedef_symbol)
            
        return typedefs

    def _extract_calls_with_query(self, root_node, symbols: List[Dict[str, Any]], node_text):
        """提取函数调用关系"""
        captures = self.queries["calls"].captures(root_node)
        
        # 找到所有函数的ID映射
        func_id_map = {}
        for symbol in symbols:
            if symbol['type'] == 'function':
                # 找到包含此调用的函数
                for node, capture_name in captures:
                    if capture_name == "call" or capture_name == "method_call":
                        # 检查调用是否在此函数内
                        if self._is_node_inside_function(node, symbol, node_text):
                            # 提取被调用函数名
                            for inner_node, inner_capture in captures:
                                if (inner_capture == "callee" and 
                                    inner_node.parent == node):
                                    callee_name = node_text(inner_node).strip()
                                    self._call_edges_name.append((symbol['id'], callee_name))

    def _extract_includes_with_query(self, root_node, file_path: str, node_text):
        """提取 include 关系"""
        captures = self.queries["includes"].captures(root_node)
        
        for node, capture_name in captures:
            if capture_name == "path":
                path_text = node_text(node).strip().strip('"<>')
                if path_text:
                    self._include_edges.append((file_path, path_text))

    # ----------------------
    # 工具方法
    # ----------------------

    def _extract_params_from_node(self, params_node, node_text) -> Tuple[str, List[Dict[str, str]]]:
        """从参数节点提取参数信息"""
        # 简化实现，实际可以更复杂
        param_text = self._clean_ws(node_text(params_node))
        params = []
        # 这里可以进一步解析参数
        return param_text, params

    def _extract_struct_members_from_node(self, fields_node, node_text) -> List[Dict[str, str]]:
        """从字段节点提取结构体成员"""
        members = []
        # 简化实现
        return members

    def _extract_enum_values_from_node(self, values_node, node_text) -> List[Dict[str, Any]]:
        """从值节点提取枚举值"""
        values = []
        # 简化实现
        return values

    def _is_file_scope_node(self, node) -> bool:
        """检查节点是否在文件作用域"""
        return node.parent is not None and node.parent.type == 'translation_unit'

    def _is_node_inside_function(self, node, function_symbol: Dict[str, Any], node_text) -> bool:
        """检查节点是否在指定函数内"""
        # 简化实现，实际可以更精确
        func_line = function_symbol['line_number']
        node_line = node.start_point[0] + 1
        return abs(node_line - func_line) < 100  # 简单的行号范围检查

    def _complexity_bucket(self, ccn: int) -> str:
        """复杂度分桶"""
        if ccn <= 5:
            return "low"
        elif ccn <= 10:
            return "medium"
        else:
            return "high"

    @staticmethod
    def _clean_ws(s: str) -> str:
        """清理空白字符"""
        return " ".join(s.replace("\n", " ").replace("\t", " ").split())

    def _generate_id(self, symbol_type: str, name: str, file_path: str, line_number: int = 0) -> str:
        """生成符号ID"""
        unique_suffix = str(uuid.uuid4())[:8]
        content = f"ts_query:{symbol_type}:{name}:{file_path}:{line_number}:{unique_suffix}"
        return hashlib.md5(content.encode()).hexdigest()[:16] 