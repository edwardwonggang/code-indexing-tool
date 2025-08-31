"""
统一代码分析器

整合多个成熟的开源静态分析工具，提供统一的分析接口（Windows专用）：
- Cppcheck: C/C++静态分析
- LSP: Language Server Protocol客户端
- CodeQL: GitHub的高级静态分析  
- Universal CTags: 经典符号提取
- Tree-sitter: 语法分析
- Lizard: 代码复杂度分析

避免自定义分析规则，依赖成熟的开源工具生态
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Set
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

# 导入各种分析器
from .cppcheck_analyzer import CppcheckAnalyzer
from .lsp_analyzer import LSPAnalyzer
from .codeql_analyzer import CodeQLAnalyzer
from .ctags_extractor import CTagsExtractor
from .cscope_analyzer import CscopeAnalyzer
from .ts_symbol_extractor import TSSymbolExtractor


@dataclass
class AnalysisConfig:
    """分析配置"""
    enable_cppcheck: bool = True  # C/C++静态分析工具
    enable_lsp: bool = True       # 语言服务器协议
    enable_codeql: bool = True    # GitHub高级代码分析
    enable_ctags: bool = True
    enable_cscope: bool = True   # 经典C代码分析工具
    enable_treesitter: bool = True
    
    # 语言过滤
    target_languages: Optional[List[str]] = None
    
    # 并行配置
    max_workers: int = 4
    timeout_seconds: int = 600
    

    
    # 输出过滤
    min_confidence: str = "medium"  # low, medium, high
    include_info_findings: bool = False


@dataclass
class AnalysisResult:
    """统一的分析结果"""
    status: str
    total_symbols: int
    total_findings: int
    symbols: List[Dict[str, Any]]
    findings: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    analyzer_results: Dict[str, Dict[str, Any]]
    errors: List[str]


class UnifiedAnalyzer:
    """统一代码分析器 - 集成多个成熟开源工具"""

    def __init__(self, config: Optional[AnalysisConfig] = None):
        """
        初始化统一分析器
        
        Args:
            config: 分析配置
        """
        self.config = config or AnalysisConfig()
        self.analyzers: Dict[str, Any] = {}
        self.errors: List[str] = []
        
        # 初始化各个分析器
        self._initialize_analyzers()

    def analyze_project(self, project_path: Path) -> AnalysisResult:
        """
        分析整个项目 - 使用多个成熟工具并行分析
        
        Args:
            project_path: 项目根目录
            
        Returns:
            统一的分析结果
        """
        project_path = project_path.resolve()
        if not project_path.exists():
            raise ValueError(f"项目路径不存在: {project_path}")
        
        logger.info(f"开始统一分析项目: {project_path}")
        logger.info(f"启用的分析器: {list(self.analyzers.keys())}")
        
        # 并行执行各个分析器
        analyzer_results = self._run_analyzers_parallel(project_path)
        
        # 合并和去重结果
        unified_result = self._merge_analysis_results(analyzer_results, project_path)
        
        logger.info(f"统一分析完成 - 符号: {unified_result.total_symbols}, 发现: {unified_result.total_findings}")
        
        return unified_result

    def analyze_file(self, file_path: Path, project_path: Path) -> AnalysisResult:
        """
        分析单个文件
        
        Args:
            file_path: 文件路径
            project_path: 项目根目录
            
        Returns:
            分析结果
        """
        logger.info(f"分析单个文件: {file_path}")
        
        # 检测文件语言
        language = self._detect_file_language(file_path)
        if not language:
            logger.warning(f"无法检测文件语言: {file_path}")
            return self._create_empty_result()
        
        # 只运行支持该语言的分析器
        applicable_analyzers = self._get_applicable_analyzers(language)
        
        analyzer_results = {}
        for name, analyzer in applicable_analyzers.items():
            try:
                if name == "cppcheck":
                    result = analyzer.analyze_file(file_path, project_path)
                elif name == "lsp":
                    result = asyncio.run(analyzer.analyze_file(file_path, project_path))
                elif name == "ctags":
                    # CTags只能分析整个项目，跳过单文件分析
                    continue
                elif name == "treesitter":
                    # Tree-sitter需要特殊处理
                    result = self._analyze_file_with_treesitter(analyzer, file_path, project_path)
                else:
                    continue
                
                analyzer_results[name] = result
                
            except Exception as e:
                logger.error(f"分析器 {name} 处理文件 {file_path} 失败: {e}")
                self.errors.append(f"{name}: {str(e)}")
        
        return self._merge_analysis_results(analyzer_results, project_path)

    def get_available_analyzers(self) -> Dict[str, Dict[str, Any]]:
        """获取可用分析器的信息"""
        analyzers_info = {}
        
        for name, analyzer in self.analyzers.items():
            try:
                if name == "cppcheck":
                    info = {
                        "name": "Cppcheck",
                        "type": "Static Analysis",
                        "languages": ["c", "cpp"],
                        "capabilities": ["memory_leaks", "bounds_checking", "null_pointer", "undefined_behavior"],
                        "version": "C/C++静态分析工具"
                    }
                elif name == "lsp":
                    info = {
                        "name": "Language Server Protocol",
                        "type": "LSP",
                        "languages": ["c", "cpp", "go", "rust", "python", "typescript", "javascript"],
                        "capabilities": ["symbols", "diagnostics", "references"],
                        "servers": analyzer.get_available_servers()
                    }
                elif name == "codeql":
                    info = {
                        "name": "CodeQL",
                        "type": "Advanced SAST",
                        "languages": ["c", "cpp", "java", "python", "javascript", "typescript", "csharp", "go"],
                        "capabilities": ["dataflow", "control_flow", "security_vulnerabilities"]
                    }
                elif name == "ctags":
                    info = {
                        "name": "Universal CTags",
                        "type": "Symbol Extraction",
                        "languages": ["c", "cpp", "python", "javascript", "go", "java", "php"],
                        "capabilities": ["symbols", "tags", "references"]
                    }
                elif name == "cscope":
                    info = {
                        "name": "Cscope",
                        "type": "Code Navigation & Analysis",
                        "languages": ["c", "cpp"],
                        "capabilities": ["symbols", "call_graph", "references", "cross_references"]
                    }
                elif name == "treesitter":
                    info = {
                        "name": "Tree-sitter",
                        "type": "Syntax Analysis",
                        "languages": ["c", "cpp", "python", "javascript", "typescript", "go", "rust"],
                        "capabilities": ["syntax_tree", "symbols", "complexity"]
                    }
                else:
                    info = {"name": name, "type": "unknown"}
                
                analyzers_info[name] = info
                
            except Exception as e:
                logger.debug(f"获取分析器 {name} 信息失败: {e}")
        
        return analyzers_info

    def create_custom_analysis_rules(self, rules_config: List[Dict[str, Any]], output_dir: Path) -> bool:
        """
        创建自定义分析规则（Windows环境优化）
        
        如果启用了多个分析器，结果将自动融合
        """
        logger.info("Windows环境下暂不支持创建自定义分析规则")
        return True

    # ----------------------
    # 私有方法
    # ----------------------

    def _initialize_analyzers(self) -> None:
        """初始化各个分析器"""
        try:
            # 初始化Cppcheck
            if self.config.enable_cppcheck:
                try:
                    self.analyzers["cppcheck"] = CppcheckAnalyzer()
                    logger.info("Cppcheck分析器初始化成功")
                except Exception as e:
                    logger.warning(f"Cppcheck分析器初始化失败: {e}")
                    self.errors.append(f"Cppcheck: {str(e)}")
            
            # 初始化LSP
            if self.config.enable_lsp:
                try:
                    self.analyzers["lsp"] = LSPAnalyzer()
                    logger.info("LSP分析器初始化成功")
                except Exception as e:
                    logger.warning(f"LSP分析器初始化失败: {e}")
                    self.errors.append(f"LSP: {str(e)}")
            
            # 初始化CodeQL
            if self.config.enable_codeql:
                try:
                    self.analyzers["codeql"] = CodeQLAnalyzer()
                    logger.info("CodeQL分析器初始化成功")
                except Exception as e:
                    logger.warning(f"CodeQL分析器初始化失败: {e}")
                    self.errors.append(f"CodeQL: {str(e)}")
            
            # 初始化CTags
            if self.config.enable_ctags:
                try:
                    self.analyzers["ctags"] = CTagsExtractor()
                    logger.info("CTags分析器初始化成功")
                except Exception as e:
                    logger.warning(f"CTags分析器初始化失败: {e}")
                    self.errors.append(f"CTags: {str(e)}")
            
            # 初始化Cscope
            if self.config.enable_cscope:
                try:
                    self.analyzers["cscope"] = CscopeAnalyzer()
                    logger.info("Cscope分析器初始化成功")
                except Exception as e:
                    logger.warning(f"Cscope分析器初始化失败: {e}")
                    self.errors.append(f"Cscope: {str(e)}")
            
            # 初始化Tree-sitter
            if self.config.enable_treesitter:
                try:
                    self.analyzers["treesitter"] = TSSymbolExtractor()
                    logger.info("Tree-sitter分析器初始化成功")
                except Exception as e:
                    logger.warning(f"Tree-sitter分析器初始化失败: {e}")
                    self.errors.append(f"Tree-sitter: {str(e)}")
            
            if not self.analyzers:
                raise RuntimeError("没有成功初始化任何分析器")
                
        except Exception as e:
            logger.error(f"分析器初始化失败: {e}")
            raise

    def _run_analyzers_parallel(self, project_path: Path) -> Dict[str, Dict[str, Any]]:
        """并行运行多个分析器"""
        analyzer_results = {}
        
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            # 提交同步分析器任务
            future_to_analyzer = {}
            
            for name, analyzer in self.analyzers.items():
                if name == "lsp":
                    # LSP是异步的，需要特殊处理
                    continue
                elif name == "cppcheck":
                    future = executor.submit(analyzer.analyze_project, project_path)
                elif name == "codeql":
                    future = executor.submit(analyzer.analyze_project, project_path)
                elif name == "ctags":
                    future = executor.submit(analyzer.extract_project, project_path)
                elif name == "cscope":
                    future = executor.submit(analyzer.analyze_project, project_path)
                elif name == "treesitter":
                    future = executor.submit(analyzer.extract_project, project_path)
                else:
                    continue
                
                future_to_analyzer[future] = name
            
            # 收集结果
            for future in as_completed(future_to_analyzer, timeout=self.config.timeout_seconds):
                analyzer_name = future_to_analyzer[future]
                try:
                    result = future.result()
                    analyzer_results[analyzer_name] = result
                    logger.info(f"分析器 {analyzer_name} 完成")
                except Exception as e:
                    logger.error(f"分析器 {analyzer_name} 执行失败: {e}")
                    self.errors.append(f"{analyzer_name}: {str(e)}")
        
        # 单独处理LSP（异步）
        if "lsp" in self.analyzers:
            try:
                lsp_result = asyncio.run(
                    self.analyzers["lsp"].analyze_project(project_path, self.config.target_languages)
                )
                analyzer_results["lsp"] = lsp_result
                logger.info("LSP分析器完成")
            except Exception as e:
                logger.error(f"LSP分析器执行失败: {e}")
                self.errors.append(f"LSP: {str(e)}")
        
        return analyzer_results

    def _merge_analysis_results(self, analyzer_results: Dict[str, Dict[str, Any]], project_path: Path) -> AnalysisResult:
        """合并多个分析器的结果"""
        all_symbols = []
        all_findings = []
        symbol_ids = set()
        finding_ids = set()
        
        # 合并符号和发现
        for analyzer_name, result in analyzer_results.items():
            if isinstance(result, dict):
                # 处理符号
                symbols = result.get("symbols", [])
                if isinstance(symbols, list):
                    for symbol in symbols:
                        if isinstance(symbol, dict):
                            symbol_id = symbol.get("id")
                            if symbol_id and symbol_id not in symbol_ids:
                                symbol["source_analyzer"] = analyzer_name
                                all_symbols.append(symbol)
                                symbol_ids.add(symbol_id)
                
                # 处理发现（安全问题、诊断等）
                findings = result.get("findings", result.get("diagnostics", []))
                if isinstance(findings, list):
                    for finding in findings:
                        if isinstance(finding, dict):
                            finding_id = finding.get("id", f"{analyzer_name}_{len(all_findings)}")
                            if finding_id not in finding_ids:
                                finding["source_analyzer"] = analyzer_name
                                all_findings.append(finding)
                                finding_ids.add(finding_id)
        
        # 应用过滤器
        filtered_findings = self._filter_findings(all_findings)
        
        # 创建统一结果
        status = "success" if analyzer_results else "error"
        
        return AnalysisResult(
            status=status,
            total_symbols=len(all_symbols),
            total_findings=len(filtered_findings),
            symbols=all_symbols,
            findings=filtered_findings,
            metadata={
                "project_path": str(project_path),
                "analyzers_used": list(analyzer_results.keys()),
                "config": self.config.__dict__,
                "languages_detected": self._detect_project_languages(project_path)
            },
            analyzer_results=analyzer_results,
            errors=self.errors.copy()
        )

    def _filter_findings(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤发现结果"""
        filtered = []
        
        confidence_levels = {"low": 1, "medium": 2, "high": 3}
        min_confidence_level = confidence_levels.get(self.config.min_confidence, 2)
        
        for finding in findings:
            # 过滤置信度
            confidence = finding.get("confidence", "medium")
            if confidence_levels.get(confidence, 2) < min_confidence_level:
                continue
            
            # 过滤信息级别的发现
            severity = finding.get("severity", "").lower()
            if not self.config.include_info_findings and severity in ["info", "note"]:
                continue
            
            filtered.append(finding)
        
        return filtered

    def _detect_file_language(self, file_path: Path) -> Optional[str]:
        """检测文件编程语言"""
        suffix = file_path.suffix.lower()
        
        language_map = {
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp", ".cxx": "cpp", ".cc": "cpp",
            ".hpp": "cpp", ".hxx": "cpp",
            ".py": "python", ".pyi": "python",
            ".js": "javascript", ".jsx": "javascript",
            ".ts": "typescript", ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".php": "php",
            ".rb": "ruby",
            ".cs": "csharp"
        }
        
        return language_map.get(suffix)

    def _detect_project_languages(self, project_path: Path) -> List[str]:
        """检测项目中的编程语言"""
        languages = set()
        
        for file_path in project_path.rglob("*"):
            if file_path.is_file():
                lang = self._detect_file_language(file_path)
                if lang:
                    languages.add(lang)
        
        return sorted(list(languages))

    def _get_applicable_analyzers(self, language: str) -> Dict[str, Any]:
        """获取适用于特定语言的分析器"""
        applicable = {}
        
        # 语言支持映射
        language_support = {
            "cppcheck": ["c", "cpp"],
            "lsp": ["c", "cpp", "go", "rust", "python", "typescript", "javascript"],
            "codeql": ["c", "cpp", "java", "python", "javascript", "typescript", "csharp", "go"],
            "ctags": ["c", "cpp", "python", "javascript", "go", "java", "php"],
            "cscope": ["c", "cpp"],
            "treesitter": ["c", "cpp", "python", "javascript", "typescript", "go", "rust"]
        }
        
        for analyzer_name, analyzer in self.analyzers.items():
            supported_languages = language_support.get(analyzer_name, [])
            if language in supported_languages:
                applicable[analyzer_name] = analyzer
        
        return applicable

    def _analyze_file_with_treesitter(self, analyzer, file_path: Path, project_path: Path) -> Dict[str, Any]:
        """使用Tree-sitter分析单个文件"""
        try:
            # Tree-sitter目前只支持项目级分析，这里做简化处理
            symbols = analyzer.extract_project(file_path.parent)
            
            # 过滤出目标文件的符号
            from ..utils.windows_compat import normalize_path
            target_rel_path = normalize_path(file_path.relative_to(project_path))
            
            file_symbols = [
                symbol for symbol in symbols 
                if symbol.get("file_path") == target_rel_path
            ]
            
            return {
                "status": "success",
                "symbols": file_symbols,
                "metadata": {"analyzer": "treesitter", "file_path": str(file_path)}
            }
            
        except Exception as e:
            logger.debug(f"Tree-sitter分析文件失败: {e}")
            return {"status": "error", "symbols": [], "error": str(e)}

    def _create_empty_result(self) -> AnalysisResult:
        """创建空的分析结果"""
        return AnalysisResult(
            status="success",
            total_symbols=0,
            total_findings=0,
            symbols=[],
            findings=[],
            metadata={},
            analyzer_results={},
            errors=[]
        ) 