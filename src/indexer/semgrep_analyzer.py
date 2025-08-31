"""
Semgrep集成分析器

使用Semgrep这个成熟的开源静态分析工具来替代自定义规则分析：
- 支持多种编程语言
- 内置丰富的安全规则集
- 高性能的模式匹配引擎
- 社区维护的规则库
- 支持自定义规则

官方网站: https://semgrep.dev/
GitHub: https://github.com/returntocorp/semgrep
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from loguru import logger


class SemgrepAnalyzer:
    """基于Semgrep的静态代码分析器"""

    def __init__(self, config_paths: Optional[List[str]] = None):
        """
        初始化Semgrep分析器
        
        Args:
            config_paths: 自定义规则配置路径列表
        """
        self.config_paths = config_paths or []
        
        # 基于官方最佳实践的分层规则集配置
        self.core_rulesets = [
            "p/security-audit",      # 核心安全审计（高价值规则）
            "p/owasp-top-10",        # OWASP Top 10安全风险
            "p/cwe-top-25",          # CWE最常见弱点枚举
        ]
        
        self.additional_rulesets = [
            "p/default",             # 通用代码质量规则
            "p/ci",                  # CI/CD优化规则（轻量级）
            "p/comment",             # 代码注释最佳实践
            "p/correctness",         # 代码正确性检查
        ]
        
        # 针对特定语言的优化规则集（官方推荐）
        self.language_specific_rulesets = {
            "c": ["p/c-audit", "p/security-audit"],
            "cpp": ["p/cpp-audit", "p/security-audit"],
            "python": ["p/python", "p/flask", "p/django", "p/sqlalchemy"],
            "javascript": ["p/javascript", "p/nodejs", "p/react", "p/express"],
            "typescript": ["p/typescript", "p/react", "p/nodejs"],
            "java": ["p/java", "p/spring", "p/struts"],
            "go": ["p/golang", "p/gosec"],
            "rust": ["p/rust"],
            "php": ["p/php", "p/laravel", "p/symfony"],
            "ruby": ["p/ruby", "p/rails"],
        }
        
        # 官方推荐的性能优化配置
        self.performance_options = {
            "max_memory": "8000",        # 最大内存使用(MB)
            "timeout": "60",             # 单文件超时(秒)
            "jobs": "auto",              # 并行作业数
            "max_target_bytes": "1000000",  # 单文件最大字节数
        }
        
        # 官方推荐的输出格式配置
        self.output_options = {
            "format": "json",            # JSON格式便于解析
            "no_git_ignore": True,       # 不自动忽略.gitignore文件
            "skip_unknown_extensions": False,  # 不跳过未知扩展名
            "strict": False,             # 允许一些警告继续执行
        }
        
        self._verify_semgrep_installation()

    def analyze_project(self, project_path: Path, languages: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        使用Semgrep分析整个项目
        
        Args:
            project_path: 项目根目录
            languages: 目标语言列表，None表示自动检测
            
        Returns:
            分析结果
        """
        project_path = project_path.resolve()
        if not project_path.exists():
            raise ValueError(f"项目路径不存在: {project_path}")
        
        logger.info(f"开始Semgrep分析: {project_path}")
        
        try:
            # 构建Semgrep命令
            cmd = self._build_semgrep_command(project_path, languages)
            
            # 使用Windows兼容的命令执行
            from ..utils.windows_compat import run_command_safe
            result = run_command_safe(cmd, timeout=600)
            
            if result.returncode != 0:
                logger.error(f"Semgrep执行失败: {result.stderr}")
                return self._create_error_result("Semgrep execution failed", result.stderr)
            
            # 解析JSON输出
            findings = self._parse_semgrep_output(result.stdout)
            
            # 转换为统一格式
            symbols = self._convert_to_symbols(findings, project_path)
            
            logger.info(f"Semgrep分析完成，发现 {len(symbols)} 个问题")
            
            return {
                "status": "success",
                "total_findings": len(symbols),
                "symbols": symbols,
                "raw_findings": findings,
                "metadata": {
                    "analyzer": "semgrep",
                    "rulesets": self.default_rulesets + self.config_paths,
                    "project_path": str(project_path)
                }
            }
            
        except Exception as e:
            logger.error(f"Semgrep分析异常: {e}")
            return self._create_error_result("Analysis exception", str(e))

    def analyze_file(self, file_path: Path, project_path: Path) -> List[Dict[str, Any]]:
        """
        分析单个文件
        
        Args:
            file_path: 文件路径
            project_path: 项目根目录
            
        Returns:
            发现的问题列表
        """
        try:
            cmd = self._build_semgrep_command(file_path)
            
            from ..utils.windows_compat import run_command_safe
            result = run_command_safe(cmd, timeout=120)
            
            if result.returncode != 0:
                logger.warning(f"Semgrep分析文件失败 {file_path}: {result.stderr}")
                return []
            
            findings = self._parse_semgrep_output(result.stdout)
            return self._convert_to_symbols(findings, project_path)
            
        except Exception as e:
            logger.warning(f"分析文件 {file_path} 异常: {e}")
            return []

    def get_available_rulesets(self) -> List[Dict[str, str]]:
        """获取可用的规则集列表"""
        try:
            cmd = ["semgrep", "--config", "help"]
            from ..utils.windows_compat import run_command_safe
            result = run_command_safe(cmd, timeout=30)
            
            # 解析规则集信息（简化版，实际可能需要更复杂的解析）
            rulesets = []
            for ruleset in self.default_rulesets:
                rulesets.append({
                    "id": ruleset,
                    "name": ruleset.replace("p/", ""),
                    "description": f"Semgrep官方规则集: {ruleset}"
                })
            
            return rulesets
            
        except Exception as e:
            logger.warning(f"获取规则集失败: {e}")
            return []

    def create_custom_rule(self, rule_config: Dict[str, Any], output_path: Path) -> bool:
        """
        创建自定义Semgrep规则
        
        Args:
            rule_config: 规则配置
            output_path: 输出路径
            
        Returns:
            是否成功
        """
        try:
            import yaml
            
            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump({"rules": [rule_config]}, f, default_flow_style=False)
            
            logger.info(f"自定义规则已保存到: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"创建自定义规则失败: {e}")
            return False

    # ----------------------
    # 私有方法
    # ----------------------

    def _verify_semgrep_installation(self) -> None:
        """验证Semgrep是否已安装"""
        try:
            from ..utils.windows_compat import run_command_safe
            result = run_command_safe(["semgrep", "--version"], timeout=10)
            
            if result.returncode == 0:
                version = result.stdout.strip()
                logger.info(f"Semgrep已安装，版本: {version}")
            else:
                raise RuntimeError("Semgrep未正确安装或配置")
                
        except Exception as e:
            raise RuntimeError(f"Semgrep验证失败: {e}. 请确保已安装Semgrep: pip install semgrep")

    def _build_semgrep_command(self, target_path: Path, languages: Optional[List[str]] = None) -> List[str]:
        """构建Semgrep命令行（基于官方最佳实践）"""
        cmd = ["semgrep"]
        
        # 基础输出配置（官方推荐格式）
        cmd.extend([
            "--json",                    # JSON输出格式
            "--quiet",                   # 减少不必要的输出
            "--no-git-ignore",           # 不自动使用.gitignore
            "--skip-unknown-extensions", # 跳过未知扩展名文件
        ])
        
        # 智能规则集选择策略
        config_sources = []
        
        if self.config_paths:
            # 使用自定义配置路径
            config_sources.extend(self.config_paths)
        else:
            # 基于语言的智能规则集选择
            if languages:
                # 有明确语言时，使用语言特定规则
                config_sources.extend(self.core_rulesets)  # 核心安全规则
                
                for lang in languages:
                    lang_lower = lang.lower()
                    if lang_lower in self.language_specific_rulesets:
                        config_sources.extend(self.language_specific_rulesets[lang_lower])
                
                # 添加通用质量规则
                config_sources.extend(["p/ci", "p/correctness"])
            else:
                # 无明确语言时，使用全面但轻量的规则集
                config_sources.extend(self.core_rulesets)
                config_sources.extend(self.additional_rulesets)
        
        # 去重并添加配置
        for config in sorted(set(config_sources)):  # 排序确保一致性
            cmd.extend(["--config", config])
        
        # 添加语言过滤（如果指定）
        if languages:
            for lang in languages:
                cmd.extend(["--lang", lang])
        
        # 官方推荐的性能优化参数
        cmd.extend([
            "--max-memory", self.performance_options["max_memory"],
            "--timeout", self.performance_options["timeout"], 
            "--jobs", self.performance_options["jobs"],
            "--max-target-bytes", self.performance_options["max_target_bytes"],
        ])
        
        # 高级选项（根据官方文档）
        cmd.extend([
            "--enable-version-check",     # 启用版本检查
            "--exclude", "*.min.js",      # 排除压缩文件
            "--exclude", "*.bundle.js",   # 排除打包文件
            "--exclude", "node_modules",  # 排除依赖目录
            "--exclude", "vendor",        # 排除第三方代码
            "--exclude", ".git",          # 排除git目录
        ])
        
        # 针对大型项目的优化
        if target_path.is_dir():
            try:
                # 检查是否为大型项目
                file_count = sum(1 for _ in target_path.rglob("*") if _.is_file())
                if file_count > 1000:
                    cmd.extend([
                        "--max-lines-per-finding", "5",  # 限制每个发现的行数
                        "--time",                         # 显示时间信息
                    ])
            except Exception:
                pass  # 忽略文件计数错误
        
        # 添加目标路径
        cmd.append(str(target_path))
        
        return cmd

    def _parse_semgrep_output(self, output: str) -> List[Dict[str, Any]]:
        """解析Semgrep JSON输出"""
        try:
            data = json.loads(output)
            return data.get("results", [])
        except json.JSONDecodeError as e:
            logger.error(f"解析Semgrep输出失败: {e}")
            return []

    def _convert_to_symbols(self, findings: List[Dict[str, Any]], project_path: Path) -> List[Dict[str, Any]]:
        """将Semgrep发现转换为统一的符号格式"""
        symbols = []
        
        for finding in findings:
            try:
                # 使用Windows兼容的路径处理
                from ..utils.windows_compat import normalize_path
                file_path = Path(finding["path"])
                rel_path = normalize_path(file_path.relative_to(project_path))
                
                symbol = {
                    "id": self._generate_finding_id(finding),
                    "name": finding["check_id"],
                    "type": "security_finding",
                    "file_path": rel_path,
                    "line_number": finding["start"]["line"],
                    "end_line": finding["end"]["line"],
                    "column": finding["start"]["col"],
                    "severity": finding["extra"]["severity"],
                    "message": finding["extra"]["message"],
                    "rule_id": finding["check_id"],
                    "confidence": finding["extra"]["metadata"].get("confidence", "medium"),
                    "category": finding["extra"]["metadata"].get("category", "security"),
                    "cwe": finding["extra"]["metadata"].get("cwe", []),
                    "owasp": finding["extra"]["metadata"].get("owasp", []),
                    "source": "semgrep",
                    "fix_suggestion": finding["extra"].get("fix", ""),
                    "code_snippet": finding["extra"]["lines"],
                    "description": f"Semgrep规则 {finding['check_id']} 发现安全问题"
                }
                
                symbols.append(symbol)
                
            except Exception as e:
                logger.debug(f"转换Semgrep发现失败: {e}")
        
        return symbols

    def _generate_finding_id(self, finding: Dict[str, Any]) -> str:
        """生成发现的唯一ID"""
        import hashlib
        
        content = f"semgrep:{finding['check_id']}:{finding['path']}:{finding['start']['line']}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _create_error_result(self, message: str, details: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            "status": "error",
            "message": message,
            "details": details,
            "total_findings": 0,
            "symbols": [],
            "metadata": {
                "analyzer": "semgrep",
                "error": True
            }
        } 