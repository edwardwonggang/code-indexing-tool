"""
Clangd LSP 客户端

通过 Language Server Protocol 与 clangd 通信，获取高精度的符号信息、语义分析和补全功能。

⚠ 依赖：需要系统安装 clangd，并位于 PATH 中。
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from loguru import logger
import uuid


class ClangdLSPClient:
    """Clangd LSP 客户端"""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        self.pending_requests: Dict[int, Callable] = {}
        self.is_initialized = False
        self.root_uri = ""
        self._lock = threading.Lock()

    def start(self, project_path: Path) -> bool:
        """启动 clangd 进程并初始化"""
        try:
            # 启动 clangd 进程
            self.process = subprocess.Popen(
                ["clangd", "--background-index", "--clang-tidy", "--completion-style=detailed"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0
            )
            
            # 启动读取线程
            self._reader_thread = threading.Thread(target=self._read_responses, daemon=True)
            self._reader_thread.start()
            
            # 发送初始化请求
            self.root_uri = project_path.as_uri()
            init_result = self._send_request("initialize", {
                "processId": None,
                "rootUri": self.root_uri,
                "capabilities": {
                    "textDocument": {
                        "publishDiagnostics": {"relatedInformation": True},
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                        "documentSymbol": {"symbolKind": {"valueSet": list(range(1, 27))}},
                        "definition": {"linkSupport": True},
                        "references": {"context": {"includeDeclaration": True}}
                    },
                    "workspace": {
                        "symbol": {"symbolKind": {"valueSet": list(range(1, 27))}}
                    }
                }
            })
            
            if init_result:
                # 发送 initialized 通知
                self._send_notification("initialized", {})
                self.is_initialized = True
                logger.info("Clangd LSP 客户端初始化成功")
                return True
            
        except FileNotFoundError:
            logger.error("未找到 clangd，请安装 clangd 并确保在 PATH 中")
        except Exception as e:
            logger.error(f"启动 clangd 失败: {e}")
        
        return False

    def get_workspace_symbols(self, query: str = "") -> List[Dict[str, Any]]:
        """获取工作区符号"""
        if not self.is_initialized:
            return []
        
        result = self._send_request("workspace/symbol", {"query": query})
        return result or []

    def get_document_symbols(self, file_path: Path) -> List[Dict[str, Any]]:
        """获取文档符号"""
        if not self.is_initialized:
            return []
        
        # 打开文档
        self._open_document(file_path)
        
        # 获取符号
        result = self._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": file_path.as_uri()}
        })
        
        return result or []

    def get_definition(self, file_path: Path, line: int, character: int) -> List[Dict[str, Any]]:
        """获取定义位置"""
        if not self.is_initialized:
            return []
        
        self._open_document(file_path)
        
        result = self._send_request("textDocument/definition", {
            "textDocument": {"uri": file_path.as_uri()},
            "position": {"line": line, "character": character}
        })
        
        return result or []

    def get_references(self, file_path: Path, line: int, character: int) -> List[Dict[str, Any]]:
        """获取引用位置"""
        if not self.is_initialized:
            return []
        
        self._open_document(file_path)
        
        result = self._send_request("textDocument/references", {
            "textDocument": {"uri": file_path.as_uri()},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True}
        })
        
        return result or []

    def get_hover_info(self, file_path: Path, line: int, character: int) -> Optional[Dict[str, Any]]:
        """获取悬停信息"""
        if not self.is_initialized:
            return None
        
        self._open_document(file_path)
        
        result = self._send_request("textDocument/hover", {
            "textDocument": {"uri": file_path.as_uri()},
            "position": {"line": line, "character": character}
        })
        
        return result

    def extract_project_symbols(self, project_path: Path) -> List[Dict[str, Any]]:
        """提取项目符号（统一格式）"""
        symbols = []
        
        # 获取工作区符号
        workspace_symbols = self.get_workspace_symbols()
        
        for ws_symbol in workspace_symbols:
            symbol = self._convert_lsp_symbol(ws_symbol, project_path)
            if symbol:
                symbols.append(symbol)
        
        # 遍历所有 C/H 文件获取详细符号
        c_files = list(project_path.rglob("*.c")) + list(project_path.rglob("*.h"))
        for file_path in c_files:
            try:
                doc_symbols = self.get_document_symbols(file_path)
                for doc_symbol in doc_symbols:
                    symbol = self._convert_document_symbol(doc_symbol, file_path, project_path)
                    if symbol:
                        symbols.append(symbol)
            except Exception as e:
                logger.warning(f"获取文档符号失败 {file_path}: {e}")
        
        logger.info(f"Clangd LSP 提取完成，共 {len(symbols)} 个符号")
        return symbols

    def shutdown(self):
        """关闭 LSP 客户端"""
        if self.is_initialized:
            self._send_request("shutdown", {})
            self._send_notification("exit", {})
        
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None
        
        self.is_initialized = False
        logger.info("Clangd LSP 客户端已关闭")

    # ----------------------
    # 私有方法
    # ----------------------

    def _send_request(self, method: str, params: Dict[str, Any], timeout: float = 5.0) -> Any:
        """发送 LSP 请求"""
        if not self.process:
            return None
        
        with self._lock:
            self.request_id += 1
            req_id = self.request_id
        
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params
        }
        
        # 创建响应等待事件
        response_event = threading.Event()
        response_data = {"result": None, "error": None}
        
        def response_handler(result, error):
            response_data["result"] = result
            response_data["error"] = error
            response_event.set()
        
        self.pending_requests[req_id] = response_handler
        
        # 发送请求
        message = json.dumps(request, ensure_ascii=False)
        content = f"Content-Length: {len(message.encode('utf-8'))}\r\n\r\n{message}"
        
        try:
            self.process.stdin.write(content)
            self.process.stdin.flush()
        except Exception as e:
            logger.error(f"发送 LSP 请求失败: {e}")
            return None
        
        # 等待响应
        if response_event.wait(timeout):
            if response_data["error"]:
                logger.warning(f"LSP 请求错误: {response_data['error']}")
            return response_data["result"]
        else:
            logger.warning(f"LSP 请求超时: {method}")
            self.pending_requests.pop(req_id, None)
            return None

    def _send_notification(self, method: str, params: Dict[str, Any]):
        """发送 LSP 通知"""
        if not self.process:
            return
        
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        message = json.dumps(notification, ensure_ascii=False)
        content = f"Content-Length: {len(message.encode('utf-8'))}\r\n\r\n{message}"
        
        try:
            self.process.stdin.write(content)
            self.process.stdin.flush()
        except Exception as e:
            logger.error(f"发送 LSP 通知失败: {e}")

    def _read_responses(self):
        """读取 LSP 响应的后台线程"""
        buffer = ""
        
        while self.process and self.process.poll() is None:
            try:
                char = self.process.stdout.read(1)
                if not char:
                    continue
                
                buffer += char
                
                # 解析完整的消息
                while "\r\n\r\n" in buffer:
                    header_end = buffer.find("\r\n\r\n")
                    header = buffer[:header_end]
                    
                    # 解析 Content-Length
                    content_length = 0
                    for line in header.split("\r\n"):
                        if line.startswith("Content-Length:"):
                            content_length = int(line.split(":")[1].strip())
                            break
                    
                    if content_length == 0:
                        buffer = buffer[header_end + 4:]
                        continue
                    
                    # 读取消息体
                    message_start = header_end + 4
                    if len(buffer) >= message_start + content_length:
                        message_body = buffer[message_start:message_start + content_length]
                        buffer = buffer[message_start + content_length:]
                        
                        # 处理消息
                        self._handle_message(message_body)
                    else:
                        break
                        
            except Exception as e:
                logger.error(f"读取 LSP 响应失败: {e}")
                break

    def _handle_message(self, message_body: str):
        """处理 LSP 消息"""
        try:
            message = json.loads(message_body)
            
            if "id" in message and message["id"] in self.pending_requests:
                # 这是对请求的响应
                handler = self.pending_requests.pop(message["id"])
                result = message.get("result")
                error = message.get("error")
                handler(result, error)
            
        except Exception as e:
            logger.error(f"处理 LSP 消息失败: {e}")

    def _open_document(self, file_path: Path):
        """打开文档"""
        try:
            from ..utils.windows_compat import WindowsCompatibility
            content = WindowsCompatibility.safe_read_text(file_path)
            self._send_notification("textDocument/didOpen", {
                "textDocument": {
                    "uri": file_path.as_uri(),
                    "languageId": "c",
                    "version": 1,
                    "text": content
                }
            })
        except Exception as e:
            logger.warning(f"打开文档失败 {file_path}: {e}")

    def _convert_lsp_symbol(self, lsp_symbol: Dict[str, Any], project_path: Path) -> Optional[Dict[str, Any]]:
        """转换 LSP 工作区符号为内部格式"""
        try:
            name = lsp_symbol.get("name", "")
            kind = lsp_symbol.get("kind", 0)
            location = lsp_symbol.get("location", {})
            uri = location.get("uri", "")
            
            if not uri:
                return None
            
            # 转换路径
            file_path = Path(uri.replace("file://", ""))
            from ..utils.windows_compat import normalize_path
            rel_path = normalize_path(file_path.relative_to(project_path))
            
            # 转换符号类型
            symbol_type = self._lsp_kind_to_type(kind)
            if not symbol_type:
                return None
            
            line_number = location.get("range", {}).get("start", {}).get("line", 0) + 1
            
            return {
                "id": self._generate_id(symbol_type, name, rel_path, line_number),
                "name": name,
                "type": symbol_type,
                "file_path": rel_path,
                "line_number": line_number,
                "declaration": "",
                "description": f"{symbol_type} {name} (from clangd LSP)"
            }
        except Exception as e:
            logger.debug(f"转换 LSP 符号失败: {e}")
            return None

    def _convert_document_symbol(self, doc_symbol: Dict[str, Any], file_path: Path, project_path: Path) -> Optional[Dict[str, Any]]:
        """转换文档符号为内部格式"""
        try:
            name = doc_symbol.get("name", "")
            kind = doc_symbol.get("kind", 0)
            range_info = doc_symbol.get("range", {})
            
            symbol_type = self._lsp_kind_to_type(kind)
            if not symbol_type:
                return None
            
            from ..utils.windows_compat import normalize_path
            rel_path = normalize_path(file_path.relative_to(project_path))
            line_number = range_info.get("start", {}).get("line", 0) + 1
            
            return {
                "id": self._generate_id(symbol_type, name, rel_path, line_number),
                "name": name,
                "type": symbol_type,
                "file_path": rel_path,
                "line_number": line_number,
                "declaration": doc_symbol.get("detail", ""),
                "description": f"{symbol_type} {name} (from clangd LSP document)"
            }
        except Exception as e:
            logger.debug(f"转换文档符号失败: {e}")
            return None

    def _lsp_kind_to_type(self, kind: int) -> Optional[str]:
        """LSP 符号类型转换"""
        # LSP SymbolKind 枚举值
        kind_map = {
            12: "function",      # Function
            5: "structure",      # Class (用作 struct)
            23: "structure",     # Struct
            10: "enum",          # Enum
            25: "typedef",       # TypeParameter (近似)
            13: "variable",      # Variable
            14: "variable",      # Constant
            15: "variable",      # String
            16: "variable",      # Number
            17: "variable",      # Boolean
            18: "variable",      # Array
        }
        return kind_map.get(kind)

    def _generate_id(self, symbol_type: str, name: str, file_path: str, line_number: int = 0) -> str:
        import hashlib
        unique_suffix = str(uuid.uuid4())[:8]
        content = f"clangd:{symbol_type}:{name}:{file_path}:{line_number}:{unique_suffix}"
        return hashlib.md5(content.encode()).hexdigest()[:16] 