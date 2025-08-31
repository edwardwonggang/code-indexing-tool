"""
API服务器

基于FastAPI的REST API服务器，提供索引查询接口
"""

import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import traceback

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
import uvicorn

from .models import (
    SearchRequest, SearchResponse, SearchResult, SymbolInfo,
    IndexBuildRequest, IndexBuildResponse, StatisticsResponse,
    HealthResponse, ErrorResponse, SymbolType, SearchType
)
from ..indexer import CCodeIndexer
from ..storage import VectorStore
from ..utils import Config


class IndexAPI:
    """索引API管理器"""
    
    def __init__(self, config: Optional[Config] = None):
        """
        初始化API管理器
        
        Args:
            config: 配置对象
        """
        self.config = config or Config()
        self.indexer = CCodeIndexer(self.config)
        self.vector_store = VectorStore(self.config)
        self.start_time = time.time()
        
        logger.info("索引API管理器初始化完成")
    
    def convert_search_result_to_model(self, result: Dict[str, Any]) -> SearchResult:
        """
        将向量存储的搜索结果转换为API模型
        
        Args:
            result: 向量存储搜索结果
            
        Returns:
            API搜索结果模型
        """
        metadata = result.get('metadata', {})
        
        # 构建符号信息
        symbol_info = SymbolInfo(
            id=result.get('id', ''),
            name=metadata.get('name', ''),
            type=metadata.get('type', 'unknown'),
            file_path=metadata.get('file_path', ''),
            full_path=metadata.get('full_path', ''),
            declaration=metadata.get('declaration', ''),
            description=metadata.get('description', ''),
            line_number=metadata.get('line_number', 0),
            # 函数特有字段
            body=metadata.get('body'),
            signature=metadata.get('signature'),
            return_type=metadata.get('return_type'),
            parameters=metadata.get('parameters'),
            is_static=metadata.get('is_static'),
            is_inline=metadata.get('is_inline'),
            complexity=metadata.get('complexity'),
            # 结构体特有字段
            members=metadata.get('members'),
            size_estimate=metadata.get('size_estimate'),
            is_packed=metadata.get('is_packed'),
            # 变量特有字段
            data_type=metadata.get('data_type'),
            is_global=metadata.get('is_global'),
            is_const=metadata.get('is_const'),
            scope=metadata.get('scope'),
            # 宏特有字段
            value=metadata.get('value'),
            is_function_like=metadata.get('is_function_like')
        )
        
        return SearchResult(
            symbol=symbol_info,
            similarity=result.get('similarity', 0.0),
            distance=result.get('distance', 1.0),
            match_reason=self._generate_match_reason(result)
        )
    
    def _generate_match_reason(self, result: Dict[str, Any]) -> str:
        """生成匹配原因说明"""
        similarity = result.get('similarity', 0.0)
        metadata = result.get('metadata', {})
        symbol_type = metadata.get('type', 'unknown')
        
        if similarity > 0.8:
            return f"高度匹配的{symbol_type}符号"
        elif similarity > 0.6:
            return f"相关的{symbol_type}符号"
        else:
            return f"可能相关的{symbol_type}符号"
    
    async def search_symbols(self, request: SearchRequest) -> SearchResponse:
        """
        搜索符号
        
        Args:
            request: 搜索请求
            
        Returns:
            搜索响应
        """
        start_time = time.time()
        
        try:
            # 构建过滤条件
            filter_dict = {}
            filters_applied = {}
            
            if request.symbol_type:
                filter_dict['type'] = request.symbol_type.value
                filters_applied['symbol_type'] = request.symbol_type.value
            
            if request.file_path:
                filter_dict['file_path'] = request.file_path
                filters_applied['file_path'] = request.file_path
            
            if request.project_path:
                filter_dict['project_path'] = request.project_path
                filters_applied['project_path'] = request.project_path
            
            # 执行搜索
            if request.search_type == SearchType.SEMANTIC:
                raw_results = self.vector_store.search(
                    query=request.query,
                    n_results=request.limit,
                    filter_dict=filter_dict
                )
            elif request.search_type == SearchType.EXACT:
                raw_results = self.vector_store.get_symbol_by_name(request.query)
                raw_results = raw_results[:request.limit]
            else:  # FUZZY
                # 模糊搜索可以使用语义搜索，但降低阈值
                raw_results = self.vector_store.search(
                    query=request.query,
                    n_results=request.limit * 2,  # 获取更多结果
                    filter_dict=filter_dict
                )
            
            # 应用相似度阈值过滤
            filtered_results = [
                result for result in raw_results 
                if result.get('similarity', 0.0) >= request.threshold
            ]
            
            # 转换为API模型
            search_results = [
                self.convert_search_result_to_model(result) 
                for result in filtered_results[:request.limit]
            ]
            
            execution_time = time.time() - start_time
            
            return SearchResponse(
                results=search_results,
                total_count=len(search_results),
                query=request.query,
                search_type=request.search_type,
                execution_time=execution_time,
                filters_applied=filters_applied
            )
            
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")
    
    async def build_index(self, request: IndexBuildRequest) -> IndexBuildResponse:
        """
        构建索引
        
        Args:
            request: 索引构建请求
            
        Returns:
            索引构建响应
        """
        start_time = time.time()
        
        try:
            # 验证项目路径
            project_path = Path(request.project_path)
            if not project_path.exists():
                raise HTTPException(status_code=400, detail=f"项目路径不存在: {request.project_path}")
            
            # 构建索引
            result = self.indexer.build_index(
                project_path=str(project_path),
                force_rebuild=request.force_rebuild
            )
            
            duration = time.time() - start_time
            
            return IndexBuildResponse(
                status=result.get('status', 'success'),
                project_path=result.get('project_path', ''),
                symbols_count=result.get('symbols_count', 0),
                functions_count=result.get('functions_count', 0),
                structures_count=result.get('structures_count', 0),
                variables_count=result.get('variables_count', 0),
                macros_count=result.get('macros_count', 0),
                build_time=result.get('build_time', ''),
                duration=duration
            )
            
        except Exception as e:
            duration = time.time() - start_time
            error_msg = str(e)
            logger.error(f"索引构建失败: {error_msg}")
            
            return IndexBuildResponse(
                status="error",
                project_path=request.project_path,
                duration=duration,
                error_message=error_msg
            )
    
    async def get_statistics(self) -> StatisticsResponse:
        """
        获取统计信息
        
        Returns:
            统计信息响应
        """
        try:
            stats = self.vector_store.get_statistics()
            
            return StatisticsResponse(
                total_symbols=stats.get('total_symbols', 0),
                symbols_by_type=stats.get('symbols_by_type', {}),
                symbols_by_project=stats.get('symbols_by_project', {}),
                embedding_dimension=stats.get('embedding_dimension', 0),
                model_name=stats.get('model_name', ''),
                projects=list(stats.get('indexed_projects', []))  # 显示已索引的项目列表
            )
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")
    
    async def get_health(self) -> HealthResponse:
        """
        健康检查
        
        Returns:
            健康检查响应
        """
        try:
            uptime = time.time() - self.start_time
            
            # 检查各组件状态
            components = {}
            try:
                # 检查向量存储
                stats = self.vector_store.get_statistics()
                components['vector_store'] = 'healthy'
            except Exception:
                components['vector_store'] = 'unhealthy'
            
            try:
                # 检查CLDK
                cldk = self.indexer.cldk
                components['cldk'] = 'healthy'
            except Exception:
                components['cldk'] = 'unhealthy'
            
            # 确定总体状态
            overall_status = 'healthy' if all(
                status == 'healthy' for status in components.values()
            ) else 'unhealthy'
            
            return HealthResponse(
                status=overall_status,
                version="1.0.0",
                uptime=uptime,
                components=components,
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return HealthResponse(
                status="unhealthy",
                version="1.0.0",
                uptime=time.time() - self.start_time,
                components={"error": str(e)},
                timestamp=datetime.now().isoformat()
            )


# 创建FastAPI应用
app = FastAPI(
    title="C代码索引API",
    description="基于IBM CodeLLM-DevKit的C语言代码索引和查询API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局API实例
api_instance = None

def get_api() -> IndexAPI:
    """获取API实例"""
    global api_instance
    if api_instance is None:
        api_instance = IndexAPI()
    return api_instance


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理器"""
    logger.error(f"API异常: {exc}\n{traceback.format_exc()}")
    
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="InternalServerError",
            message="服务内部错误",
            detail=str(exc),
            timestamp=datetime.now().isoformat()
        ).dict()
    )


@app.get("/", response_model=Dict[str, str])
async def root():
    """根路径"""
    return {
        "service": "C代码索引API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check(api: IndexAPI = Depends(get_api)):
    """健康检查"""
    return await api.get_health()


@app.get("/statistics", response_model=StatisticsResponse)
async def get_statistics(api: IndexAPI = Depends(get_api)):
    """获取统计信息"""
    return await api.get_statistics()


@app.post("/search", response_model=SearchResponse)
async def search_symbols(request: SearchRequest, api: IndexAPI = Depends(get_api)):
    """搜索符号"""
    return await api.search_symbols(request)


@app.get("/search/semantic", response_model=SearchResponse)
async def search_semantic(
    q: str = Query(..., description="搜索查询"),
    limit: int = Query(20, ge=1, le=100, description="返回结果数量"),
    symbol_type: Optional[str] = Query(None, description="符号类型过滤"),
    file_path: Optional[str] = Query(None, description="文件路径过滤"),
    threshold: float = Query(0.5, ge=0.0, le=1.0, description="相似度阈值"),
    api: IndexAPI = Depends(get_api)
):
    """语义搜索（GET方式）"""
    request = SearchRequest(
        query=q,
        search_type=SearchType.SEMANTIC,
        symbol_type=SymbolType(symbol_type) if symbol_type else None,
        file_path=file_path,
        limit=limit,
        threshold=threshold
    )
    return await api.search_symbols(request)


@app.get("/search/exact", response_model=SearchResponse)
async def search_exact(
    q: str = Query(..., description="精确搜索查询"),
    limit: int = Query(20, ge=1, le=100, description="返回结果数量"),
    symbol_type: Optional[str] = Query(None, description="符号类型过滤"),
    file_path: Optional[str] = Query(None, description="文件路径过滤"),
    api: IndexAPI = Depends(get_api)
):
    """精确搜索（GET方式）"""
    request = SearchRequest(
        query=q,
        search_type=SearchType.EXACT,
        symbol_type=SymbolType(symbol_type) if symbol_type else None,
        file_path=file_path,
        limit=limit
    )
    return await api.search_symbols(request)


@app.get("/symbols/{symbol_name}", response_model=SearchResponse)
async def get_symbol_by_name(
    symbol_name: str,
    api: IndexAPI = Depends(get_api)
):
    """按名称获取符号"""
    request = SearchRequest(
        query=symbol_name,
        search_type=SearchType.EXACT,
        limit=100
    )
    return await api.search_symbols(request)


@app.get("/symbols/type/{symbol_type}", response_model=SearchResponse)
async def get_symbols_by_type(
    symbol_type: SymbolType,
    limit: int = Query(50, ge=1, le=100, description="返回结果数量"),
    api: IndexAPI = Depends(get_api)
):
    """按类型获取符号"""
    request = SearchRequest(
        query="",
        search_type=SearchType.SEMANTIC,
        symbol_type=symbol_type,
        limit=limit,
        threshold=0.0  # 获取所有结果
    )
    return await api.search_symbols(request)


@app.post("/index/build", response_model=IndexBuildResponse)
async def build_index(
    request: IndexBuildRequest,
    background_tasks: BackgroundTasks,
    api: IndexAPI = Depends(get_api)
):
    """构建索引"""
    return await api.build_index(request)


@app.delete("/index/project/{project_path:path}")
async def delete_project_index(
    project_path: str,
    api: IndexAPI = Depends(get_api)
):
    """删除项目索引"""
    try:
        api.vector_store.delete_by_project(project_path)
        return {"status": "success", "message": f"项目 {project_path} 的索引已删除"}
    except Exception as e:
        logger.error(f"删除项目索引失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除索引失败: {str(e)}")


def start_server(config: Optional[Config] = None):
    """
    启动API服务器
    
    Args:
        config: 配置对象
    """
    global api_instance
    
    if config is None:
        config = Config()
    
    # 初始化API实例
    api_instance = IndexAPI(config)
    
    # 启动服务器
    uvicorn.run(
        app,
        host=config.get('api_host', '127.0.0.1'),
        port=config.get('api_port', 8000),
        workers=config.get('api_workers', 1),
        log_level=config.get('log_level', 'info').lower()
    )


if __name__ == "__main__":
    start_server() 