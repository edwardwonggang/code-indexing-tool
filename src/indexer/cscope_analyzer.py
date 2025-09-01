"""
Cscope分析器集成

Cscope是一个经典的C代码浏览和分析工具，专门用于：
- 查找函数定义和调用关系
- 查找变量定义和引用
- 查找文本字符串和正则表达式
- 生成交叉引用数据库
- 构建调用图和依赖关系

官方网站: http://cscope.sourceforge.net/
GitHub: https://github.com/jonathangray/cscope
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger


class CscopeAnalyzer:
    """基于Cscope的C代码分析器"""

    def __init__(self):
        """初始化Cscope分析器"""
        self.supported_extensions = {".c", ".h", ".cpp", ".cxx", ".cc", ".hpp", ".hxx"}
        self._verify_cscope_installation()

    def analyze_project(self, project_path: Path) -> Dict[str, Any]:
        """
        使用Cscope分析整个项目
        
        Args:
            project_path: 项目根目录
            
        Returns:
            分析结果包含符号、调用关系、引用关系等
        """
        project_path = project_path.resolve()
        if not project_path.exists():
            raise ValueError(f"项目路径不存在: {project_path}")
        
        # 如果Cscope不可用，返回空结果
        if not getattr(self, 'cscope_available', False):
            logger.info("Cscope不可用，跳过Cscope分析")
            return {
                "symbols": [],
                "call_graph": {"nodes": [], "edges": []},
                "references": [],
                "metadata": {"tool": "cscope", "status": "unavailable"}
            }
        
        logger.info(f"开始Cscope分析: {project_path}")
        
        try:
            # 检查是否有C/C++文件
            source_files = self._find_source_files(project_path)
            if not source_files:
                logger.info("项目中未找到C/C++文件，跳过Cscope分析")
                return self._create_empty_result()
            
            logger.info(f"找到 {len(source_files)} 个源文件")
            
            # 构建Cscope数据库
            db_path = self._build_cscope_database(project_path, source_files)
            
            # 提取各种分析结果
            symbols = self._extract_symbols(db_path, project_path)
            call_relations = self._extract_call_relations(db_path, project_path)
            references = self._extract_references(db_path, project_path)
            
            logger.info(f"Cscope分析完成，发现 {len(symbols)} 个符号，{len(call_relations)} 个调用关系")
            
            return {
                "status": "success",
                "total_symbols": len(symbols),
                "total_call_relations": len(call_relations),
                "total_references": len(references),
                "symbols": symbols,
                "call_relations": call_relations,
                "references": references,
                "metadata": {
                    "analyzer": "cscope",
                    "project_path": str(project_path),
                    "files_analyzed": len(source_files),
                    "database_path": str(db_path)
                }
            }
            
        except Exception as e:
            logger.error(f"Cscope分析异常: {e}")
            return self._create_error_result("Cscope analysis failed", str(e))

    def find_symbol_definition(self, db_path: Path, symbol_name: str) -> List[Dict[str, Any]]:
        """
        查找符号定义（官方查询类型0）
        
        Args:
            db_path: Cscope数据库路径
            symbol_name: 符号名称
            
        Returns:
            符号定义列表
        """
        return self._execute_cscope_query(db_path, "0", symbol_name, "symbol_definition")

    def find_function_definition(self, db_path: Path, function_name: str) -> List[Dict[str, Any]]:
        """
        查找函数定义（官方查询类型1）
        
        Args:
            db_path: Cscope数据库路径
            function_name: 函数名称
            
        Returns:
            函数定义列表
        """
        return self._execute_cscope_query(db_path, "1", function_name, "function_definition")

    def find_functions_called_by(self, db_path: Path, function_name: str) -> List[Dict[str, Any]]:
        """
        查找指定函数调用的其他函数（官方查询类型2）
        
        Args:
            db_path: Cscope数据库路径
            function_name: 函数名称
            
        Returns:
            被调用函数列表
        """
        return self._execute_cscope_query(db_path, "2", function_name, "called_functions")

    def find_function_calls(self, db_path: Path, function_name: str) -> List[Dict[str, Any]]:
        """
        查找调用指定函数的其他函数（官方查询类型3）
        
        Args:
            db_path: Cscope数据库路径
            function_name: 函数名称
            
        Returns:
            函数调用列表
        """
        return self._execute_cscope_query(db_path, "3", function_name, "function_calls")

    def find_text_string(self, db_path: Path, text: str) -> List[Dict[str, Any]]:
        """
        查找文本字符串（官方查询类型4）
        
        Args:
            db_path: Cscope数据库路径
            text: 要查找的文本
            
        Returns:
            包含该文本的位置列表
        """
        return self._execute_cscope_query(db_path, "4", text, "text_occurrences")

    def find_egrep_pattern(self, db_path: Path, pattern: str) -> List[Dict[str, Any]]:
        """
        查找egrep模式（官方查询类型6）
        
        Args:
            db_path: Cscope数据库路径
            pattern: 正则表达式模式
            
        Returns:
            匹配模式的位置列表
        """
        return self._execute_cscope_query(db_path, "6", pattern, "egrep_matches")

    def find_file(self, db_path: Path, filename: str) -> List[Dict[str, Any]]:
        """
        查找文件（官方查询类型7）
        
        Args:
            db_path: Cscope数据库路径
            filename: 文件名
            
        Returns:
            匹配的文件列表
        """
        return self._execute_cscope_query(db_path, "7", filename, "file_matches")

    def find_files_including(self, db_path: Path, filename: str) -> List[Dict[str, Any]]:
        """
        查找包含指定文件的其他文件（官方查询类型8）
        
        Args:
            db_path: Cscope数据库路径
            filename: 被包含的文件名
            
        Returns:
            包含该文件的文件列表
        """
        return self._execute_cscope_query(db_path, "8", filename, "including_files")

    def find_symbol_references(self, db_path: Path, symbol_name: str) -> List[Dict[str, Any]]:
        """
        查找符号引用
        
        Args:
            db_path: Cscope数据库路径
            symbol_name: 符号名称
            
        Returns:
            符号引用列表
        """
        try:
            # 使用cscope命令查找符号引用 (-L 4)
            cmd = ["cscope", "-d", "-L", "-4", symbol_name, "-f", str(db_path)]
            result = self._run_cscope_command(cmd)
            
            references = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    reference = self._parse_cscope_output_line(line)
                    if reference:
                        references.append(reference)
            
            return references
            
        except Exception as e:
            logger.error(f"查找符号引用失败 {symbol_name}: {e}")
            return []

    def get_call_graph(self, db_path: Path, function_name: str, depth: int = 2) -> Dict[str, Any]:
        """
        获取函数调用图
        
        Args:
            db_path: Cscope数据库路径
            function_name: 函数名称
            depth: 分析深度
            
        Returns:
            调用图数据
        """
        try:
            nodes = set()
            edges = []
            visited = set()
            
            def traverse_calls(func_name: str, current_depth: int):
                if current_depth > depth or func_name in visited:
                    return
                
                visited.add(func_name)
                nodes.add(func_name)
                
                # 查找该函数调用的其他函数
                calls = self.find_function_calls(db_path, func_name)
                for call in calls:
                    called_func = call.get("function_name", "")
                    if called_func and called_func != func_name:
                        nodes.add(called_func)
                        edges.append({
                            "caller": func_name,
                            "callee": called_func,
                            "file_path": call.get("file_path", ""),
                            "line_number": call.get("line_number", 0)
                        })
                        traverse_calls(called_func, current_depth + 1)
            
            traverse_calls(function_name, 0)
            
            return {
                "root_function": function_name,
                "nodes": list(nodes),
                "edges": edges,
                "depth": depth,
                "total_functions": len(nodes),
                "total_calls": len(edges)
            }
            
        except Exception as e:
            logger.error(f"获取调用图失败 {function_name}: {e}")
            return {"nodes": [], "edges": []}

    # ----------------------
    # 私有方法
    # ----------------------

    def _verify_cscope_installation(self) -> None:
        """验证Cscope是否已安装"""
        try:
            # 首先尝试直接运行 cscope
            from ..utils.windows_compat import run_command_safe
            result = run_command_safe(["cscope", "-V"], timeout=10)
            
            if result.returncode == 0:
                # cscope版本信息输出到stderr而不是stdout
                version_info = result.stderr.strip() or result.stdout.strip()
                if version_info:
                    # 提取版本号部分
                    lines = version_info.split('\n')
                    version_line = lines[0] if lines else version_info
                    logger.info(f"✅ Cscope已安装，版本: {version_line}")
                else:
                    logger.info("✅ Cscope已安装 (无版本信息)")
                self.cscope_available = True
                return
                
        except Exception as e:
            logger.debug(f"直接运行cscope失败: {e}")
            
        # 如果直接运行失败，尝试一些常见的路径
        possible_paths = [
            "C:\\tools\\msys64\\usr\\bin\\cscope.exe",
            "C:\\msys64\\usr\\bin\\cscope.exe",
            "C:\\msys32\\usr\\bin\\cscope.exe",
            "C:\\cygwin64\\bin\\cscope.exe",
            "C:\\cygwin\\bin\\cscope.exe",
        ]
        
        for path in possible_paths:
            try:
                if Path(path).exists():
                    result = run_command_safe([path, "-V"], timeout=10)
                    if result.returncode == 0:
                        # cscope版本信息通常在stderr
                        version_output = result.stderr.strip() or result.stdout.strip()
                        version_line = version_output.split('\n')[0] if version_output else "无版本信息"
                        logger.info(f"✅ Cscope已安装，路径: {path}，版本: {version_line}")
                        self.cscope_available = True
                        self.cscope_path = path
                        return
            except Exception as e:
                logger.debug(f"测试路径{path}失败: {e}")
                continue
                
        # 如果都没找到，提供详细的安装指导
        logger.info("⚠️ Cscope未安装或未配置在PATH中，将跳过Cscope分析")
        logger.info("💡 Cscope安装选项（任选一种）：")
        logger.info("   1. 通过MSYS2安装: pacman -S cscope")
        logger.info("   2. 通过Git Bash安装: 下载预编译版本到Git/usr/bin/")
        logger.info("   3. 通过WSL安装: sudo apt-get install cscope")
        logger.info("   4. 通过Chocolatey安装: choco install cscope")
        logger.info("📝 注意：Cscope是可选组件，不影响主要功能")
        self.cscope_available = False

    def _find_source_files(self, project_path: Path) -> List[Path]:
        """查找项目中的源文件"""
        source_files = []
        
        for ext in self.supported_extensions:
            source_files.extend(project_path.rglob(f"*{ext}"))
        
        # 过滤掉一些常见的不需要分析的目录
        excluded_dirs = {"build", "target", "dist", "node_modules", ".git", "__pycache__"}
        
        filtered_files = []
        for file_path in source_files:
            if not any(excluded_dir in file_path.parts for excluded_dir in excluded_dirs):
                filtered_files.append(file_path)
        
        return filtered_files

    def _build_cscope_database(self, project_path: Path, source_files: List[Path]) -> Path:
        """构建Cscope数据库"""
        try:
            # 如果 cscope 不可用，直接抛出异常
            if not getattr(self, 'cscope_available', False):
                raise RuntimeError("Cscope不可用")
                
            # 创建临时目录存放cscope数据库
            db_dir = project_path / ".cscope_tmp"
            db_dir.mkdir(exist_ok=True)

            # 确保目录权限正确
            import stat
            db_dir.chmod(stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

            # 创建文件列表
            file_list_path = (db_dir / "cscope.files").resolve()
            with open(file_list_path, 'w', encoding='utf-8') as f:
                for file_path in source_files:
                    # 使用相对路径避免Windows路径问题
                    try:
                        rel_path = file_path.relative_to(project_path)
                        f.write(f"{rel_path}\n")
                    except ValueError:
                        # 如果无法创建相对路径，使用绝对路径
                        f.write(f"{file_path.resolve()}\n")

            db_path = (db_dir / "cscope.out").resolve()

            # 确保文件列表可读
            file_list_path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
            
            # 获取 cscope 命令路径
            cscope_cmd = getattr(self, 'cscope_path', 'cscope')
            
            # 使用简化的cscope命令，移除有问题的参数
            cmd = [
                cscope_cmd,
                "-b",  # 只构建数据库，不启动界面
                "-f", str(db_path),  # 输出文件
                "-i", str(file_list_path)  # 输入文件列表
            ]

            # 确保输出目录存在且可写
            db_path.parent.mkdir(parents=True, exist_ok=True)

            # 在数据库目录下运行命令，避免路径问题
            from ..utils.windows_compat import run_command_safe
            result = run_command_safe(cmd, cwd=db_path.parent, timeout=300)

            if result.returncode != 0:
                # 尝试更简单的命令
                logger.info(f"标准Cscope命令失败，尝试简化命令")
                logger.debug(f"失败原因: {result.stderr or result.stdout}")

                simple_cmd = [cscope_cmd, "-b", "-R"]
                simple_result = run_command_safe(simple_cmd, cwd=project_path, timeout=300)

                if simple_result.returncode != 0:
                    raise RuntimeError(f"Cscope数据库构建失败: {result.stderr or result.stdout}")
                else:
                    # 移动生成的文件到目标位置
                    default_db = project_path / "cscope.out"
                    if default_db.exists():
                        import shutil
                        shutil.move(str(default_db), str(db_path))
                        logger.info("✅ 使用简化命令成功构建Cscope数据库")
                    else:
                        raise RuntimeError("Cscope数据库文件未生成")
            
            logger.info(f"Cscope数据库构建完成: {db_path}")
            return db_path
            
        except Exception as e:
            logger.error(f"构建Cscope数据库失败: {e}")
            raise

    def _extract_symbols(self, db_path: Path, project_path: Path) -> List[Dict[str, Any]]:
        """从Cscope数据库提取符号"""
        symbols = []
        
        try:
            # 使用多种查询方式来获取更全面的符号信息
            
            # 1. 查找全局定义 (-L 0)
            cmd = [getattr(self, 'cscope_path', 'cscope'), "-d", "-L", "-0", ".*", "-f", str(db_path)]
            result = self._run_cscope_command(cmd)
            
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    symbol = self._parse_cscope_output_line(line)
                    if symbol and symbol.get('function_name') not in ['<global>', '.', '']:
                        symbol.update({
                            "id": self._generate_symbol_id(symbol),
                            "type": "global_definition",
                            "source": "cscope",
                            "description": f"Cscope全局定义: {symbol.get('function_name', '')}"
                        })
                        symbols.append(symbol)
            
            # 2. 查找所有函数定义 (-L 1) - 更精确的函数查询
            # 先尝试查找一些常见的函数模式
            common_patterns = ["cJSON_*", "main", "test_*", "*_test", "*Test*", "unity_*"]
            
            for pattern in common_patterns:
                try:
                    cmd = [getattr(self, 'cscope_path', 'cscope'), "-d", "-L", "-1", pattern, "-f", str(db_path)]
                    result = self._run_cscope_command(cmd)
                    
                    for line in result.stdout.strip().split('\n'):
                        if line.strip():
                            symbol = self._parse_cscope_output_line(line)
                            if symbol and symbol.get('function_name') not in ['<global>', '.', '']:
                                symbol.update({
                                    "id": self._generate_symbol_id(symbol),
                                    "type": "function",
                                    "source": "cscope",
                                    "description": f"Cscope函数: {symbol.get('function_name', '')}"
                                })
                                symbols.append(symbol)
                except Exception as e:
                    logger.debug(f"查询模式 {pattern} 失败: {e}")
            
        except Exception as e:
            logger.warning(f"提取Cscope符号失败: {e}")
        
        # 去重
        unique_symbols = []
        seen_ids = set()
        for symbol in symbols:
            symbol_id = symbol.get('id')
            if symbol_id not in seen_ids:
                unique_symbols.append(symbol)
                seen_ids.add(symbol_id)
        
        logger.info(f"Cscope提取了 {len(unique_symbols)} 个唯一符号")
        return unique_symbols

    def _extract_call_relations(self, db_path: Path, project_path: Path) -> List[Dict[str, Any]]:
        """提取函数调用关系"""
        call_relations = []
        
        try:
            # 查找所有函数调用 (-L 3)
            cmd = ["cscope", "-d", "-L", "-3", ".*", "-f", str(db_path)]
            result = self._run_cscope_command(cmd)
            
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    call = self._parse_cscope_output_line(line)
                    if call:
                        call_relations.append({
                            "caller_context": call.get("context", ""),
                            "callee": call.get("function_name", ""),
                            "file_path": call.get("file_path", ""),
                            "line_number": call.get("line_number", 0),
                            "source": "cscope"
                        })
            
        except Exception as e:
            logger.warning(f"提取调用关系失败: {e}")
        
        return call_relations

    def _extract_references(self, db_path: Path, project_path: Path) -> List[Dict[str, Any]]:
        """提取符号引用"""
        references = []
        
        try:
            # 查找所有符号引用 (-L 4)
            cmd = ["cscope", "-d", "-L", "-4", ".*", "-f", str(db_path)]
            result = self._run_cscope_command(cmd)
            
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    ref = self._parse_cscope_output_line(line)
                    if ref:
                        references.append({
                            "symbol_name": ref.get("function_name", ""),
                            "file_path": ref.get("file_path", ""),
                            "line_number": ref.get("line_number", 0),
                            "context": ref.get("context", ""),
                            "source": "cscope"
                        })
            
        except Exception as e:
            logger.warning(f"提取符号引用失败: {e}")
        
        return references

    def _execute_cscope_query(self, db_path: Path, query_type: str, search_term: str, result_type: str) -> List[Dict[str, Any]]:
        """
        执行Cscope查询（基于官方查询接口）
        
        Args:
            db_path: Cscope数据库路径
            query_type: 查询类型（0-8，对应官方查询类型）
            search_term: 搜索词
            result_type: 结果类型（用于日志和调试）
            
        Returns:
            查询结果列表
        """
        try:
            # 构建官方推荐的Cscope命令
            cmd = [
                "cscope",
                "-d",              # 不更新数据库
                "-L",              # 行级输出模式
                "-p3",             # 显示3级路径组件
                f"-{query_type}",  # 查询类型
                search_term,       # 搜索词
                "-f", str(db_path) # 数据库文件
            ]
            
            result = self._run_cscope_command(cmd)
            
            if result.returncode != 0:
                logger.warning(f"Cscope查询失败 (类型{query_type}): {result.stderr}")
                return []
            
            # 解析输出结果
            results = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parsed_result = self._parse_cscope_output_line(line)
                    if parsed_result:
                        parsed_result["query_type"] = query_type
                        parsed_result["result_type"] = result_type
                        results.append(parsed_result)
            
            logger.debug(f"Cscope查询成功 (类型{query_type}): 找到 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"执行Cscope查询失败 (类型{query_type}): {e}")
            return []

    def _run_cscope_command(self, cmd: List[str]) -> subprocess.CompletedProcess:
        """运行Cscope命令（带超时和错误处理）"""
        from ..utils.windows_compat import run_command_safe
        return run_command_safe(cmd, timeout=60)

    def _parse_cscope_output_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        解析Cscope输出行
        
        Cscope输出格式: filename function_name line_number context
        """
        try:
            parts = line.strip().split(' ', 3)
            if len(parts) >= 3:
                file_path = parts[0]
                function_name = parts[1]
                line_number = int(parts[2])
                context = parts[3] if len(parts) > 3 else ""
                
                # 如果function_name是"<global>"或"."，尝试从context中提取真正的函数名
                if function_name in ["<global>", "."]:
                    # 从context中提取函数名，匹配C函数定义模式
                    import re
                    # 匹配函数定义模式：返回类型 函数名(参数)
                    func_match = re.search(r'\b(\w+)\s*\(', context)
                    if func_match:
                        extracted_name = func_match.group(1)
                        # 过滤一些不是函数名的关键字
                        keywords = {'if', 'for', 'while', 'switch', 'sizeof', 'return', 'printf', 'scanf'}
                        if extracted_name not in keywords:
                            function_name = extracted_name
                
                return {
                    "file_path": file_path,
                    "function_name": function_name,
                    "line_number": line_number,
                    "context": context
                }
        except (ValueError, IndexError) as e:
            logger.debug(f"解析Cscope输出行失败: {line}, 错误: {e}")
        
        return None

    def _generate_symbol_id(self, symbol: Dict[str, Any]) -> str:
        """生成符号ID"""
        import hashlib
        
        content = f"cscope:{symbol.get('function_name', '')}:{symbol.get('file_path', '')}:{symbol.get('line_number', 0)}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _create_empty_result(self) -> Dict[str, Any]:
        """创建空结果"""
        return {
            "status": "success",
            "total_symbols": 0,
            "total_call_relations": 0,
            "total_references": 0,
            "symbols": [],
            "call_relations": [],
            "references": [],
            "metadata": {
                "analyzer": "cscope",
                "note": "No C/C++ files found"
            }
        }

    def _create_error_result(self, message: str, details: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            "status": "error",
            "message": message,
            "details": details,
            "total_symbols": 0,
            "total_call_relations": 0,
            "total_references": 0,
            "symbols": [],
            "call_relations": [],
            "references": [],
            "metadata": {
                "analyzer": "cscope",
                "error": True
            }
        } 