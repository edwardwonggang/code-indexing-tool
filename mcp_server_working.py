#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C代码索引工具 MCP Server (工作版)

真正能运行的版本，修复所有已知问题
"""

import asyncio
import sys
import os
from pathlib import Path

# 设置编码环境变量
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    import mcp.types as types
    from mcp.server.stdio import stdio_server
except ImportError as e:
    print(f"MCP 导入失败: {e}", file=sys.stderr)
    print("请运行: pip install mcp", file=sys.stderr)
    sys.exit(1)

# 创建 MCP 服务器实例
server = Server("c-code-indexer")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """返回可用的工具列表"""
    return [
        Tool(
            name="build_c_index",
            description="为C语言项目构建代码索引",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "C项目的根目录路径"
                    },
                    "force_rebuild": {
                        "type": "boolean", 
                        "description": "是否强制重建索引",
                        "default": False
                    }
                },
                "required": ["project_path"]
            }
        ),
        Tool(
            name="search_code_semantic",
            description="使用自然语言语义搜索C代码符号",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "自然语言搜索查询，例如：'内存分配函数'、'JSON解析'等"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量限制",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="search_symbol_exact",
            description="精确搜索特定的符号名称",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_name": {
                        "type": "string",
                        "description": "要搜索的确切符号名称，例如：'malloc'、'cJSON_Parse'等"
                    }
                },
                "required": ["symbol_name"]
            }
        ),
        Tool(
            name="get_project_statistics",
            description="获取项目的索引统计信息",
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        ),
        Tool(
            name="get_symbols_by_type",
            description="按类型获取符号列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_type": {
                        "type": "string",
                        "enum": ["function", "structure", "variable", "macro", "typedef", "enum"],
                        "description": "要获取的符号类型"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量限制",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 100
                    }
                },
                "required": ["symbol_type"]
            }
        ),
        Tool(
            name="analyze_function_complexity",
            description="分析函数复杂度",
            inputSchema={
                "type": "object",
                "properties": {
                    "function_name": {
                        "type": "string",
                        "description": "要分析的函数名称"
                    }
                },
                "required": ["function_name"]
            }
        ),
        Tool(
            name="get_callees",
            description="根据符号ID查询被调函数（可指定深度）",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {"type": "string", "description": "起始符号ID"},
                    "depth": {"type": "integer", "default": 1}
                },
                "required": ["symbol_id"]
            }
        ),
        Tool(
            name="get_callers",
            description="根据符号ID查询调用者（可指定深度）",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {"type": "string", "description": "目标符号ID"},
                    "depth": {"type": "integer", "default": 1}
                },
                "required": ["symbol_id"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """处理工具调用"""
    try:
        if name == "build_c_index":
            return await build_c_index(arguments)
        elif name == "search_code_semantic":
            return await search_code_semantic(arguments)
        elif name == "search_symbol_exact":
            return await search_symbol_exact(arguments)
        elif name == "get_project_statistics":
            return await get_project_statistics(arguments)
        elif name == "get_symbols_by_type":
            return await get_symbols_by_type(arguments)
        elif name == "analyze_function_complexity":
            return await analyze_function_complexity(arguments)
        elif name == "get_callees":
            return await get_callees(arguments)
        elif name == "get_callers":
            return await get_callers(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")
            
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"❌ 工具执行错误: {str(e)}"
        )]

async def build_c_index(args: dict) -> list[types.TextContent]:
    """构建C代码索引"""
    project_path = args["project_path"]
    force_rebuild = args.get("force_rebuild", False)
    
    if not Path(project_path).exists():
        return [types.TextContent(
            type="text",
            text=f"❌ 错误: 项目路径不存在: {project_path}"
        )]
    
    try:
        # 尝试使用真实的索引器
        try:
            from src.indexer import CCodeIndexer
            from src.utils import Config
            
            config = Config()
            indexer = CCodeIndexer(config)
            result = indexer.build_index(project_path, force_rebuild=force_rebuild)
            
            return [types.TextContent(
                type="text",
                text=f"""✅ C代码索引构建完成!

📊 **索引统计信息**:
   📁 项目路径: {project_path}
   🔢 总符号数: {result.get('symbols_count', 0)}
   🎯 函数数量: {result.get('functions_count', 0)}
   🏗️ 结构体数量: {result.get('structures_count', 0)}
   📦 变量数量: {result.get('variables_count', 0)}
   ⚙️ 宏定义数量: {result.get('macros_count', 0)}
   
📈 **性能信息**:
   ⏱️ 索引时间: {result.get('build_time', 'N/A')}
   💾 索引大小: {result.get('index_size', 'N/A')}

🎉 现在可以使用语义搜索和精确搜索功能了！"""
            )]
            
        except ImportError:
            # 如果导入失败，返回模拟结果
            c_files = list(Path(project_path).rglob("*.c")) + list(Path(project_path).rglob("*.h"))
            file_count = len(c_files)
            
            return [types.TextContent(
                type="text",
                text=f"""📋 **模拟索引构建完成** (需要完整安装才能使用实际功能)

📁 项目路径: {project_path}
🔄 强制重建: {force_rebuild}
📄 发现C/H文件: {file_count} 个

💡 **要使用完整功能，请确保**:
1. 所有依赖已安装: `pip install -r requirements.txt`
2. 项目结构完整
3. Python环境正确配置

📚 **安装完成后可以**:
- 🔍 语义搜索: "内存分配相关的函数"
- 🎯 精确搜索: "malloc", "free"
- 📊 获取统计信息
- 📝 按类型浏览符号"""
            )]
            
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"❌ 索引构建失败: {str(e)}\n\n请检查项目路径是否正确，以及是否包含C源代码文件。"
        )]

async def search_code_semantic(args: dict) -> list[types.TextContent]:
    """语义搜索代码"""
    query = args["query"]
    limit = args.get("limit", 10)
    
    try:
        try:
            from src.storage import VectorStore
            from src.utils import Config
            
            config = Config()
            vector_store = VectorStore(config)
            results = vector_store.search(query, n_results=limit)
            
            if not results:
                return [types.TextContent(
                    type="text",
                    text=f"🔍 **语义搜索结果**: '{query}'\n\n❌ 未找到相关符号。\n\n💡 **建议**:\n- 尝试更通用的关键词\n- 确保已构建项目索引\n- 检查项目是否包含相关代码"
                )]
            
            result_text = f"🔍 **语义搜索结果**: '{query}'\n找到 **{len(results)}** 个相关符号:\n\n"
            
            for i, result in enumerate(results, 1):
                metadata = result['metadata']
                similarity = result.get('similarity', 0.0)
                
                result_text += f"**{i}. {metadata['name']}** ({metadata['type']})\n"
                result_text += f"   🆔 ID: {result.get('id', 'N/A')}\n"
                result_text += f"   📄 {metadata['file_path']}:{metadata.get('line_number', '?')}\n"
                result_text += f"   📝 {metadata.get('declaration', 'N/A')}\n"
                result_text += f"   🎯 相似度: {similarity:.2%}\n\n"
            
            return [types.TextContent(type="text", text=result_text)]
            
        except ImportError:
            return [types.TextContent(
                type="text",
                text=f"""📋 **模拟语义搜索**: '{query}'
限制: {limit} 个结果

💡 **模拟结果**:
1. **sample_function** (function)
   📄 example.c:10
   📝 void sample_function(int param);
   🎯 相似度: 85%

2. **utility_helper** (function)  
   📄 utils.c:25
   📝 int utility_helper(const char* input);
   🎯 相似度: 78%

要使用实际搜索功能，请先构建项目索引。"""
            )]
            
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"❌ 语义搜索失败: {str(e)}"
        )]

async def search_symbol_exact(args: dict) -> list[types.TextContent]:
    """精确搜索符号"""
    symbol_name = args["symbol_name"]
    
    try:
        try:
            from src.storage import VectorStore
            from src.utils import Config
            
            config = Config()
            vector_store = VectorStore(config)
            results = vector_store.get_symbol_by_name(symbol_name)
            
            if not results:
                return [types.TextContent(
                    type="text",
                    text=f"🎯 **精确搜索结果**: '{symbol_name}'\n\n❌ 未找到符号。\n\n💡 **建议**:\n- 检查符号名称拼写\n- 确保符号存在于已索引的代码中\n- 尝试语义搜索获取相关符号"
                )]
            
            result_text = f"🎯 **精确搜索结果**: '{symbol_name}'\n找到 **{len(results)}** 个匹配:\n\n"
            
            for i, result in enumerate(results, 1):
                metadata = result['metadata']
                result_text += f"**{i}. {metadata['name']}** ({metadata['type']})\n"
                result_text += f"   🆔 ID: {result.get('id', 'N/A')}\n"
                result_text += f"   📄 {metadata['file_path']}:{metadata.get('line_number', '?')}\n"
                result_text += f"   📝 {metadata.get('declaration', 'N/A')}\n\n"
            
            return [types.TextContent(type="text", text=result_text)]
            
        except ImportError:
            return [types.TextContent(
                type="text",
                text=f"""📋 **模拟精确搜索**: '{symbol_name}'

💡 **模拟结果**:
**{symbol_name}** (function)
📄 example.c:25  
📝 int {symbol_name}(const char* input);

要使用实际搜索功能，请先构建项目索引。"""
            )]
            
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"❌ 精确搜索失败: {str(e)}"
        )]

async def get_project_statistics(args: dict) -> list[types.TextContent]:
    """获取项目统计信息"""
    try:
        try:
            from src.storage import VectorStore
            from src.utils import Config
            
            config = Config()
            vector_store = VectorStore(config)
            stats = vector_store.get_statistics()
            
            result_text = "📊 **项目索引统计信息**:\n\n"
            result_text += f"🔢 总符号数: **{stats['total_symbols']}**\n"
            result_text += f"🧮 向量维度: {stats['embedding_dimension']}\n"
            result_text += f"🤖 嵌入模型: {stats['model_name']}\n\n"
            
            result_text += "📈 **符号类型分布**:\n"
            for symbol_type, count in stats['symbols_by_type'].items():
                percentage = (count / stats['total_symbols']) * 100 if stats['total_symbols'] > 0 else 0
                result_text += f"   {symbol_type}: **{count}** 个 ({percentage:.1f}%)\n"
            
            return [types.TextContent(type="text", text=result_text)]
            
        except ImportError:
            return [types.TextContent(
                type="text",
                text="""📊 **模拟项目统计信息**:

🔢 总符号数: **128**
🧮 向量维度: 384  
🤖 嵌入模型: sentence-transformers/all-MiniLM-L6-v2

📈 **符号类型分布**:
   function: **85** 个 (66.4%)
   structure: **12** 个 (9.4%)
   variable: **31** 个 (24.2%)

💡 要查看实际统计，请先构建项目索引。"""
            )]
            
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"❌ 获取统计信息失败: {str(e)}"
        )]

async def get_symbols_by_type(args: dict) -> list[types.TextContent]:
    """按类型获取符号"""
    symbol_type = args["symbol_type"]
    limit = args.get("limit", 20)
    
    try:
        try:
            from src.storage import VectorStore
            from src.utils import Config
            
            config = Config()
            vector_store = VectorStore(config)
            results = vector_store.search_by_symbol_type(symbol_type, limit=limit)
            
            if not results:
                return [types.TextContent(
                    type="text",
                    text=f"📂 **{symbol_type} 类型符号**:\n\n❌ 未找到 {symbol_type} 类型的符号。"
                )]
            
            result_text = f"📂 **{symbol_type} 类型符号** (显示前 {len(results)} 个):\n\n"
            
            for i, result in enumerate(results, 1):
                metadata = result['metadata']
                result_text += f"**{i}. {metadata['name']}**\n"
                result_text += f"   📄 {metadata['file_path']}:{metadata.get('line_number', '?')}\n"
                result_text += f"   📝 {metadata.get('declaration', 'N/A')}\n\n"
            
            return [types.TextContent(type="text", text=result_text)]
            
        except ImportError:
            return [types.TextContent(
                type="text",
                text=f"""📋 **模拟 {symbol_type} 类型符号**:

1. **sample_{symbol_type}**
   📄 example.c:10
   📝 示例声明

2. **another_{symbol_type}**
   📄 utils.c:25
   📝 另一个示例

要查看实际符号，请先构建项目索引。"""
            )]
            
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"❌ 获取符号失败: {str(e)}"
        )]

async def analyze_function_complexity(args: dict) -> list[types.TextContent]:
    """分析函数复杂度"""
    function_name = args["function_name"]
    
    try:
        try:
            from src.storage import VectorStore
            from src.utils import Config
            
            config = Config()
            vector_store = VectorStore(config)
            results = vector_store.get_symbol_by_name(function_name)
            
            # 过滤出函数类型的结果
            functions = [r for r in results if r['metadata'].get('type') == 'function']
            
            if not functions:
                return [types.TextContent(
                    type="text",
                    text=f"🧮 **函数复杂度分析**: '{function_name}'\n\n❌ 未找到该函数。"
                )]
            
            result_text = f"🧮 **函数复杂度分析**: '{function_name}'\n\n"
            
            for func in functions:
                metadata = func['metadata']
                result_text += f"**📍 {metadata['name']}**\n"
                result_text += f"   📄 {metadata['file_path']}:{metadata.get('line_number', '?')}\n"
                result_text += f"   📝 {metadata.get('declaration', 'N/A')}\n"
                
                complexity = metadata.get('complexity', 'N/A')
                result_text += f"   🧮 复杂度评分: {complexity}\n\n"
            
            return [types.TextContent(type="text", text=result_text)]
            
        except ImportError:
            return [types.TextContent(
                type="text",
                text=f"""📋 **模拟函数复杂度分析**: '{function_name}'

**📍 {function_name}**
📄 example.c:25
📝 int {function_name}(const char* input);
🧮 复杂度评分: 中等 (15)

💡 要获取实际分析，请先构建项目索引。"""
            )]
            
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"❌ 复杂度分析失败: {str(e)}"
        )]

async def get_callees(args: dict) -> list[types.TextContent]:
    symbol_id = args["symbol_id"]
    depth = args.get("depth", 1)
    try:
        from src.utils import Config
        from src.storage import GraphStore
        config = Config()
        graph_path = config.get_metadata_dir() / "call_graph.json"
        store = GraphStore(graph_path)
        store.load()
        callees = store.get_callees(symbol_id, depth=depth)
        lines = [f"📞 Callees(depth={depth}): {len(callees)}"] + [f"- {c}" for c in callees]
        return [types.TextContent(type="text", text="\n".join(lines))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 获取被调失败: {e}")]

async def get_callers(args: dict) -> list[types.TextContent]:
    symbol_id = args["symbol_id"]
    depth = args.get("depth", 1)
    try:
        from src.utils import Config
        from src.storage import GraphStore
        config = Config()
        graph_path = config.get_metadata_dir() / "call_graph.json"
        store = GraphStore(graph_path)
        store.load()
        callers = store.get_callers(symbol_id, depth=depth)
        lines = [f"📣 Callers(depth={depth}): {len(callers)}"] + [f"- {c}" for c in callers]
        return [types.TextContent(type="text", text="\n".join(lines))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 获取调用者失败: {e}")]

async def main():
    """主函数 - 启动MCP服务器"""
    # 使用标准输入输出运行服务器
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, 
            write_stream, 
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main()) 