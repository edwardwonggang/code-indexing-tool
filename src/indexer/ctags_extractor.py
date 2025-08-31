"""
CTags 符号提取器

使用 universal-ctags 直接扫描 C 项目，输出传统格式，再解析为内部统一符号结构。

⚠ 依赖：需要系统安装 universal-ctags，并位于 PATH 中。
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger


class CTagsExtractor:
    """基于 universal-ctags 的符号提取器"""

    def extract_project(self, project_path: Path) -> List[Dict[str, Any]]:
        project_path = project_path.resolve()
        if not project_path.exists():
            raise ValueError(f"项目路径不存在: {project_path}")

        logger.info("CTags 开始扫描项目: {}".format(project_path))
        symbols: List[Dict[str, Any]] = []

        # 使用唯一的临时文件名避免冲突
        import time
        import os
        temp_suffix = f"_{int(time.time())}_{os.getpid()}.tags"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=temp_suffix) as tmpf:
            tmpf_path = tmpf.name
        
        try:
            # 确保临时文件被删除（如果存在）
            if Path(tmpf_path).exists():
                Path(tmpf_path).unlink()
                
            # 基于兼容性的CTags命令构建
            cmd = [
                "ctags",
                # 核心语言设置
                "--languages=C,C++",
                
                # 字段配置（兼容性更好的字段集）
                "--fields=+n+k+S+l+f+t+z",  
                # n: 行号, k: 类型, S: 签名, l: 语言, f: 文件范围, t: 类型和原型, z: 作用域
                
                # 扩展功能
                "--extras=+q+f+r",
                # q: 限定名称, f: 文件名标签, r: 引用标签
                
                # 使用传统的标准格式而不是JSON
                "--output-encoding=utf-8",
                
                # 强制覆盖已存在的文件
                "--append=no",
                
                # 符号类型配置
                "--c-kinds=+p+x",     # 函数原型 + 外部变量
                "--c++-kinds=+p+x",   # C++函数原型 + 外部变量
                
                # 递归扫描
                "-R",
                
                # 排除不必要的文件
                "--exclude=*.min.js",
                "--exclude=*.bundle.js", 
                "--exclude=node_modules",
                "--exclude=.git",
                "--exclude=*.o",
                "--exclude=*.so",
                "--exclude=*.dll",
                
                # 输出文件
                "-f", tmpf_path,
                
                # 目标路径
                str(project_path),
            ]
            try:
                from ..utils.windows_compat import run_command_safe
                result = run_command_safe(cmd, timeout=300)
                if result.returncode != 0:
                    logger.error(f"ctags 运行失败: {result.stderr}")
                    return []
            except Exception as e:
                logger.error(f"ctags 执行失败: {e}")
                return []

            # 验证文件是否创建成功
            if not Path(tmpf_path).exists():
                logger.error("CTags 未能创建输出文件")
                return []
                
            # 解析传统的 tags 格式
            try:
                with open(tmpf_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            line = line.strip()
                            if line and not line.startswith('!'):  # 跳过注释行
                                symbol = self._parse_tags_line(line, project_path)
                                if symbol:
                                    symbols.append(symbol)
                        except Exception as e:
                            logger.debug(f"解析 ctags 行失败: {e}")
            except Exception as e:
                logger.error(f"读取 ctags 输出失败: {e}")
                
        finally:
            # 确保清理临时文件
            try:
                if Path(tmpf_path).exists():
                    Path(tmpf_path).unlink()
            except Exception as e:
                logger.debug(f"清理临时文件失败: {e}")

        logger.info(f"CTags 完成，共提取 {len(symbols)} 个符号")
        return symbols

    # ----------------------
    # 私有方法
    # ----------------------

    def _parse_tags_line(self, line: str, project_path: Path) -> Optional[Dict[str, Any]]:
        """解析传统的CTags输出格式"""
        try:
            # 传统 tags 格式: symbol_name<TAB>file_path<TAB>ex_cmd;"<TAB>extensions
            parts = line.split('\t')
            if len(parts) < 3:
                return None
            
            name = parts[0]
            file_path = parts[1]
            ex_cmd = parts[2]
            
            # 提取行号（从 ex_cmd 中）
            line_number = 1
            if ex_cmd.isdigit():
                line_number = int(ex_cmd)
            elif ';' in ex_cmd:
                # 处理类似 "/^function_name($/;" 格式
                try:
                    # 尝试从扩展字段中获取行号
                    for part in parts[3:]:
                        if part.startswith('line:'):
                            line_number = int(part.split(':')[1])
                            break
                except:
                    pass
            
            # 提取符号类型
            symbol_type = "variable"  # 默认类型
            scope = None
            signature = None
            language = None
            
            # 解析扩展字段
            for part in parts[3:]:
                if '\t' in part:
                    continue
                if part.startswith('kind:'):
                    kind = part.split(':', 1)[1]
                    symbol_type = self._map_ctags_kind(kind)
                elif part.startswith('scope:'):
                    scope = part.split(':', 1)[1]
                elif part.startswith('signature:'):
                    signature = part.split(':', 1)[1]
                elif part.startswith('language:'):
                    language = part.split(':', 1)[1]
                elif part.startswith('line:'):
                    try:
                        line_number = int(part.split(':')[1])
                    except:
                        pass
            
            # 使用 Windows 兼容的路径处理
            from ..utils.windows_compat import normalize_path
            try:
                rel_path = normalize_path(Path(file_path).relative_to(project_path))
            except:
                rel_path = file_path

            # 构建符号信息
            symbol = {
                "id": self._generate_id(symbol_type, name, rel_path, line_number),
                "name": name,
                "type": symbol_type,
                "file_path": rel_path,
                "line_number": line_number,
                "source": "ctags"
            }
            
            # 添加可选字段
            if scope:
                symbol["scope"] = scope
            if signature:
                symbol["signature"] = signature
            if language:
                symbol["language"] = language
                
            # 构建声明和描述
            declaration_parts = []
            if signature:
                declaration_parts.append(signature)
            if name:
                declaration_parts.append(name)
            
            symbol["declaration"] = " ".join(declaration_parts) if declaration_parts else name
            
            scope_info = f" 在 {scope}" if scope else ""
            symbol["description"] = f"CTags检测到的{symbol_type}: {name}{scope_info}"
            
            return symbol
            
        except Exception as e:
            logger.debug(f"解析CTags行失败: {line}, 错误: {e}")
            return None

    def _map_ctags_kind(self, kind: str) -> str:
        """映射CTags的符号类型到内部类型"""
        type_mapping = {
            "function": "function",
            "f": "function",            # C函数
            "method": "function",       # C++方法
            "m": "function",           # C++成员函数
            "struct": "structure",
            "s": "structure",          # C结构体
            "class": "structure",      # C++类
            "c": "structure",          # C++类
            "union": "structure",
            "u": "structure",          # C联合体
            "macro": "macro",
            "d": "macro",              # #define宏
            "variable": "variable",
            "v": "variable",           # 变量
            "member": "variable",      # 结构体成员
            "typedef": "typedef",
            "t": "typedef",            # typedef定义
            "enum": "enum",
            "e": "enum",               # 枚举
            "g": "enum",               # 枚举成员
            "prototype": "function",   # 函数原型
            "p": "function",           # 函数原型
            "namespace": "namespace",
            "n": "namespace",          # 命名空间
        }
        
        return type_mapping.get(kind, "variable")

    def _generate_id(self, symbol_type: str, name: str, file_path: str, line_number: int = 0) -> str:
        import hashlib
        content = f"ctags:{symbol_type}:{name}:{file_path}:{line_number}"
        return hashlib.md5(content.encode()).hexdigest()[:16] 