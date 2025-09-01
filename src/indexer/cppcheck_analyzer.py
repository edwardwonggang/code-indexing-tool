"""
Cppcheck集成分析器

Cppcheck是一个成熟的C/C++静态分析工具，专注于：
- 内存泄漏检测
- 缓冲区溢出检测
- 未初始化变量
- 死代码检测
- 类型转换错误
- 并发问题

官方网站: https://cppcheck.sourceforge.io/
GitHub: https://github.com/danmar/cppcheck
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger


class CppcheckAnalyzer:
    """基于Cppcheck的C/C++静态分析器"""

    def __init__(self, config_file: Optional[Path] = None):
        """
        初始化Cppcheck分析器
        
        Args:
            config_file: Cppcheck配置文件路径
        """
        self.config_file = config_file
        self.supported_extensions = {".c", ".cpp", ".cxx", ".cc", ".h", ".hpp", ".hxx"}
        self._verify_cppcheck_installation()

    def analyze_project(self, project_path: Path) -> Dict[str, Any]:
        """
        使用Cppcheck分析整个项目
        
        Args:
            project_path: 项目根目录
            
        Returns:
            分析结果
        """
        project_path = project_path.resolve()
        if not project_path.exists():
            raise ValueError(f"项目路径不存在: {project_path}")
        
        logger.info(f"开始Cppcheck分析: {project_path}")
        
        try:
            # 检查是否有C/C++文件
            cpp_files = self._find_cpp_files(project_path)
            if not cpp_files:
                logger.info("项目中未找到C/C++文件，跳过Cppcheck分析")
                return self._create_empty_result()
            
            logger.info(f"找到 {len(cpp_files)} 个C/C++文件")
            
            # 构建Cppcheck命令
            cmd = self._build_cppcheck_command(project_path)
            
            # 执行Cppcheck分析 - 针对大型项目增加超时时间
            from ..utils.windows_compat import run_command_safe
            result = run_command_safe(cmd, timeout=3600)  # 1小时超时
            
            if result.returncode != 0:
                logger.warning(f"Cppcheck执行完成但有警告: {result.stderr}")
            
            # 解析XML输出
            findings = self._parse_cppcheck_output(result.stdout)
            
            # 转换为统一格式
            symbols = self._convert_to_symbols(findings, project_path)
            
            logger.info(f"Cppcheck分析完成，发现 {len(symbols)} 个问题")
            
            return {
                "status": "success",
                "total_findings": len(symbols),
                "symbols": symbols,
                "raw_findings": findings,
                "metadata": {
                    "analyzer": "cppcheck",
                    "project_path": str(project_path),
                    "files_analyzed": len(cpp_files)
                }
            }
            
        except Exception as e:
            logger.error(f"Cppcheck分析异常: {e}")
            return self._create_error_result("Cppcheck analysis failed", str(e))

    def analyze_file(self, file_path: Path, project_path: Path) -> List[Dict[str, Any]]:
        """
        分析单个文件
        
        Args:
            file_path: 文件路径
            project_path: 项目根目录
            
        Returns:
            发现的问题列表
        """
        if file_path.suffix.lower() not in self.supported_extensions:
            logger.debug(f"文件 {file_path} 不是C/C++文件，跳过Cppcheck分析")
            return []
        
        try:
            # 构建单文件分析命令
            cmd = self._build_cppcheck_command(file_path, single_file=True)
            
            from ..utils.windows_compat import run_command_safe
            result = run_command_safe(cmd, timeout=60)
            
            if result.returncode not in (0, 1):  # Cppcheck返回1表示有问题发现
                logger.warning(f"Cppcheck分析文件失败 {file_path}: {result.stderr}")
                return []
            
            findings = self._parse_cppcheck_output(result.stdout)
            return self._convert_to_symbols(findings, project_path)
            
        except Exception as e:
            logger.warning(f"分析文件 {file_path} 异常: {e}")
            return []

    def get_supported_checks(self) -> List[Dict[str, str]]:
        """获取支持的检查类型"""
        return [
            {
                "id": "error",
                "name": "错误检查",
                "description": "严重的编程错误，如内存泄漏、缓冲区溢出等"
            },
            {
                "id": "warning", 
                "name": "警告检查",
                "description": "潜在的问题，如未使用的变量、类型转换等"
            },
            {
                "id": "style",
                "name": "代码风格",
                "description": "代码风格和最佳实践建议"
            },
            {
                "id": "performance",
                "name": "性能检查",
                "description": "性能相关的优化建议"
            },
            {
                "id": "portability",
                "name": "可移植性",
                "description": "跨平台兼容性问题"
            },
            {
                "id": "information",
                "name": "信息提示",
                "description": "一般性的信息和建议"
            }
        ]

    def create_config_file(self, config: Dict[str, Any], output_path: Path) -> bool:
        """
        创建Cppcheck配置文件
        
        Args:
            config: 配置内容
            output_path: 输出路径
            
        Returns:
            是否成功
        """
        try:
            # 创建XML配置文件
            root = ET.Element("project")
            
            # 添加检查设置
            if "enable" in config:
                enable_elem = ET.SubElement(root, "enable")
                enable_elem.text = ",".join(config["enable"])
            
            # 添加忽略模式
            if "suppressions" in config:
                for suppression in config["suppressions"]:
                    supp_elem = ET.SubElement(root, "suppression")
                    supp_elem.text = suppression
            
            # 添加包含路径
            if "includes" in config:
                for include in config["includes"]:
                    inc_elem = ET.SubElement(root, "includedir")
                    inc_elem.text = include
            
            # 写入文件
            tree = ET.ElementTree(root)
            tree.write(output_path, encoding="utf-8", xml_declaration=True)
            
            logger.info(f"Cppcheck配置文件已保存到: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"创建Cppcheck配置文件失败: {e}")
            return False

    # ----------------------
    # 私有方法
    # ----------------------

    def _verify_cppcheck_installation(self) -> None:
        """验证Cppcheck是否已安装"""
        try:
            from ..utils.windows_compat import run_command_safe
            result = run_command_safe(["cppcheck", "--version"], timeout=10)
            
            if result.returncode == 0:
                version = result.stdout.strip()
                logger.info(f"Cppcheck已安装，版本: {version}")
            else:
                raise RuntimeError("Cppcheck未正确安装或配置")
                
        except Exception as e:
            raise RuntimeError(f"Cppcheck验证失败: {e}. 请确保已安装Cppcheck")

    def _find_cpp_files(self, project_path: Path) -> List[Path]:
        """查找项目中的C/C++文件"""
        cpp_files = []
        
        for ext in self.supported_extensions:
            cpp_files.extend(project_path.rglob(f"*{ext}"))
        
        # 过滤掉一些常见的不需要分析的目录
        excluded_dirs = {"build", "target", "dist", "node_modules", ".git", "__pycache__"}
        
        filtered_files = []
        for file_path in cpp_files:
            if not any(excluded_dir in file_path.parts for excluded_dir in excluded_dirs):
                filtered_files.append(file_path)
        
        return filtered_files

    def _build_cppcheck_command(self, target_path: Path, single_file: bool = False) -> List[str]:
        """构建Cppcheck命令行（基于官方最佳实践）"""
        cmd = ["cppcheck"]
        
        # 基础输出配置（官方推荐）
        cmd.extend([
            "--xml",                    # XML输出格式
            "--xml-version=2",          # XML版本2（支持更多字段）
            "--quiet",                  # 减少冗余输出
        ])
        
        # 检查级别配置（基于官方文档）
        cmd.extend([
            "--enable=all",             # 启用所有检查类型
            "--inconclusive",           # 包含不确定的分析结果
            "--inline-suppr",           # 支持内联抑制注释
        ])
        
        # 错误处理配置
        cmd.extend([
            "--error-exitcode=1",       # 发现错误时退出码为1
            "--force",                  # 强制检查所有文件
        ])
        
        # 性能和资源配置（官方推荐）
        import os
        cpu_count = os.cpu_count() or 4  # 获取CPU核心数，默认4
        cmd.extend([
            "--max-configs=12",         # 限制配置数量（官方默认）
            "--platform=native",        # 使用本地平台配置
            "-j", str(min(cpu_count, 8)),  # 并行处理，最多8个线程
        ])
        
        # C/C++标准配置（官方支持的标准）
        cmd.extend([
            "--std=c11",               # C11标准
            "--std=c++17",             # C++17标准
        ])
        
        # 检测Cppcheck版本并决定是否使用库配置
        try:
            from ..utils.windows_compat import run_command_safe
            version_result = run_command_safe(["cppcheck", "--version"], timeout=10)
            version_text = version_result.stdout

            # 提取版本号
            import re
            version_match = re.search(r'Cppcheck (\d+)\.(\d+)', version_text)
            if version_match:
                major, minor = int(version_match.group(1)), int(version_match.group(2))
                supports_library = (major > 1) or (major == 1 and minor >= 80)  # 1.80+支持--library
            else:
                supports_library = False

            if supports_library:
                # 库配置（官方内置库）
                standard_libraries = ["std", "posix"]
                if single_file:
                    # 单文件分析时使用基础库
                    for lib in standard_libraries:
                        cmd.extend(["--library", lib])
                else:
                    # 项目分析时使用完整库配置
                    extended_libraries = standard_libraries + ["windows", "gtk", "qt", "boost"]
                    for lib in extended_libraries:
                        cmd.extend(["--library", lib])

                # 添加自定义配置文件
                if self.config_file and self.config_file.exists():
                    cmd.extend(["--library", str(self.config_file)])

                logger.debug(f"使用Cppcheck库配置 (版本 {major}.{minor})")
            else:
                logger.debug(f"Cppcheck版本不支持--library参数，跳过库配置")

        except Exception as e:
            logger.debug(f"无法检测Cppcheck版本，跳过库配置: {e}")
        
        # 抑制规则配置（基于官方推荐）
        suppressions = [
            "missingIncludeSystem",     # 抑制系统头文件缺失警告
            "unmatchedSuppression",     # 抑制未匹配的抑制规则
            "missingInclude",           # 抑制一般头文件缺失
        ]
        
        if not single_file:
            # 项目级分析额外抑制
            suppressions.extend([
                "unusedFunction",       # 项目中未使用函数很常见
                "toomanyconfigs",       # 抑制配置过多警告
            ])
        
        for suppression in suppressions:
            cmd.extend(["--suppress", suppression])
        
        # 针对不同文件类型的优化
        if single_file:
            cmd.extend([
                "--max-ctu-depth=1",   # 限制跨翻译单元分析深度
            ])
        else:
            # 项目级分析配置
            cmd.extend([
                "--max-ctu-depth=3",   # 更深的跨翻译单元分析
                "--check-config",      # 详细配置检查
                "--report-progress",   # 显示分析进度
            ])
            
            # 针对大型项目的优化
            try:
                if target_path.is_dir():
                    c_files = list(target_path.rglob("*.c"))
                    cpp_files = list(target_path.rglob("*.cpp"))
                    file_count = len(c_files) + len(cpp_files)
                    
                    if file_count > 100:
                        # 大型项目优化 (针对10万行项目)
                        cmd.extend([
                            "--max-configs=16",  # 增加配置数量以充分利用16GB内存
                            "--template='{file}:{line}: [{severity}] {message} [{id}]'",  # 简化输出
                            "-j", "12",  # 增加并行作业数
                        ])
                    elif file_count > 20:
                        # 中型项目配置
                        cmd.extend([
                            "--verbose",        # 详细输出
                        ])
            except Exception:
                pass  # 忽略文件统计错误
        
        # 添加目标路径
        cmd.append(str(target_path))
        
        return cmd

    def _parse_cppcheck_output(self, xml_output: str) -> List[Dict[str, Any]]:
        """解析Cppcheck XML输出"""
        findings = []

        try:
            if not xml_output.strip():
                logger.debug("Cppcheck输出为空")
                return findings

            # 检查是否是有效的XML
            if not xml_output.strip().startswith('<?xml') and not xml_output.strip().startswith('<'):
                logger.warning(f"Cppcheck输出不是有效的XML格式: {xml_output[:100]}...")
                return findings

            # 尝试解析XML
            try:
                root = ET.fromstring(xml_output)
            except ET.ParseError as e:
                # 如果XML解析失败，尝试添加根元素
                logger.debug(f"直接解析失败，尝试包装: {e}")
                wrapped_xml = f"<results>{xml_output}</results>"
                try:
                    root = ET.fromstring(wrapped_xml)
                except ET.ParseError:
                    logger.warning("XML包装后仍然解析失败，跳过Cppcheck结果")
                    return findings

            # 查找所有错误
            for error in root.findall(".//error"):
                finding = {
                    "id": error.get("id", "unknown"),
                    "severity": error.get("severity", "unknown"),
                    "message": error.get("msg", ""),
                    "verbose": error.get("verbose", ""),
                    "cwe": error.get("cwe", ""),
                    "locations": []
                }

                # 查找位置信息
                for location in error.findall("location"):
                    try:
                        loc_info = {
                            "file": location.get("file", ""),
                            "line": int(location.get("line", 0)),
                            "column": int(location.get("column", 0)),
                            "info": location.get("info", "")
                        }
                        finding["locations"].append(loc_info)
                    except ValueError as e:
                        logger.debug(f"解析位置信息失败: {e}")
                        continue

                findings.append(finding)

        except Exception as e:
            logger.warning(f"处理Cppcheck输出异常: {e}")
            logger.debug(f"输出内容: {xml_output[:200]}...")

        return findings

    def _convert_to_symbols(self, findings: List[Dict[str, Any]], project_path: Path) -> List[Dict[str, Any]]:
        """将Cppcheck发现转换为统一符号格式"""
        symbols = []
        
        for finding in findings:
            try:
                # 获取主要位置（通常是第一个位置）
                if not finding.get("locations"):
                    continue
                
                main_location = finding["locations"][0]
                file_path = Path(main_location["file"])
                
                # 使用Windows兼容的路径处理
                from ..utils.windows_compat import normalize_path
                try:
                    rel_path = normalize_path(file_path.relative_to(project_path))
                except ValueError:
                    # 如果文件不在项目路径内，使用绝对路径的文件名
                    rel_path = file_path.name
                
                # 映射严重程度
                severity_map = {
                    "error": "high",
                    "warning": "medium", 
                    "style": "low",
                    "performance": "medium",
                    "portability": "low",
                    "information": "info"
                }
                
                symbol = {
                    "id": self._generate_finding_id(finding, main_location),
                    "name": finding["id"],
                    "type": "static_analysis_finding",
                    "file_path": rel_path,
                    "line_number": main_location["line"],
                    "column": main_location.get("column", 0),
                    "severity": severity_map.get(finding["severity"], "medium"),
                    "category": finding["severity"],
                    "message": finding["message"],
                    "description": finding.get("verbose", finding["message"]),
                    "rule_id": finding["id"],
                    "cwe": finding.get("cwe", ""),
                    "source": "cppcheck",
                    "tool": "Cppcheck",
                    "locations": finding["locations"],
                    "check_type": finding["severity"]
                }
                
                symbols.append(symbol)
                
            except Exception as e:
                logger.debug(f"转换Cppcheck发现失败: {e}")
        
        return symbols

    def _generate_finding_id(self, finding: Dict[str, Any], location: Dict[str, Any]) -> str:
        """生成发现的唯一ID"""
        import hashlib
        
        content = f"cppcheck:{finding['id']}:{location['file']}:{location['line']}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _create_empty_result(self) -> Dict[str, Any]:
        """创建空结果"""
        return {
            "status": "success",
            "total_findings": 0,
            "symbols": [],
            "raw_findings": [],
            "metadata": {
                "analyzer": "cppcheck",
                "note": "No C/C++ files found"
            }
        }

    def _create_error_result(self, message: str, details: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            "status": "error",
            "message": message,
            "details": details,
            "total_findings": 0,
            "symbols": [],
            "metadata": {
                "analyzer": "cppcheck",
                "error": True
            }
        } 