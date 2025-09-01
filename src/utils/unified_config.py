"""
统一配置系统

基于各个工具的官方最佳实践，提供协调一致的配置管理：
- Windows专用：Cppcheck、Clang、CTags等工具集成
- CTags: 字段配置和符号类型
- Cscope: 数据库构建和查询选项  
- Cppcheck: 检查级别和库配置
- Tree-sitter: 解析配置和性能选项

确保各工具配置互补而不冲突，最大化分析效果。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Union
from loguru import logger


@dataclass
class ProjectProfile:
    """项目配置文件（基于项目特征自动优化）"""
    project_type: str = "general"           # 项目类型: web, system, embedded, library
    primary_languages: List[str] = field(default_factory=lambda: ["c"])
    file_count_estimate: int = 100          # 预估文件数量
    complexity_level: str = "medium"        # 复杂度: simple, medium, high
    security_focus: bool = True             # 是否重点关注安全
    performance_focus: bool = False         # 是否重点关注性能


@dataclass
class PerformanceConfig:
    """性能配置（针对16GB内存和4小时分析时间优化）"""
    max_memory_mb: int = 14000              # 最大内存使用 (16GB的87.5%)
    timeout_seconds: int = 14400            # 分析超时时间 (4小时)
    parallel_jobs: str = "auto"             # 并行作业数
    max_file_size_mb: int = 100             # 单文件最大大小 (放宽限制)
    enable_caching: bool = True             # 启用缓存
    incremental_analysis: bool = True       # 增量分析
    batch_size: int = 20                    # 批处理大小 (针对大型项目优化)
    progress_report_interval: int = 50      # 进度报告间隔


@dataclass
class QualityConfig:
    """代码质量配置"""
    min_confidence_level: str = "medium"    # 最小置信度: low, medium, high
    include_style_checks: bool = True       # 包含代码风格检查
    include_performance_checks: bool = True # 包含性能检查
    include_security_checks: bool = True    # 包含安全检查
    strict_mode: bool = False               # 严格模式
    experimental_checks: bool = False       # 实验性检查


class UnifiedConfig:
    """统一配置管理器（协调各工具的最佳实践）"""
    
    def __init__(self, project_path: Path, profile: Optional[ProjectProfile] = None):
        """
        初始化统一配置
        
        Args:
            project_path: 项目根路径
            profile: 项目配置文件
        """
        self.project_path = project_path
        self.profile = profile or self._detect_project_profile()
        self.performance = PerformanceConfig()
        self.quality = QualityConfig()
        
        # 自动调优配置
        self._auto_tune_performance()
        self._auto_tune_quality()
        
        logger.info(f"统一配置初始化完成: {self.profile.project_type} 项目，{len(self.profile.primary_languages)} 种语言")
    
    def _detect_project_profile(self) -> ProjectProfile:
        """自动检测项目配置文件"""
        try:
            # 检测主要语言
            language_files = {
                "c": len(list(self.project_path.rglob("*.c"))),
                "cpp": len(list(self.project_path.rglob("*.cpp"))),
                "python": len(list(self.project_path.rglob("*.py"))),
                "javascript": len(list(self.project_path.rglob("*.js"))),
                "typescript": len(list(self.project_path.rglob("*.ts"))),
                "java": len(list(self.project_path.rglob("*.java"))),
                "go": len(list(self.project_path.rglob("*.go"))),
            }
            
            # 确定主要语言
            primary_languages = [lang for lang, count in language_files.items() if count > 5]
            if not primary_languages:
                primary_languages = ["c"]  # 默认
            
            # 估算项目规模
            total_files = sum(language_files.values())
            
            # 检测项目类型
            project_type = "general"
            if any((self.project_path / name).exists() for name in ["package.json", "webpack.config.js"]):
                project_type = "web"
            elif any((self.project_path / name).exists() for name in ["Makefile", "CMakeLists.txt"]):
                project_type = "system"
            elif any((self.project_path / name).exists() for name in ["setup.py", "pyproject.toml"]):
                project_type = "library"
            
            # 确定复杂度
            complexity_level = "simple" if total_files < 50 else "medium" if total_files < 500 else "high"
            
            return ProjectProfile(
                project_type=project_type,
                primary_languages=primary_languages,
                file_count_estimate=total_files,
                complexity_level=complexity_level,
                security_focus=True,  # 默认关注安全
                performance_focus=(complexity_level == "high")
            )
            
        except Exception as e:
            logger.warning(f"项目配置检测失败，使用默认配置: {e}")
            return ProjectProfile()
    
    def _auto_tune_performance(self):
        """基于项目特征自动调优性能配置"""
        if self.profile.complexity_level == "high":
            # 大型项目优化 (针对10万行+项目)
            self.performance.max_memory_mb = 14000
            self.performance.timeout_seconds = 14400  # 4小时
            self.performance.max_file_size_mb = 100
            self.performance.batch_size = 15  # 更小的批大小
        elif self.profile.complexity_level == "simple":
            # 小型项目优化
            self.performance.max_memory_mb = 6000
            self.performance.timeout_seconds = 3600  # 1小时
            self.performance.max_file_size_mb = 50
            self.performance.batch_size = 50
    
    def _auto_tune_quality(self):
        """基于项目特征自动调优质量配置"""
        if self.profile.security_focus:
            self.quality.include_security_checks = True
            self.quality.min_confidence_level = "medium"
        
        if self.profile.performance_focus:
            self.quality.include_performance_checks = True
            self.quality.min_confidence_level = "high"  # 更严格
    

    
    def get_ctags_config(self) -> Dict[str, Any]:
        """获取CTags优化配置"""
        # 基础字段配置（官方推荐）
        fields = "+n+k+S+l+m+A+f+t+z"  # 全字段集
        extras = "+q+f+r"               # 限定名+文件名+引用
        
        # 根据项目复杂度调整
        if self.profile.complexity_level == "simple":
            fields = "+n+k+S"  # 简化字段集
            extras = "+q"      # 基础扩展
        
        config = {
            "languages": ",".join(self.profile.primary_languages).upper(),
            "fields": fields,
            "extras": extras,
            "recursive": True,
            "output_format": "json",
        }
        
        # 性能优化
        if self.profile.file_count_estimate > 1000:
            config["exclude_patterns"] = [
                "*.min.js", "*.bundle.js", "node_modules", 
                ".git", "*.o", "*.so", "*.dll"
            ]
        
        return config
    
    def get_cscope_config(self) -> Dict[str, Any]:
        """获取Cscope优化配置"""
        config = {
            "batch_mode": True,           # 批处理模式
            "build_inverted_index": True, # 构建倒排索引
            "kernel_mode": True,          # 内核模式
            "recursive": True,            # 递归扫描
            "verbose": (self.profile.complexity_level != "simple"),
            "unconditional_rebuild": False,  # 增量构建
        }
        
        # 大型项目优化
        if self.profile.file_count_estimate > 1000:
            config.update({
                "ignore_case": True,      # 忽略大小写
                "truncate_symbols": True, # 截断符号提高性能
            })
        
        return config
    
    def get_cppcheck_config(self) -> Dict[str, Any]:
        """获取Cppcheck优化配置"""
        config = {
            "xml_version": 2,
            "enable_all": True,
            "inconclusive": True,
            "inline_suppr": True,
            "max_configs": 12,
            "platform": "native",
            "jobs": self.performance.parallel_jobs,
        }
        
        # 标准配置
        standards = ["c11"]
        if "cpp" in self.profile.primary_languages:
            standards.append("c++17")
        config["standards"] = standards
        
        # 库配置
        libraries = ["std", "posix"]
        if self.profile.project_type == "web":
            libraries.extend(["gtk", "qt"])
        elif self.profile.project_type == "system":
            libraries.extend(["windows", "posix"])
        config["libraries"] = libraries
        
        # 抑制规则
        suppressions = ["missingIncludeSystem", "unmatchedSuppression"]
        if self.profile.complexity_level == "high":
            suppressions.extend(["unusedFunction", "toomanyconfigs"])
        config["suppressions"] = suppressions
        
        # 性能调优
        if self.profile.file_count_estimate > 100:
            config["max_ctu_depth"] = 3
            config["report_progress"] = True
        else:
            config["max_ctu_depth"] = 1
        
        return config
    
    def get_treesitter_config(self) -> Dict[str, Any]:
        """获取Tree-sitter优化配置"""
        config = {
            "supported_extensions": [".c", ".h", ".cpp", ".cxx", ".cc", ".hpp", ".hxx"],
            "max_file_size_mb": self.performance.max_file_size_mb,
            "timeout_micros": 1000000,
            "max_start_depth": 1000,
        }
        
        # 排除模式（基于最佳实践）
        exclude_patterns = [
            "build", "debug", "release", ".git", ".svn",
            "node_modules", "vendor", "third_party", "external",
            "__pycache__", ".pytest_cache"
        ]
        
        if self.profile.project_type == "web":
            exclude_patterns.extend(["dist", "coverage", ".next", ".nuxt"])
        
        config["exclude_patterns"] = exclude_patterns
        
        return config
    
    def get_unified_analysis_config(self) -> Dict[str, Any]:
        """获取统一分析器配置"""
        return {
            "enable_ctags": True,
            "enable_cscope": True,  # 启用C代码分析
            "enable_cppcheck": True,  # 启用C/C++静态分析
            "enable_treesitter": True,
            "enable_lsp": True,  # 自动安装并启用
            "enable_codeql": True,  # 自动安装并启用
            
            "target_languages": self.profile.primary_languages,
            "max_workers": min(16, max(4, os.cpu_count())) if os.cpu_count() else 4,  # 增加并发数
            "timeout_seconds": self.performance.timeout_seconds,
            "batch_size": getattr(self.performance, 'batch_size', 20),
            "min_confidence": self.quality.min_confidence_level,
            "include_info_findings": (self.quality.min_confidence_level == "low"),
        }
    
    def save_config(self, config_path: Optional[Path] = None) -> Path:
        """保存配置到文件"""
        if config_path is None:
            config_path = self.project_path / ".analysis_config.json"
        
        import json
        config_data = {
            "project_profile": {
                "project_type": self.profile.project_type,
                "primary_languages": self.profile.primary_languages,
                "file_count_estimate": self.profile.file_count_estimate,
                "complexity_level": self.profile.complexity_level,
                "security_focus": self.profile.security_focus,
                "performance_focus": self.profile.performance_focus,
            },
            "performance": {
                "max_memory_mb": self.performance.max_memory_mb,
                "timeout_seconds": self.performance.timeout_seconds,
                "parallel_jobs": self.performance.parallel_jobs,
                "max_file_size_mb": self.performance.max_file_size_mb,
            },
            "quality": {
                "min_confidence_level": self.quality.min_confidence_level,
                "include_style_checks": self.quality.include_style_checks,
                "include_performance_checks": self.quality.include_performance_checks,
                "include_security_checks": self.quality.include_security_checks,
            },
            "tool_configs": {

                "ctags": self.get_ctags_config(),
                "cscope": self.get_cscope_config(),
                "cppcheck": self.get_cppcheck_config(),
                "treesitter": self.get_treesitter_config(),
                "unified": self.get_unified_analysis_config(),
            }
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"统一配置已保存到: {config_path}")
        return config_path
    
    @classmethod
    def load_config(cls, config_path: Path, project_path: Path) -> 'UnifiedConfig':
        """从文件加载配置"""
        import json
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        profile_data = config_data.get("project_profile", {})
        profile = ProjectProfile(
            project_type=profile_data.get("project_type", "general"),
            primary_languages=profile_data.get("primary_languages", ["c"]),
            file_count_estimate=profile_data.get("file_count_estimate", 100),
            complexity_level=profile_data.get("complexity_level", "medium"),
            security_focus=profile_data.get("security_focus", True),
            performance_focus=profile_data.get("performance_focus", False),
        )
        
        config = cls(project_path, profile)
        
        # 应用保存的性能和质量配置
        if "performance" in config_data:
            perf_data = config_data["performance"]
            config.performance.max_memory_mb = perf_data.get("max_memory_mb", 8000)
            config.performance.timeout_seconds = perf_data.get("timeout_seconds", 300)
            config.performance.parallel_jobs = perf_data.get("parallel_jobs", "auto")
            config.performance.max_file_size_mb = perf_data.get("max_file_size_mb", 10)
        
        if "quality" in config_data:
            qual_data = config_data["quality"]
            config.quality.min_confidence_level = qual_data.get("min_confidence_level", "medium")
            config.quality.include_style_checks = qual_data.get("include_style_checks", True)
            config.quality.include_performance_checks = qual_data.get("include_performance_checks", True)
            config.quality.include_security_checks = qual_data.get("include_security_checks", True)
        
        logger.info(f"统一配置已从文件加载: {config_path}")
        return config
    
 