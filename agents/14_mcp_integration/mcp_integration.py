"""
MCP 协议集成 — Model Context Protocol Client

项目 12 用本地 Registry 管理工具，工具与 Agent 紧耦合。
本项目实现 MCP (Model Context Protocol) Client:
  - JSON-RPC 2.0 协议与 MCP Server 通信
  - 三阶段握手: initialize → initialized → ready
  - 工具发现: list_tools() 自动获取 Server 提供的工具列表
  - 工具调用: call_tool(name, arguments) 远程执行
  - 与 Ollama Function Calling 集成: MCP 工具自动转为 API tools 参数

核心概念:
- MCP: 标准化协议，Agent 无需硬编码工具，动态发现并调用
- JSON-RPC 2.0: 请求/响应消息格式（method, params, id）
- Server 能力: tools / resources / prompts 三类能力
"""

import json
import os
import select
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"
HEADERS = {"Content-Type": "application/json"}

# MCP Server 配置
# 官方包名是 @modelcontextprotocol/server-filesystem
# （旧名 @anthropic-ai/... 已废弃, npx 解析会失败导致握手拿到空响应）
MCP_SERVER_CMD = "npx -y @modelcontextprotocol/server-filesystem"
MCP_SERVER_ARGS = [os.path.join(SCRIPT_DIR, "workspace")]


# ============================================================
# JSON-RPC 2.0 基础
# ============================================================

class JsonRpcClient:
    """Minimal JSON-RPC 2.0 client over stdio."""

    def __init__(self):
        self._id = 0
        self._proc = None
        self._buffer = ""

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def start(self, cmd: str, args: list = None):
        """Launch MCP Server as subprocess (stdio transport)."""
        full_cmd = cmd
        if args:
            full_cmd += " " + " ".join(args)
        self._proc = subprocess.Popen(
            full_cmd, shell=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )

    def _read_response(self, timeout: float = 90.0) -> str:
        """按行读一条响应。

        npx 首次拉取包可能耗时远超固定 sleep——用 select 轮询
        等待 stdout 可读（带总超时），比裸 readline/裸 sleep 更稳。
        """
        deadline = time.time() + timeout
        out = self._proc.stdout
        while time.time() < deadline:
            if self._proc.poll() is not None:
                return ""
            ready, _, _ = select.select([out], [], [], 1.0)
            if ready:
                line = out.readline()
                if line.strip():
                    return line
        return ""

    def send(self, method: str, params: dict = None) -> dict:
        """Send JSON-RPC request, read response."""
        if not self._proc or self._proc.poll() is not None:
            return {"error": {"message": "Server not running"}}

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params:
            request["params"] = params

        payload = json.dumps(request)
        self._proc.stdin.write(payload + "\n")
        self._proc.stdin.flush()

        # Read response (line-delimited JSON)
        try:
            line = self._read_response()
            return json.loads(line.strip()) if line.strip() else {}
        except Exception as e:
            return {"error": {"message": str(e)}}

    def send_notification(self, method: str, params: dict = None):
        """Send notification (no id, no response expected)."""
        if not self._proc or self._proc.poll() is not None:
            return
        request = {"jsonrpc": "2.0", "method": method}
        if params:
            request["params"] = params
        payload = json.dumps(request)
        self._proc.stdin.write(payload + "\n")
        self._proc.stdin.flush()

    def stop(self):
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None


# ============================================================
# MCP Client
# ============================================================

class MCPClient:
    """MCP Client: connect, discover tools, call tools."""

    def __init__(self):
        self.rpc = JsonRpcClient()
        self.server_info = None
        self.tools = []
        self._initialized = False

    def connect(self, cmd: str, args: list = None) -> bool:
        """Connect to MCP Server (launch + initialize handshake)."""
        print(f"  Launching: {cmd} {' '.join(args or [])}")
        self.rpc.start(cmd, args)
        time.sleep(1)  # Wait for server to start

        # Step 1: initialize
        print("  [1] initialize...")
        resp = self.rpc.send("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "agent-mcp-client", "version": "0.1.0"},
        })
        if "error" in resp:
            print(f"  Init failed: {resp['error']}")
            return False

        self.server_info = resp.get("result", {})
        print(f"  Server: {self.server_info.get('serverInfo', {})}")

        # Step 2: initialized notification
        self.rpc.send_notification("notifications/initialized")
        self._initialized = True
        print("  [2] initialized -> ready")
        return True

    def list_tools(self) -> list:
        """Discover tools from MCP Server."""
        if not self._initialized:
            return []
        print("  [3] tools/list...")
        resp = self.rpc.send("tools/list")
        tools = resp.get("result", {}).get("tools", [])
        self.tools = tools
        print(f"  Found {len(tools)} tools:")
        for t in tools:
            print(f"    - {t.get('name')}: {t.get('description', '')[:60]}")
        return tools

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Call a tool on the MCP Server."""
        if not self._initialized:
            return {"error": "Not connected"}
        print(f"  [call] {name}({arguments})")
        resp = self.rpc.send("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        result = resp.get("result", {})
        content = result.get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return {"result": "\n".join(texts), "raw": result}

    def get_tools_schema(self) -> list:
        """Convert MCP tools to Ollama Function Calling schema."""
        schemas = []
        for t in self.tools:
            input_schema = t.get("inputSchema", {"type": "object", "properties": {}})
            schemas.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": input_schema,
                },
            })
        return schemas

    def disconnect(self):
        self.rpc.stop()
        self._initialized = False
        print("  Disconnected")


# ============================================================
# Agent loop（Ollama + MCP tools）
# ============================================================

def call_ollama(messages: list, tools_schema: list = None) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "options": {"temperature": 0.3, "num_predict": 512},
        "stream": False,
    }
    if tools_schema:
        payload["tools"] = tools_schema
    try:
        resp = __import__('requests').post(
            BASE_URL, headers=HEADERS, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def run_agent(mcp: MCPClient, question: str, max_rounds: int = 5):
    print(f"\nUser: {question}\n")
    messages = [{"role": "user", "content": question}]
    tools_schema = mcp.get_tools_schema()

    for rnd in range(max_rounds):
        print(f"--- Round {rnd + 1} ---")
        resp = call_ollama(messages, tools_schema)
        if "error" in resp:
            print(f"API Error: {resp['error']}")
            return

        message = resp.get("message", {})
        tool_calls = message.get("tool_calls", [])
        content = message.get("content", "")

        if not tool_calls:
            print(f"Agent: {content}")
            return

        messages.append(message)
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", {})
            result = mcp.call_tool(name, args)
            text = result.get("result", str(result))
            print(f"  >> {name} -> {text[:120]}")
            messages.append({"role": "tool", "tool_name": name, "content": text})

    print("Max rounds reached")


# ============================================================
# Demo 模式 — 模拟 MCP 交互（无需 npx 和 Ollama）
# ============================================================

def run_demo():
    print("=" * 60)
    print("MCP Protocol Integration -- Demo Mode (no Ollama/npx)")
    print("=" * 60)

    # Simulate MCP Server tools
    simulated_tools = [
        {
            "name": "read_file",
            "description": "Read contents of a file from the allowed directory",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                },
                "required": ["path"],
            },
        },
        {
            "name": "list_directory",
            "description": "List files and directories in the given path",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path"},
                },
                "required": [],
            },
        },
        {
            "name": "search_files",
            "description": "Search for files matching a pattern",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern"},
                    "path": {"type": "string", "description": "Directory to search"},
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "write_file",
            "description": "Write content to a file in the allowed directory",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    ]

    # ---- Phase 1: Simulate connection handshake ----
    print("\n--- Phase 1: MCP Connection Handshake ---")
    print("  JSON-RPC 2.0 Request (initialize):")
    init_request = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "agent-mcp-client", "version": "0.1.0"},
        },
    }
    print(f"    {json.dumps(init_request, indent=2)[:200]}")

    print("\n  JSON-RPC 2.0 Response:")
    init_response = {
        "jsonrpc": "2.0", "id": 1,
        "result": {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": "mcp-server-filesystem", "version": "0.6.0"},
        },
    }
    for line in json.dumps(init_response, indent=2).split('\n'):
        print(f"    {line}")

    print("\n  Notification (notifications/initialized):")
    notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    print(f"    {json.dumps(notif)}")
    print("  -> MCP handshake complete, server is ready")

    # ---- Phase 2: Tool discovery ----
    print(f"\n--- Phase 2: Tool Discovery (tools/list) ---")
    for t in simulated_tools:
        schema = json.dumps(t["inputSchema"], indent=2)
        params_str = ", ".join(t["inputSchema"].get("properties", {}).keys())
        print(f"  {t['name']}({params_str})")
        print(f"    {t['description'][:70]}")

    # ---- Phase 3: Tool invocation ----
    print(f"\n--- Phase 3: Tool Invocation (tools/call) ---")

    call_request = {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {
            "name": "list_directory",
            "arguments": {"path": "."},
        },
    }
    print(f"  Request: {json.dumps(call_request)}")

    call_response = {
        "jsonrpc": "2.0", "id": 3,
        "result": {
            "content": [
                {"type": "text", "text": "[DIR] notes\n[FILE] readme.md\n[FILE] data.csv"},
            ],
        },
    }
    resp_text = call_response["result"]["content"][0]["text"]
    print(f"  Response: {resp_text}")

    # ---- Phase 4: Schema conversion for Ollama ----
    print(f"\n--- Phase 4: MCP Tools -> Ollama Schema ---")
    for t in simulated_tools[:2]:
        ollama_schema = {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["inputSchema"],
            },
        }
        print(f"  {t['name']}: function calling schema ready")

    # ---- Summary ----
    print(f"\n{'='*60}")
    print("MCP Protocol Flow:")
    print("  1. Client launches Server (subprocess, stdio)")
    print("  2. initialize (JSON-RPC) -> Server info + capabilities")
    print("  3. notifications/initialized -> Ready")
    print("  4. tools/list -> Discover available tools")
    print("  5. tools/call -> Execute tool remotely")
    print("  6. Convert MCP tools -> Ollama schema -> Agent loop")
    print(f"{'='*60}")
    print("\nKey advantage over project 12 (local Registry):")
    print("  - Tools are NOT hardcoded in Agent code")
    print("  - Any MCP Server provides tools dynamically")
    print("  - Ecosystem: filesystem, database, web search, etc.")
    print("  - Standard protocol: same Client works with any Server")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        os.makedirs(os.path.join(SCRIPT_DIR, "workspace"), exist_ok=True)
        mcp = MCPClient()
        try:
            if mcp.connect(MCP_SERVER_CMD, MCP_SERVER_ARGS):
                mcp.list_tools()
                q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
                if q:
                    run_agent(mcp, q)
                else:
                    print("Usage: python mcp_integration.py [--demo | 'question']")
                    print("  --demo   : Simulate without npx/Ollama")
                    print("  question : Ask question (needs npx + Ollama)")
        finally:
            mcp.disconnect()
