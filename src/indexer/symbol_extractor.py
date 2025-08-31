"""
符号提取器

使用clang的Python绑定解析C代码AST来提取符号信息
"""

from typing import Dict, List, Any, Optional
from pathlib import Path
from loguru import logger
import clang.cindex as clang
import hashlib


class SymbolExtractor:
    """基于clang AST的C语言符号提取器"""
    
    def __init__(self):
        """初始化符号提取器"""
        # 配置clang index
        self.index = clang.Index.create()
        logger.info("clang AST符号提取器初始化完成")
        
    def extract_from_analysis(self, analysis, project_path: Path) -> List[Dict[str, Any]]:
        """
        从项目中提取符号（使用clang AST解析）
        
        Args:
            analysis: CLDK分析对象（不使用）
            project_path: 项目路径
            
        Returns:
            符号信息列表
        """
        symbols = []
        
        try:
            # 获取所有C源文件
            c_files = list(project_path.glob("*.c")) + list(project_path.glob("*.h"))
            
            for file_path in c_files:
                logger.info(f"正在解析文件: {file_path.name}")
                file_symbols = self._extract_file_symbols_with_clang(file_path, project_path)
                symbols.extend(file_symbols)
                
            logger.info(f"符号提取完成，共提取 {len(symbols)} 个符号")
            
        except Exception as e:
            logger.error(f"符号提取失败: {e}")
            raise
            
        return symbols
    
    def _extract_file_symbols_with_clang(self, file_path: Path, project_path: Path) -> List[Dict[str, Any]]:
        """使用clang AST解析单个文件"""
        symbols = []
        
        try:
            # 解析文件生成AST
            translation_unit = self.index.parse(
                str(file_path),
                args=['-std=c99', '-I.']  # C99标准，包含当前目录
            )
            
            if not translation_unit:
                logger.warning(f"无法解析文件: {file_path}")
                return symbols
            
            # 检查解析错误
            for diagnostic in translation_unit.diagnostics:
                if diagnostic.severity >= clang.Diagnostic.Error:
                    logger.warning(f"解析错误 {file_path}: {diagnostic.spelling}")
            
            relative_path = file_path.relative_to(project_path)
            
            # 遍历AST节点提取符号
            self._traverse_ast_node(translation_unit.cursor, str(relative_path), symbols, str(file_path))
            
        except Exception as e:
            logger.error(f"解析文件 {file_path} 失败: {e}")
            
        return symbols
    
    def _traverse_ast_node(self, node, file_path: str, symbols: List[Dict[str, Any]], full_file_path: str):
        """递归遍历AST节点提取符号"""
        
        # 只处理当前文件中的符号（跳过include的文件）
        if node.location.file and str(node.location.file) != full_file_path:
            return
            
        try:
            # 提取不同类型的符号
            if node.kind == clang.CursorKind.FUNCTION_DECL:
                symbol = self._extract_function_from_cursor(node, file_path)
                if symbol:
                    symbols.append(symbol)
                    
            elif node.kind == clang.CursorKind.STRUCT_DECL:
                symbol = self._extract_struct_from_cursor(node, file_path)
                if symbol:
                    symbols.append(symbol)
                    
            elif node.kind == clang.CursorKind.TYPEDEF_DECL:
                symbol = self._extract_typedef_from_cursor(node, file_path)
                if symbol:
                    symbols.append(symbol)
                    
            elif node.kind == clang.CursorKind.VAR_DECL:
                symbol = self._extract_variable_from_cursor(node, file_path)
                if symbol:
                    symbols.append(symbol)
                    
            elif node.kind == clang.CursorKind.MACRO_DEFINITION:
                symbol = self._extract_macro_from_cursor(node, file_path)
                if symbol:
                    symbols.append(symbol)
                    
            elif node.kind == clang.CursorKind.ENUM_DECL:
                symbol = self._extract_enum_from_cursor(node, file_path)
                if symbol:
                    symbols.append(symbol)
                    
        except Exception as e:
            logger.warning(f"处理AST节点时出错: {e}")
        
        # 递归处理子节点
        for child in node.get_children():
            self._traverse_ast_node(child, file_path, symbols, full_file_path)
    
    def _extract_function_from_cursor(self, cursor, file_path: str) -> Optional[Dict[str, Any]]:
        """从游标提取函数信息"""
        try:
            func_name = cursor.spelling
            if not func_name:
                return None
                
            # 获取函数位置信息
            line_number = cursor.location.line
            
            # 获取函数类型信息
            func_type = cursor.type
            return_type = func_type.get_result().spelling if func_type.get_result() else "void"
            
            # 提取参数信息
            parameters = []
            param_strings = []
            for arg in cursor.get_arguments():
                param_name = arg.spelling or f"param{len(parameters)}"
                param_type = arg.type.spelling
                parameters.append({
                    "name": param_name,
                    "type": param_type
                })
                param_strings.append(f"{param_type} {param_name}")
            
            param_string = ", ".join(param_strings)
            
            # 构建函数签名
            signature = f"{return_type} {func_name}({param_string})"
            
            # 检查函数属性
            is_static = cursor.linkage == clang.LinkageKind.INTERNAL
            # 检查是否为内联函数（通过存储类别检查）
            is_inline = cursor.kind == clang.CursorKind.FUNCTION_DECL and 'inline' in cursor.displayname
            
            # 估算函数复杂度（基于AST结构）
            complexity = self._estimate_function_complexity(cursor)
            
            return {
                'id': self._generate_id('function', func_name, file_path, line_number),
                'name': func_name,
                'type': 'function',
                'file_path': file_path,
                'line_number': line_number,
                'declaration': signature,
                'return_type': return_type,
                'parameters': param_string,
                'parameter_list': parameters,
                'is_static': is_static,
                'is_inline': is_inline,
                'complexity': complexity,
                'description': f"函数 {func_name} 返回 {return_type}"
            }
            
        except Exception as e:
            logger.warning(f"提取函数信息失败: {e}")
            return None
    
    def _extract_struct_from_cursor(self, cursor, file_path: str) -> Optional[Dict[str, Any]]:
        """从游标提取结构体信息"""
        try:
            struct_name = cursor.spelling
            if not struct_name:
                return None
                
            line_number = cursor.location.line
            
            # 提取结构体成员
            members = []
            for child in cursor.get_children():
                if child.kind == clang.CursorKind.FIELD_DECL:
                    member_name = child.spelling
                    member_type = child.type.spelling
                    members.append({
                        "name": member_name,
                        "type": member_type
                    })
            
            # 获取结构体声明
            declaration = f"struct {struct_name}"
            if members:
                member_decls = [f"  {m['type']} {m['name']};" for m in members]
                declaration += " {\n" + "\n".join(member_decls) + "\n}"
            
            return {
                'id': self._generate_id('structure', struct_name, file_path, line_number),
                'name': struct_name,
                'type': 'structure',
                'file_path': file_path,
                'line_number': line_number,
                'declaration': declaration,
                'members': members,
                'member_count': len(members),
                'description': f"结构体 {struct_name} 包含 {len(members)} 个成员"
            }
            
        except Exception as e:
            logger.warning(f"提取结构体信息失败: {e}")
            return None
    
    def _extract_typedef_from_cursor(self, cursor, file_path: str) -> Optional[Dict[str, Any]]:
        """从游标提取typedef信息"""
        try:
            typedef_name = cursor.spelling
            if not typedef_name:
                return None
                
            line_number = cursor.location.line
            underlying_type = cursor.underlying_typedef_type.spelling
            
            return {
                'id': self._generate_id('typedef', typedef_name, file_path, line_number),
                'name': typedef_name,
                'type': 'typedef',
                'file_path': file_path,
                'line_number': line_number,
                'declaration': f"typedef {underlying_type} {typedef_name}",
                'underlying_type': underlying_type,
                'description': f"类型定义 {typedef_name} -> {underlying_type}"
            }
            
        except Exception as e:
            logger.warning(f"提取typedef信息失败: {e}")
            return None
    
    def _extract_variable_from_cursor(self, cursor, file_path: str) -> Optional[Dict[str, Any]]:
        """从游标提取变量信息"""
        try:
            var_name = cursor.spelling
            if not var_name:
                return None
                
            line_number = cursor.location.line
            var_type = cursor.type.spelling
            
            # 检查变量属性
            is_static = cursor.linkage == clang.LinkageKind.INTERNAL
            is_const = cursor.type.is_const_qualified()
            
            return {
                'id': self._generate_id('variable', var_name, file_path, line_number),
                'name': var_name,
                'type': 'variable',
                'file_path': file_path,
                'line_number': line_number,
                'declaration': f"{var_type} {var_name}",
                'data_type': var_type,
                'is_static': is_static,
                'is_const': is_const,
                'description': f"变量 {var_name} 类型为 {var_type}"
            }
            
        except Exception as e:
            logger.warning(f"提取变量信息失败: {e}")
            return None
    
    def _extract_macro_from_cursor(self, cursor, file_path: str) -> Optional[Dict[str, Any]]:
        """从游标提取宏定义信息"""
        try:
            macro_name = cursor.spelling
            if not macro_name:
                return None
                
            line_number = cursor.location.line
            
            # 获取宏的源码范围来提取定义
            source_range = cursor.extent
            
            return {
                'id': self._generate_id('macro', macro_name, file_path, line_number),
                'name': macro_name,
                'type': 'macro',
                'file_path': file_path,
                'line_number': line_number,
                'declaration': f"#define {macro_name}",
                'description': f"宏定义 {macro_name}"
            }
            
        except Exception as e:
            logger.warning(f"提取宏信息失败: {e}")
            return None
    
    def _extract_enum_from_cursor(self, cursor, file_path: str) -> Optional[Dict[str, Any]]:
        """从游标提取枚举信息"""
        try:
            enum_name = cursor.spelling
            if not enum_name:
                return None
                
            line_number = cursor.location.line
            
            # 提取枚举值
            enum_values = []
            for child in cursor.get_children():
                if child.kind == clang.CursorKind.ENUM_CONSTANT_DECL:
                    enum_values.append({
                        "name": child.spelling,
                        "value": child.enum_value
                    })
            
            return {
                'id': self._generate_id('enum', enum_name, file_path, line_number),
                'name': enum_name,
                'type': 'enum',
                'file_path': file_path,
                'line_number': line_number,
                'declaration': f"enum {enum_name}",
                'values': enum_values,
                'description': f"枚举 {enum_name} 包含 {len(enum_values)} 个值"
            }
            
        except Exception as e:
            logger.warning(f"提取枚举信息失败: {e}")
            return None
    
    def _estimate_function_complexity(self, cursor) -> str:
        """基于AST结构估算函数复杂度"""
        complexity_count = 0
        
        def count_complexity_nodes(node):
            nonlocal complexity_count
            
            # 计算控制流语句
            if node.kind in [
                clang.CursorKind.IF_STMT,
                clang.CursorKind.WHILE_STMT,
                clang.CursorKind.FOR_STMT,
                clang.CursorKind.SWITCH_STMT,
                clang.CursorKind.CASE_STMT,
                clang.CursorKind.DO_STMT,
            ]:
                complexity_count += 1
            
            # 递归处理子节点
            for child in node.get_children():
                count_complexity_nodes(child)
        
        count_complexity_nodes(cursor)
        
        if complexity_count <= 2:
            return "low"
        elif complexity_count <= 5:
            return "medium"
        else:
            return "high"
    
    def _generate_id(self, symbol_type: str, name: str, file_path: str, line_number: int = 0) -> str:
        """生成符号唯一ID"""
        import uuid
        # 使用文件路径、符号类型、名称、行号和UUID确保绝对唯一性
        unique_suffix = str(uuid.uuid4())[:8]
        content = f"{symbol_type}:{name}:{file_path}:{line_number}:{unique_suffix}"
        return hashlib.md5(content.encode()).hexdigest()[:16] 