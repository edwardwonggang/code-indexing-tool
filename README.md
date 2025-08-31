# 🚀 C代码索引工具 - 使用指南

## 📋 这是什么？

这是一个**AI智能C代码分析工具**，可以：
- 📊 **分析C代码**：自动提取函数、变量、结构体等
- 🔍 **智能搜索**：用自然语言搜索代码（如"内存分配函数"）
- 🤖 **AI集成**：通过MCP协议让AI助手直接使用

## 💻 系统要求

- **操作系统**：Windows 10/11
- **Python版本**：3.10+
- **PowerShell**：Windows PowerShell 5.1+ 或 PowerShell 7+

---

## 🛠️ 需要安装什么？

### 1️⃣ Python依赖
```bash
pip install -r requirements.txt
pip install mcp
```

### 2️⃣ 完整工具安装指南

#### 🚀 一键自动安装（推荐）
```powershell
# 运行自动安装脚本（需要管理员权限）
.\install.ps1
```

这会自动安装所有必需工具：
- ✅ **CodeQL** - GitHub高级代码分析
- ✅ **Cppcheck** - C/C++静态分析  
- ✅ **Python LSP** - Python语言服务器
- ✅ **TypeScript LSP** - JavaScript/TypeScript语言服务器
- ✅ **Clangd LSP** - C/C++语言服务器
- ✅ **Universal CTags** - 符号提取
- ✅ **Cscope** - 调用关系分析

#### 🔧 手动安装（可选）

如果自动安装失败，可以手动安装各个工具：

##### 1. CodeQL（高级代码分析）
```powershell
# 下载并安装CodeQL CLI
$codeqlVersion = "2.15.4"
$codeqlUrl = "https://github.com/github/codeql-cli-binaries/releases/download/v$codeqlVersion/codeql-win64.zip"
Invoke-WebRequest -Uri $codeqlUrl -OutFile "codeql.zip"
Expand-Archive -Path "codeql.zip" -DestinationPath "C:\tools"

# 添加到PATH环境变量
$env:PATH += ";C:\tools\codeql\codeql"
```

##### 2. Cppcheck（C/C++静态分析）
```powershell
# 使用Chocolatey安装
choco install cppcheck

# 或手动下载：https://cppcheck.sourceforge.io/
```

##### 3. LSP服务器集合
```powershell
# Python LSP服务器
pip install python-lsp-server[all]

# TypeScript/JavaScript LSP服务器  
npm install -g typescript-language-server typescript

# Clangd LSP服务器（C/C++）
choco install llvm
```

##### 4. Universal CTags（符号提取）
```powershell
# 使用Chocolatey安装
choco install universal-ctags

# 或从官网下载：https://github.com/universal-ctags/ctags
```

##### 5. Cscope（调用关系分析）
```powershell
# 通过MSYS2安装
choco install msys2
#
# 方法2: 直接下载预编译包
# 1. 下载cscope预编译包
# 链接: https://mirror.msys2.org/msys/x86_64/cscope-15.9-2-x86_64.pkg.tar.zst

# 2. 在MSYS2中手动安装
# 打开MSYS2终端，执行：
#pacman -U cscope-15.9-2-x86_64.pkg.tar.zst

# 添加MSYS2到PATH：C:\msys64\usr\bin
```

#### ✅ 验证安装
运行验证脚本检查所有工具：
```powershell
python install.py
```

或手动验证各工具：
```powershell
# 检查版本信息
codeql version
cppcheck --version  
pylsp --version
typescript-language-server --version
clangd --version
ctags --version
cscope -V
```

#### 🔍 当前工具状态
| 工具 | 功能 | 安装方式 | 验证命令 |
|------|------|----------|----------|
| **CodeQL** | 高级代码分析 | GitHub下载 | `codeql version` |
| **Cppcheck** | C/C++静态分析 | Chocolatey | `cppcheck --version` |
| **Python LSP** | Python语言服务器 | pip | `pylsp --version` |
| **TypeScript LSP** | JS/TS语言服务器 | npm | `typescript-language-server --version` |
| **Clangd LSP** | C/C++语言服务器 | LLVM | `clangd --version` |
| **Universal CTags** | 符号提取 | Chocolatey | `ctags --version` |
| **Cscope** | 调用关系分析 | MSYS2 | `cscope -V` |

#### Clangd LSP（必备）
提供高精度的语义分析和类型推断：
```bash
# Windows使用Chocolatey安装LLVM（包含clangd）
choco install llvm

# 或从LLVM官网下载：https://releases.llvm.org/download.html
#'https://github.com/llvm/llvm-project/releases/download/llvmorg-20.1.8/LLVM-20.1.8-win64.exe'
# 下载Windows版本，解压后将bin目录添加到PATH
# 确保clangd.exe在PATH中可访问
```

#### Tree-sitter Query（必备）
高级语法查询功能：
```bash
# 已包含在requirements.txt中
pip install tree-sitter>=0.20.0

# 确保安装了C语言解析器
pip install tree-sitter-languages>=1.7.0
```

**在Windows PowerShell中验证安装**：
```powershell
# 检查CTags
ctags --version
# 预期输出：Universal Ctags 5.9.0

# 检查Cscope  
cscope -V
# 预期输出：cscope: version 15.9

# 检查Clangd
clangd --version
# 预期输出：clangd version 20.1.8

# 检查Tree-sitter（Python包）
python -c "import tree_sitter; print('Tree-sitter: 已安装')"
python -c "import tree_sitter_languages; print('Tree-sitter Languages: 已安装')"
```

---

## 🎯 有哪些功能？

| 功能 | 工具名称 | 实现技术 | 作用 |
|------|----------|----------|------|
| **构建索引** | `build_c_index` | Tree-sitter + CTags + Cscope | 分析整个C项目 |
| **语义搜索** | `search_code_semantic` | SentenceTransformers | 自然语言搜索 |
| **精确搜索** | `search_symbol_exact` | 向量数据库 | 按名称查找符号 |
| **项目统计** | `get_project_statistics` | 元数据管理 | 查看分析结果统计 |
| **按类型查看** | `get_symbols_by_type` | 符号分类 | 查看函数/结构体等 |
| **复杂度分析** | `analyze_function_complexity` | Lizard | 分析函数复杂程度 |
| **调用关系** | `get_callees/get_callers` | Cscope | 查看函数调用链 |

### ✅ 全功能分析能力
所有必备工具已安装，具备完整的分析功能：

| 分析功能 | 实现工具 | 能力 |
|----------|----------|------|
| **基础语法分析** | Tree-sitter + Lizard | 函数、变量、结构体提取，复杂度分析 |
| **精确符号提取** | Universal CTags | 跨文件引用、精确定义位置 |
| **调用关系分析** | Cscope | 函数调用链、符号引用关系 |
| **高精度语义分析** | Clangd LSP | 类型推断、语义理解、错误检测 |
| **高级语法查询** | TSQuery | 复杂模式匹配、精确代码结构识别 |

---

## 📁 生成什么文件？在哪里？

**首次运行后**，工具会自动创建 `data/` 目录：

```
data/                          # 📁 运行时自动创建
├── chroma/                    # 向量数据库
│   ├── chroma.sqlite3         # ChromaDB数据库文件
│   └── [uuid]/                # 向量索引文件
└── metadata/                  # 元数据文件
    └── project_name.json     # 项目分析结果
```

### 文件说明：
- **向量数据库**：支持语义搜索的AI模型数据（约17MB）
- **元数据文件**：项目统计、符号列表、索引状态（约2MB）
- **自动管理**：无需手动操作，工具自动维护

---

## 🎮 怎么使用？

### MCP方式（推荐）

#### 1️⃣ 启动MCP服务器
```bash
python mcp_server_working.py
```

#### 2️⃣ 在AI对话中使用

**构建索引**：
> "请为我的C项目 `D:\myproject\redis` 构建代码索引"

**语义搜索**：
> "在这个项目中搜索网络连接处理相关的函数"
> "找到内存分配相关的代码"

**精确查找**：
> "查找 `malloc` 函数的详细信息"

**获取统计**：
> "这个项目有多少个函数和结构体？"

**复杂度分析**：
> "分析 `parse_json` 函数的复杂度"

### Web API方式（可选）
```bash
# 启动Web服务器
python src/api/server.py

# 浏览器访问：http://localhost:8000
# 使用REST API进行搜索
```

---

## 🤖 MCP使用（AI助手集成）

### 1️⃣ 启动MCP服务器
```bash
python mcp_server_working.py
```

### 2️⃣ 在AI对话中使用

**构建索引**：
> "请为我的C项目 `D:\myproject\redis` 构建代码索引"

**语义搜索**：
> "在这个项目中搜索网络连接处理相关的函数"
> "找到内存分配相关的代码"

**精确查找**：
> "查找 `malloc` 函数的详细信息"

**获取统计**：
> "这个项目有多少个函数和结构体？"

**复杂度分析**：
> "分析 `parse_json` 函数的复杂度"

---

## 🔧 配置AI客户端

### Claude Desktop
在 `claude_desktop_config.json` 添加：
```json
{
  "mcpServers": {
    "c-code-indexer": {
      "command": "python",
      "args": ["D:/你的路径/mcp_server_working.py"]
    }
  }
}
```

### Cursor编辑器
在项目的 `.cursorrules` 文件中已配置好MCP工具，直接使用即可。

---

## ⚡ 快速开始示例

### 分析一个C项目的完整流程：

1. **准备项目**：确保有C源文件的目录
2. **构建索引**：`python mcp_server_working.py` 后对AI说："为 `D:\myproject` 构建索引"
3. **开始搜索**：对AI说："找到这个项目中的内存管理函数"
4. **查看结果**：AI会返回相关函数的详细信息

---

## 🆘 常见问题

**Q: 构建索引失败？**
A: 检查项目路径是否正确，确保包含 `.c` 或 `.h` 文件

**Q: 搜索结果为空？**  
A: 确保先构建了索引，且项目包含相关代码

**Q: MCP连接失败？**
A: 重启AI客户端，确保路径配置正确

**Q: 缺少CTags或Cscope？**
A: 这些是必备工具，请按照安装说明正确安装并配置PATH环境变量

**Q: Cscope找不到命令？**
A: 确保MSYS2安装正确，并将 `C:\msys64\usr\bin` 添加到系统PATH

**Q: Clangd LSP不工作？**
A: 请确保LLVM正确安装并在PATH中。验证：`clangd --version` 应显示版本20.1.8

**Q: 所有工具都是必需的吗？**
A: 是的，为了提供最佳的分析体验，所有7个工具都是必备的：
- **CodeQL**: GitHub高级代码分析和安全扫描
- **Cppcheck**: C/C++静态分析和错误检测
- **Python LSP**: Python代码智能分析
- **TypeScript LSP**: JavaScript/TypeScript代码分析
- **Clangd LSP**: C/C++高精度语义分析
- **Universal CTags**: 精确符号提取和跨文件引用
- **Cscope**: 调用关系分析和代码导航

**Q: 工具安装验证失败？**
A: 按照以下顺序检查：
1. **重新打开PowerShell窗口**（刷新环境变量）
2. **运行自动验证**：`python install.py`
3. **手动验证各工具**：
   ```powershell
   codeql version          # 应显示 CodeQL 2.15.4+
   cppcheck --version      # 应显示 Cppcheck 版本
   pylsp --version         # 应显示 Python LSP 版本
   typescript-language-server --version  # 应显示 TS LSP 版本
   clangd --version        # 应显示 Clangd 版本
   ctags --version         # 应显示 Universal CTags 版本
   cscope -V              # 应显示 Cscope 版本
   ```
4. **检查PATH环境变量**：确保所有工具目录都在系统PATH中
5. **重新运行安装脚本**：`.\install.ps1`（管理员权限）

**Q: 某个工具安装失败怎么办？**
A: 针对性解决方案：
- **CodeQL失败**：检查网络连接，手动下载ZIP文件
- **Cppcheck失败**：确保Chocolatey正常工作
- **LSP服务器失败**：检查pip和npm环境
- **CTags失败**：从GitHub手动下载二进制文件
- **Cscope失败**：确保MSYS2正确安装

---

## 🎉 就这么简单！

现在你可以让AI助手像分析师一样理解你的C代码了！ 