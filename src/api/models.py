"""
API数据模型

定义API请求和响应的数据结构
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class SymbolType(str, Enum):
    """符号类型枚举"""
    FUNCTION = "function"
    STRUCTURE = "structure" 
    VARIABLE = "variable"
    MACRO = "macro"


class SearchType(str, Enum):
    """搜索类型枚举"""
    SEMANTIC = "semantic"
    EXACT = "exact"
    FUZZY = "fuzzy"


class SearchRequest(BaseModel):
    """搜索请求模型"""
    query: str = Field(..., description="搜索查询", min_length=1, max_length=500)
    search_type: SearchType = Field(SearchType.SEMANTIC, description="搜索类型")
    symbol_type: Optional[SymbolType] = Field(None, description="符号类型过滤")
    file_path: Optional[str] = Field(None, description="文件路径过滤")
    project_path: Optional[str] = Field(None, description="项目路径过滤")
    limit: int = Field(20, description="返回结果数量", ge=1, le=100)
    threshold: float = Field(0.5, description="相似度阈值", ge=0.0, le=1.0)


class ParameterInfo(BaseModel):
    """参数信息模型"""
    name: str = Field("", description="参数名")
    type: str = Field("", description="参数类型")
    description: str = Field("", description="参数描述")
    is_pointer: bool = Field(False, description="是否为指针")
    is_const: bool = Field(False, description="是否为常量")


class MemberInfo(BaseModel):
    """结构体成员信息模型"""
    name: str = Field("", description="成员名")
    type: str = Field("", description="成员类型")
    description: str = Field("", description="成员描述")
    offset: int = Field(0, description="偏移量")
    size: int = Field(0, description="大小")


class SymbolInfo(BaseModel):
    """符号信息模型"""
    id: str = Field(..., description="符号唯一ID")
    name: str = Field(..., description="符号名称")
    type: SymbolType = Field(..., description="符号类型")
    file_path: str = Field(..., description="文件路径")
    full_path: str = Field("", description="完整文件路径")
    declaration: str = Field("", description="声明")
    description: str = Field("", description="描述")
    line_number: int = Field(0, description="行号")
    
    # 函数特有字段
    body: Optional[str] = Field(None, description="函数体")
    signature: Optional[str] = Field(None, description="函数签名")
    return_type: Optional[str] = Field(None, description="返回类型")
    parameters: Optional[List[ParameterInfo]] = Field(None, description="参数列表")
    is_static: Optional[bool] = Field(None, description="是否为静态函数")
    is_inline: Optional[bool] = Field(None, description="是否为内联函数")
    complexity: Optional[int] = Field(None, description="复杂度")
    
    # 结构体特有字段
    members: Optional[List[MemberInfo]] = Field(None, description="结构体成员")
    size_estimate: Optional[int] = Field(None, description="大小估算")
    is_packed: Optional[bool] = Field(None, description="是否为紧凑结构体")
    
    # 变量特有字段
    data_type: Optional[str] = Field(None, description="数据类型")
    is_global: Optional[bool] = Field(None, description="是否为全局变量")
    is_const: Optional[bool] = Field(None, description="是否为常量")
    scope: Optional[str] = Field(None, description="作用域")
    
    # 宏特有字段
    value: Optional[str] = Field(None, description="宏值")
    is_function_like: Optional[bool] = Field(None, description="是否为函数式宏")


class SearchResult(BaseModel):
    """搜索结果项模型"""
    symbol: SymbolInfo = Field(..., description="符号信息")
    similarity: float = Field(..., description="相似度分数")
    distance: float = Field(..., description="距离分数")
    match_reason: str = Field("", description="匹配原因")


class SearchResponse(BaseModel):
    """搜索响应模型"""
    results: List[SearchResult] = Field(..., description="搜索结果列表")
    total_count: int = Field(..., description="总结果数")
    query: str = Field(..., description="原始查询")
    search_type: SearchType = Field(..., description="搜索类型")
    execution_time: float = Field(..., description="执行时间(秒)")
    filters_applied: Dict[str, Any] = Field({}, description="应用的过滤条件")


class IndexBuildRequest(BaseModel):
    """索引构建请求模型"""
    project_path: str = Field(..., description="项目路径")
    force_rebuild: bool = Field(False, description="是否强制重建")
    include_patterns: Optional[List[str]] = Field(None, description="包含文件模式")
    exclude_patterns: Optional[List[str]] = Field(None, description="排除文件模式")


class IndexBuildResponse(BaseModel):
    """索引构建响应模型"""
    status: str = Field(..., description="构建状态")
    project_path: str = Field(..., description="项目路径")
    symbols_count: int = Field(0, description="符号总数")
    functions_count: int = Field(0, description="函数数量")
    structures_count: int = Field(0, description="结构体数量")
    variables_count: int = Field(0, description="变量数量")
    macros_count: int = Field(0, description="宏数量")
    build_time: str = Field("", description="构建时间")
    duration: float = Field(0.0, description="构建耗时(秒)")
    error_message: Optional[str] = Field(None, description="错误信息")


class ProjectSummary(BaseModel):
    """项目摘要模型"""
    project_path: str = Field(..., description="项目路径")
    last_indexed: str = Field("", description="最后索引时间")
    total_files: int = Field(0, description="文件总数")
    total_symbols: int = Field(0, description="符号总数")
    symbols_by_type: Dict[str, int] = Field({}, description="按类型分组的符号数量")
    index_size: int = Field(0, description="索引大小")
    is_up_to_date: bool = Field(True, description="索引是否最新")


class StatisticsResponse(BaseModel):
    """统计信息响应模型"""
    total_symbols: int = Field(0, description="符号总数")
    symbols_by_type: Dict[str, int] = Field({}, description="按类型分组的符号数量")
    symbols_by_project: Dict[str, int] = Field({}, description="按项目分组的符号数量")
    embedding_dimension: int = Field(0, description="嵌入向量维度")
    model_name: str = Field("", description="嵌入模型名称")
    projects: List[ProjectSummary] = Field([], description="项目列表")


class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: str = Field("healthy", description="服务状态")
    version: str = Field("1.0.0", description="版本号")
    uptime: float = Field(0.0, description="运行时间(秒)")
    components: Dict[str, str] = Field({}, description="组件状态")
    timestamp: str = Field("", description="检查时间")


class ErrorResponse(BaseModel):
    """错误响应模型"""
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误消息")
    detail: Optional[str] = Field(None, description="详细信息")
    timestamp: str = Field("", description="错误时间")
    request_id: Optional[str] = Field(None, description="请求ID") 