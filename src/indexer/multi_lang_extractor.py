"""
多语言代码符号提取器
支持C/C++/Python/JavaScript等多种语言的统一符号提取
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
        logger.warning("Tree-sitter Query 不可用，多语言提取器将跳过高级查询功能")

from tree_sitter_languages import get_language, get_parser
import lizard


class MultiLanguageExtractor:
    """多语言符号提取器"""

    def __init__(self):
        """初始化多语言提取器"""
        if not QUERY_AVAILABLE:
            raise ImportError("tree-sitter 库未安装或 Query 不可用")
        
        # 支持的语言映射
        self.language_map = {
            "c": {
                "extensions": [".c", ".h"],
                "parser": None,
                "language": None
            },
            "cpp": {
                "extensions": [".cpp", ".cxx", ".cc", ".hpp", ".hxx"],
                "parser": None,
                "language": None
            },
            "go": {
                "extensions": [".go"],
                "parser": None,
                "language": None
            },
            "rust": {
                "extensions": [".rs"],
                "parser": None,
                "language": None
            },
            "python": {
                "extensions": [".py"],
                "parser": None,
                "language": None
            },
            "javascript": {
                "extensions": [".js", ".jsx"],
                "parser": None,
                "language": None
            },
            "typescript": {
                "extensions": [".ts", ".tsx"],
                "parser": None,
                "language": None
            }
        }
        
        # 初始化可用的语言解析器
        self._init_parsers()
        
        # 语言特定的查询
        self.queries = {}
        self._compile_language_queries()

    def extract_project(self, project_path: Path, target_languages: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        提取项目符号
        
        Args:
            project_path: 项目根路径
            target_languages: 目标语言列表，None 表示所有支持的语言
        
        Returns:
            符号列表
        """
        project_path = project_path.resolve()
        if not project_path.exists():
            raise ValueError(f"项目路径不存在: {project_path}")
        
        logger.info(f"开始多语言符号提取: {project_path}")
        
        symbols: List[Dict[str, Any]] = []
        file_count_by_lang = {}
        
        # 收集各语言文件
        language_files = self._collect_language_files(project_path, target_languages)
        
        # 按语言处理文件
        for language, files in language_files.items():
            if not files:
                continue
                
            logger.info(f"处理 {language} 文件 {len(files)} 个")
            file_count_by_lang[language] = len(files)
            
            try:
                lang_symbols = self._extract_language_symbols(language, files, project_path)
                symbols.extend(lang_symbols)
                logger.info(f"{language} 符号提取完成，共 {len(lang_symbols)} 个")
            except Exception as e:
                logger.error(f"提取 {language} 符号失败: {e}")
        
        logger.info(f"多语言符号提取完成，总计 {len(symbols)} 个符号，涵盖 {len(file_count_by_lang)} 种语言")
        return symbols

    def get_supported_languages(self) -> List[str]:
        """获取支持的语言列表"""
        return [lang for lang, info in self.language_map.items() if info["parser"] is not None]

    def detect_file_language(self, file_path: Path) -> Optional[str]:
        """检测文件语言"""
        suffix = file_path.suffix.lower()
        for language, info in self.language_map.items():
            if suffix in info["extensions"]:
                return language
        return None

    # ----------------------
    # 私有方法
    # ----------------------

    def _init_parsers(self):
        """初始化语言解析器"""
        for language, info in self.language_map.items():
            try:
                # 尝试获取解析器
                parser = get_parser(language)
                lang_obj = get_language(language)
                
                info["parser"] = parser
                info["language"] = lang_obj
                logger.debug(f"初始化 {language} 解析器成功")
            except Exception as e:
                logger.warning(f"初始化 {language} 解析器失败: {e}")

    def _compile_language_queries(self):
        """编译各语言的查询"""
        # C/C++ 查询
        c_cpp_queries = {
            "functions": """
            (function_definition
              declarator: (function_declarator
                declarator: (identifier) @name
              )
            ) @function
            """,
            "classes": """
            (class_specifier
              name: (type_identifier) @name
            ) @class
            """,
            "structs": """
            (struct_specifier
              name: (type_identifier)? @name
            ) @struct
            """
        }
        
        # Go 查询
        go_queries = {
            "functions": """
            (function_declaration
              name: (identifier) @name
            ) @function
            (method_declaration
              name: (field_identifier) @name
            ) @method
            """,
            "types": """
            (type_declaration
              (type_spec
                name: (type_identifier) @name
              )
            ) @type
            """,
            "structs": """
            (struct_type) @struct
            """
        }
        
        # Rust 查询
        rust_queries = {
            "functions": """
            (function_item
              name: (identifier) @name
            ) @function
            """,
            "structs": """
            (struct_item
              name: (type_identifier) @name
            ) @struct
            """,
            "enums": """
            (enum_item
              name: (type_identifier) @name
            ) @enum
            """,
            "traits": """
            (trait_item
              name: (type_identifier) @name
            ) @trait
            """
        }
        
        # Python 查询
        python_queries = {
            "functions": """
            (function_definition
              name: (identifier) @name
            ) @function
            """,
            "classes": """
            (class_definition
              name: (identifier) @name
            ) @class
            """
        }
        
        # JavaScript/TypeScript 查询
        js_queries = {
            "functions": """
            (function_declaration
              name: (identifier) @name
            ) @function
            (arrow_function) @arrow_function
            """,
            "classes": """
            (class_declaration
              name: (identifier) @name
            ) @class
            """
        }
        
        # 编译查询
        query_map = {
            "c": c_cpp_queries,
            "cpp": c_cpp_queries,
            "go": go_queries,
            "rust": rust_queries,
            "python": python_queries,
            "javascript": js_queries,
            "typescript": js_queries
        }
        
        for language, queries in query_map.items():
            if language in self.language_map and self.language_map[language]["language"]:
                lang_obj = self.language_map[language]["language"]
                compiled_queries = {}
                
                for query_name, query_str in queries.items():
                    try:
                        compiled_queries[query_name] = Query(lang_obj, query_str)
                    except Exception as e:
                        logger.warning(f"编译 {language} {query_name} 查询失败: {e}")
                
                self.queries[language] = compiled_queries

    def _collect_language_files(self, project_path: Path, target_languages: Optional[List[str]]) -> Dict[str, List[Path]]:
        """收集各语言的文件"""
        language_files = {lang: [] for lang in self.language_map.keys()}
        
        # 遍历项目文件
        for file_path in project_path.rglob("*"):
            if not file_path.is_file():
                continue
            
            language = self.detect_file_language(file_path)
            if language and (target_languages is None or language in target_languages):
                if self.language_map[language]["parser"]:  # 只处理有解析器的语言
                    language_files[language].append(file_path)
        
        return language_files

    def _extract_language_symbols(self, language: str, files: List[Path], project_path: Path) -> List[Dict[str, Any]]:
        """提取特定语言的符号"""
        symbols = []
        
        parser = self.language_map[language]["parser"]
        queries = self.queries.get(language, {})
        
        if not parser:
            logger.warning(f"没有 {language} 解析器")
            return symbols
        
        for file_path in files:
            try:
                source_bytes = file_path.read_bytes()
                tree = parser.parse(source_bytes)
                
                file_symbols = self._extract_file_symbols(
                    language, tree, file_path, project_path, source_bytes, queries
                )
                symbols.extend(file_symbols)
                
            except Exception as e:
                logger.warning(f"解析 {language} 文件 {file_path} 失败: {e}")
        
        return symbols

    def _extract_file_symbols(
        self, 
        language: str, 
        tree, 
        file_path: Path, 
        project_path: Path, 
        source: bytes, 
        queries: Dict[str, Query]
    ) -> List[Dict[str, Any]]:
        """从单个文件提取符号"""
        symbols = []
        rel_path = str(file_path.relative_to(project_path)).replace("\\", "/")
        
        def node_text(node) -> str:
            return source[node.start_byte:node.end_byte].decode(errors="ignore")
        
        # 根据语言类型提取符号
        if language in ["c", "cpp"]:
            symbols.extend(self._extract_c_cpp_symbols(tree.root_node, rel_path, node_text, queries))
        elif language == "go":
            symbols.extend(self._extract_go_symbols(tree.root_node, rel_path, node_text, queries))
        elif language == "rust":
            symbols.extend(self._extract_rust_symbols(tree.root_node, rel_path, node_text, queries))
        elif language == "python":
            symbols.extend(self._extract_python_symbols(tree.root_node, rel_path, node_text, queries))
        elif language in ["javascript", "typescript"]:
            symbols.extend(self._extract_js_symbols(tree.root_node, rel_path, node_text, queries))
        
        return symbols

    def _extract_c_cpp_symbols(self, root_node, file_path: str, node_text, queries: Dict[str, Query]) -> List[Dict[str, Any]]:
        """提取 C/C++ 符号"""
        symbols = []
        
        # 提取函数
        if "functions" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["functions"], "function", file_path, node_text
            ))
        
        # 提取类（C++）
        if "classes" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["classes"], "class", file_path, node_text
            ))
        
        # 提取结构体
        if "structs" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["structs"], "structure", file_path, node_text
            ))
        
        return symbols

    def _extract_go_symbols(self, root_node, file_path: str, node_text, queries: Dict[str, Query]) -> List[Dict[str, Any]]:
        """提取 Go 符号"""
        symbols = []
        
        # 提取函数和方法
        if "functions" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["functions"], "function", file_path, node_text
            ))
        
        # 提取类型
        if "types" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["types"], "type", file_path, node_text
            ))
        
        return symbols

    def _extract_rust_symbols(self, root_node, file_path: str, node_text, queries: Dict[str, Query]) -> List[Dict[str, Any]]:
        """提取 Rust 符号"""
        symbols = []
        
        # 提取函数
        if "functions" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["functions"], "function", file_path, node_text
            ))
        
        # 提取结构体
        if "structs" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["structs"], "structure", file_path, node_text
            ))
        
        # 提取枚举
        if "enums" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["enums"], "enum", file_path, node_text
            ))
        
        # 提取 trait
        if "traits" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["traits"], "trait", file_path, node_text
            ))
        
        return symbols

    def _extract_python_symbols(self, root_node, file_path: str, node_text, queries: Dict[str, Query]) -> List[Dict[str, Any]]:
        """提取 Python 符号"""
        symbols = []
        
        # 提取函数
        if "functions" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["functions"], "function", file_path, node_text
            ))
        
        # 提取类
        if "classes" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["classes"], "class", file_path, node_text
            ))
        
        return symbols

    def _extract_js_symbols(self, root_node, file_path: str, node_text, queries: Dict[str, Query]) -> List[Dict[str, Any]]:
        """提取 JavaScript/TypeScript 符号"""
        symbols = []
        
        # 提取函数
        if "functions" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["functions"], "function", file_path, node_text
            ))
        
        # 提取类
        if "classes" in queries:
            symbols.extend(self._extract_generic_symbols(
                root_node, queries["classes"], "class", file_path, node_text
            ))
        
        return symbols

    def _extract_generic_symbols(
        self, 
        root_node, 
        query: Query, 
        symbol_type: str, 
        file_path: str, 
        node_text
    ) -> List[Dict[str, Any]]:
        """通用符号提取"""
        symbols = []
        captures = query.captures(root_node)
        
        # 按符号分组
        symbol_captures = {}
        for node, capture_name in captures:
            if capture_name in (symbol_type, "name"):
                if capture_name == symbol_type:
                    symbol_captures[node.id] = {"node": node, "type": symbol_type}
                elif node.parent and node.parent.id in symbol_captures:
                    symbol_captures[node.parent.id]["name"] = node
        
        for symbol_data in symbol_captures.values():
            if "name" not in symbol_data:
                continue
            
            symbol_node = symbol_data["node"]
            name_node = symbol_data["name"]
            
            symbol_name = node_text(name_node).strip()
            line_number = symbol_node.start_point[0] + 1
            
            symbol = {
                'id': self._generate_id(symbol_type, symbol_name, file_path, line_number),
                'name': symbol_name,
                'type': symbol_type,
                'file_path': file_path,
                'line_number': line_number,
                'declaration': self._clean_ws(node_text(symbol_node)[:200]),  # 限制长度
                'description': f"{symbol_type} {symbol_name} (multi-lang)"
            }
            symbols.append(symbol)
        
        return symbols

    @staticmethod
    def _clean_ws(s: str) -> str:
        """清理空白字符"""
        return " ".join(s.replace("\n", " ").replace("\t", " ").split())

    def _generate_id(self, symbol_type: str, name: str, file_path: str, line_number: int = 0) -> str:
        """生成符号ID"""
        unique_suffix = str(uuid.uuid4())[:8]
        content = f"multilang:{symbol_type}:{name}:{file_path}:{line_number}:{unique_suffix}"
        return hashlib.md5(content.encode()).hexdigest()[:16] 