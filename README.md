# 🚀 C代码索引工具

**AI智能C代码分析工具** - 让AI助手像专家一样理解你的C代码！

## ✨ 核心功能

- 📊 **智能分析**：自动提取函数、变量、结构体等代码符号
- 🔍 **语义搜索**：用自然语言搜索代码（如"内存分配函数"）  
- 🤖 **AI集成**：通过MCP协议与AI助手无缝集成
- ⚡ **高性能**：支持大型项目，200+ files/s处理速度

## 🎯 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
pip install mcp
```

### 2. 启动MCP服务器
```bash
python mcp_server_working.py
```

### 3. 对AI说话
> "请为我的C项目 `D:\myproject` 构建代码索引"
> "搜索内存分配相关的函数"

## 📖 完整指南

**👉 查看 [使用指南.md](使用指南.md) 获取详细说明**

包含：
- 🛠️ 完整安装步骤
- 🎯 所有功能详解  
- 📁 生成文件说明
- 🤖 MCP使用方法
- ⚡ 快速开始示例

## 🏗️ 项目结构

```
c-code-indexer/
├── src/                      # 核心源代码
├── mcp_server_working.py     # MCP服务器（主要入口）
├── 使用指南.md               # 完整使用说明 📖
├── requirements.txt          # Python依赖
├── test_project_cjson/       # 测试项目
└── .cursorrules             # Cursor编辑器MCP配置
```

**运行时生成**：
- `data/` - 索引数据和向量数据库（首次运行后自动创建）

## 🎮 支持的操作

| 功能 | MCP工具 | AI对话示例 |
|------|---------|-----------|
| 构建索引 | `build_c_index` | "分析这个C项目" |
| 语义搜索 | `search_code_semantic` | "找内存管理函数" |
| 精确查找 | `search_symbol_exact` | "查找malloc函数" |
| 获取统计 | `get_project_statistics` | "项目有多少函数？" |

## 💡 技术特色

- **多层次分析**：Tree-sitter + CTags + Cscope 三重保障
- **AI增强搜索**：SentenceTransformers语义理解
- **增量索引**：智能缓存，支持大型项目
- **Windows优化**：专门为Windows环境优化

---

**🎉 让AI成为你的C代码分析助手！** 