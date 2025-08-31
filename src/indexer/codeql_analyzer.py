"""
CodeQL 代码分析器

集成 GitHub CodeQL 进行高级静态代码分析，包括：
- 安全漏洞检测
- 代码质量问题
- 数据流分析
- 控制流分析

⚠ 依赖：需要安装 CodeQL CLI 工具
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger


class CodeQLAnalyzer:
    """CodeQL 代码分析器"""

    def __init__(self):
        self.codeql_path = self._find_codeql()
        self.database_path: Optional[Path] = None
        self.temp_dir: Optional[Path] = None

    def analyze_project(self, project_path: Path) -> Dict[str, Any]:
        """
        分析整个项目
        
        Args:
            project_path: 项目根路径
        
        Returns:
            分析结果
        """
        if not self.codeql_path:
            logger.error("CodeQL CLI 未找到，请安装 CodeQL 工具")
            return {"status": "error", "message": "CodeQL CLI not found"}
        
        project_path = project_path.resolve()
        if not project_path.exists():
            raise ValueError(f"项目路径不存在: {project_path}")
        
        logger.info(f"开始 CodeQL 分析: {project_path}")
        
        try:
            # 创建临时目录
            self.temp_dir = Path(tempfile.mkdtemp(prefix="codeql_"))
            self.database_path = self.temp_dir / "database"
            
            # 创建 CodeQL 数据库
            if not self._create_database(project_path):
                return {"status": "error", "message": "Failed to create CodeQL database"}
            
            # 运行查询
            analysis_results = self._run_queries()
            
            # 生成符号信息
            symbols = self._extract_symbols()
            
            return {
                "status": "success",
                "project_path": str(project_path),
                "analysis_results": analysis_results,
                "symbols_count": len(symbols),
                "symbols": symbols
            }
            
        except Exception as e:
            logger.error(f"CodeQL 分析失败: {e}")
            return {"status": "error", "message": str(e)}
        
        finally:
            # 清理临时文件
            self._cleanup()

    def get_vulnerabilities(self, project_path: Path) -> List[Dict[str, Any]]:
        """获取安全漏洞"""
        result = self.analyze_project(project_path)
        if result["status"] == "success":
            return result["analysis_results"].get("vulnerabilities", [])
        return []

    def get_code_quality_issues(self, project_path: Path) -> List[Dict[str, Any]]:
        """获取代码质量问题"""
        result = self.analyze_project(project_path)
        if result["status"] == "success":
            return result["analysis_results"].get("code_quality", [])
        return []

    def extract_project_symbols(self, project_path: Path) -> List[Dict[str, Any]]:
        """提取项目符号（兼容接口）"""
        result = self.analyze_project(project_path)
        if result["status"] == "success":
            return result.get("symbols", [])
        return []

    # ----------------------
    # 私有方法
    # ----------------------

    def _find_codeql(self) -> Optional[str]:
        """查找 CodeQL CLI 工具"""
        try:
            result = subprocess.run(["codeql", "version"], 
                                  capture_output=True, text=True, check=True)
            logger.info(f"找到 CodeQL: {result.stdout.strip()}")
            return "codeql"
        except (subprocess.CalledProcessError, FileNotFoundError):
            # 尝试常见路径
            common_paths = [
                "codeql.exe",
                r"C:\codeql\codeql.exe",
                "/usr/local/bin/codeql",
                "/opt/codeql/codeql"
            ]
            
            for path in common_paths:
                try:
                    result = subprocess.run([path, "version"], 
                                          capture_output=True, text=True, check=True)
                    logger.info(f"找到 CodeQL: {path}")
                    return path
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue
            
            logger.warning("未找到 CodeQL CLI 工具")
            return None

    def _create_database(self, project_path: Path) -> bool:
        """创建 CodeQL 数据库"""
        try:
            cmd = [
                self.codeql_path,
                "database", "create",
                str(self.database_path),
                "--language=cpp",
                f"--source-root={project_path}",
                "--overwrite"
            ]
            
            # 对于 C 项目，如果有 Makefile 或 CMakeLists.txt，使用构建命令
            if (project_path / "Makefile").exists():
                cmd.extend(["--command=make"])
            elif (project_path / "CMakeLists.txt").exists():
                cmd.extend(["--command=cmake . && make"])
            else:
                # 对于没有构建系统的项目，使用无构建模式
                cmd.append("--no-run-unnecessary-builds")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("CodeQL 数据库创建成功")
                return True
            else:
                logger.error(f"创建 CodeQL 数据库失败: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"创建 CodeQL 数据库时出错: {e}")
            return False

    def _run_queries(self) -> Dict[str, List[Dict[str, Any]]]:
        """运行 CodeQL 查询"""
        results = {
            "vulnerabilities": [],
            "code_quality": [],
            "data_flow": [],
            "control_flow": []
        }
        
        # 定义查询套件
        query_suites = {
            "security": "cpp-security-extended.qls",
            "code_quality": "cpp-code-scanning.qls"
        }
        
        for category, suite in query_suites.items():
            try:
                # 运行查询套件
                results_file = self.temp_dir / f"{category}_results.json"
                
                cmd = [
                    self.codeql_path,
                    "database", "analyze",
                    str(self.database_path),
                    suite,
                    "--format=json",
                    f"--output={results_file}"
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0 and results_file.exists():
                    # 解析结果
                    with open(results_file, 'r', encoding='utf-8') as f:
                        query_results = json.load(f)
                    
                    # 转换为内部格式
                    if category == "security":
                        results["vulnerabilities"] = self._convert_security_results(query_results)
                    elif category == "code_quality":
                        results["code_quality"] = self._convert_quality_results(query_results)
                        
                    logger.info(f"CodeQL {category} 查询完成，发现 {len(query_results.get('runs', [{}])[0].get('results', []))} 个问题")
                else:
                    logger.warning(f"CodeQL {category} 查询失败: {result.stderr}")
                    
            except Exception as e:
                logger.error(f"运行 CodeQL {category} 查询时出错: {e}")
        
        return results

    def _extract_symbols(self) -> List[Dict[str, Any]]:
        """从 CodeQL 数据库提取符号"""
        symbols = []
        
        try:
            # 使用自定义查询提取符号信息
            query_file = self.temp_dir / "extract_symbols.ql"
            results_file = self.temp_dir / "symbols.json"
            
            # 写入符号提取查询
            symbol_query = """
import cpp

from Element e, Location loc, string name
where
  (
    e instanceof Function or
    e instanceof Class or
    e instanceof Variable or
    e instanceof Macro or
    e instanceof Enum or
    e instanceof TypedefType
  ) and
  loc = e.getLocation() and
  name = e.toString()
select e, name, e.getPrimaryQlClass(), loc.getFile().getRelativePath(), 
       loc.getStartLine(), loc.getStartColumn(), loc.getEndLine(), loc.getEndColumn()
"""
            
            with open(query_file, 'w', encoding='utf-8') as f:
                f.write(symbol_query)
            
            # 运行查询
            cmd = [
                self.codeql_path,
                "query", "run",
                str(query_file),
                "--database", str(self.database_path),
                "--output", str(results_file),
                "--format", "json"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and results_file.exists():
                with open(results_file, 'r', encoding='utf-8') as f:
                    query_results = json.load(f)
                
                symbols = self._convert_symbol_results(query_results)
                logger.info(f"从 CodeQL 提取了 {len(symbols)} 个符号")
            else:
                logger.warning(f"符号提取查询失败: {result.stderr}")
                
        except Exception as e:
            logger.error(f"提取符号时出错: {e}")
        
        return symbols

    def _convert_security_results(self, query_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """转换安全查询结果"""
        vulnerabilities = []
        
        runs = query_results.get("runs", [])
        for run in runs:
            results = run.get("results", [])
            for result in results:
                vuln = {
                    "id": self._generate_id("vulnerability", result.get("ruleId", "unknown")),
                    "rule_id": result.get("ruleId", ""),
                    "message": result.get("message", {}).get("text", ""),
                    "severity": self._map_severity(result.get("level", "note")),
                    "locations": [],
                    "description": f"安全漏洞: {result.get('ruleId', 'Unknown')}"
                }
                
                # 提取位置信息
                for location in result.get("locations", []):
                    phys_loc = location.get("physicalLocation", {})
                    artifact_loc = phys_loc.get("artifactLocation", {})
                    region = phys_loc.get("region", {})
                    
                    vuln["locations"].append({
                        "file_path": artifact_loc.get("uri", ""),
                        "start_line": region.get("startLine", 0),
                        "start_column": region.get("startColumn", 0),
                        "end_line": region.get("endLine", 0),
                        "end_column": region.get("endColumn", 0)
                    })
                
                vulnerabilities.append(vuln)
        
        return vulnerabilities

    def _convert_quality_results(self, query_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """转换代码质量查询结果"""
        issues = []
        
        runs = query_results.get("runs", [])
        for run in runs:
            results = run.get("results", [])
            for result in results:
                issue = {
                    "id": self._generate_id("quality", result.get("ruleId", "unknown")),
                    "rule_id": result.get("ruleId", ""),
                    "message": result.get("message", {}).get("text", ""),
                    "severity": self._map_severity(result.get("level", "note")),
                    "category": "code_quality",
                    "locations": [],
                    "description": f"代码质量问题: {result.get('ruleId', 'Unknown')}"
                }
                
                # 提取位置信息
                for location in result.get("locations", []):
                    phys_loc = location.get("physicalLocation", {})
                    artifact_loc = phys_loc.get("artifactLocation", {})
                    region = phys_loc.get("region", {})
                    
                    issue["locations"].append({
                        "file_path": artifact_loc.get("uri", ""),
                        "start_line": region.get("startLine", 0),
                        "start_column": region.get("startColumn", 0),
                        "end_line": region.get("endLine", 0),
                        "end_column": region.get("endColumn", 0)
                    })
                
                issues.append(issue)
        
        return issues

    def _convert_symbol_results(self, query_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """转换符号查询结果"""
        symbols = []
        
        # CodeQL 查询结果格式较复杂，这里简化处理
        tuples = query_results.get("#select", {}).get("tuples", [])
        
        for tuple_data in tuples:
            if len(tuple_data) >= 6:
                symbol = {
                    "id": self._generate_id("codeql_symbol", tuple_data[1]),
                    "name": tuple_data[1],
                    "type": self._map_codeql_type(tuple_data[2]),
                    "file_path": tuple_data[3],
                    "line_number": tuple_data[4],
                    "declaration": f"{tuple_data[2]} {tuple_data[1]}",
                    "description": f"{tuple_data[2]} {tuple_data[1]} (from CodeQL)"
                }
                symbols.append(symbol)
        
        return symbols

    def _map_severity(self, level: str) -> str:
        """映射严重程度"""
        mapping = {
            "error": "high",
            "warning": "medium",
            "note": "low",
            "info": "low"
        }
        return mapping.get(level, "low")

    def _map_codeql_type(self, codeql_type: str) -> str:
        """映射 CodeQL 类型到内部类型"""
        if "Function" in codeql_type:
            return "function"
        elif "Class" in codeql_type or "Struct" in codeql_type:
            return "structure"
        elif "Variable" in codeql_type:
            return "variable"
        elif "Macro" in codeql_type:
            return "macro"
        elif "Enum" in codeql_type:
            return "enum"
        elif "Typedef" in codeql_type:
            return "typedef"
        else:
            return "unknown"

    def _generate_id(self, prefix: str, name: str) -> str:
        """生成唯一 ID"""
        import hashlib, uuid
        unique_suffix = str(uuid.uuid4())[:8]
        content = f"codeql:{prefix}:{name}:{unique_suffix}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _cleanup(self):
        """清理临时文件"""
        if self.temp_dir and self.temp_dir.exists():
            import shutil
            try:
                shutil.rmtree(self.temp_dir)
                logger.debug("清理 CodeQL 临时文件")
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")
        
        self.temp_dir = None
        self.database_path = None 