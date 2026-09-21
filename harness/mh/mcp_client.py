"""mh.mcp_client — MCP 动态工具 (项目 15): 发现·代理·过权限门

MCP server(interview/19 的书店夹具)作为外部进程, 客户端桥接三步:
  1. 后台线程跑独立 event loop, 维持持久 stdio 会话(避免每次调用重启进程)
  2. list_tools → 动态注册进 mh 工具表(schema 从 MCP inputSchema 映射)
  3. 每次调用经 07 权限门(外部工具不可信, 拦截点在意图与副作用之间)

信任边界: MCP 工具不是"直接信" —— 与 interview/20 的 guard 思路一致,
本模块把它做进 mh 的工具表协议里。
"""

import asyncio
import json
import threading
from pathlib import Path


class MCPBridge:
    """持久 MCP 客户端桥: 同步接口, 后台线程 + 单一常驻协程。

    关键: stdio_client 的 anyio 上下文绑定在创建它的任务上, 协程返回即关进程
    (实测 Connection closed)。因此由一个永不返回的 _session_main 协程持有
    整个会话生命周期, 其余调用用 run_coroutine_threadsafe 投递进同一 loop。
    """

    def __init__(self, server_script: str, server_name: str = "mcp-server"):
        self._ready = threading.Event()
        self._stop = None
        self._loop = asyncio.new_event_loop()
        self._session = None
        self._server_script = str(Path(server_script).resolve())
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _async(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=60)

    def start(self):
        self._stop = asyncio.Event()
        asyncio.run_coroutine_threadsafe(self._session_main(), self._loop)
        if not self._ready.wait(timeout=30):
            raise RuntimeError("MCP 会话 30s 未就绪")

    async def _session_main(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=sys_executable(),
                                       args=[self._server_script, "serve"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                self._ready.set()
                await self._stop.wait()  # 保持上下文存活直到 close

    def list_tools(self):
        resp = self._async(self._session.list_tools())
        return [(t.name, t.description or "", t.input_schema) for t in resp.tools]

    def call(self, name: str, args: dict) -> str:
        r = self._async(self._session.call_tool(name, args or {}))
        parts = [c.text for c in r.content if getattr(c, "text", None)]
        return "\n".join(parts) or "(空结果)"

    def close(self):
        try:
            self._async(self._stop.set())
        except Exception:
            pass  # 会话可能已断; 进程随 daemon 线程回收
        self._loop.call_soon_threadsafe(self._loop.stop)


def sys_executable():
    import sys
    return sys.executable


def mcp_tools(bridge: MCPBridge) -> dict:
    """MCP 工具 → mh 工具表条目(未包权限门)。"""
    out = {}
    for name, desc, schema in bridge.list_tools():
        def fn(_n=name, _b=bridge, **args):
            return _b.call(_n, args)
        fn.__name__ = name
        out[name] = {
            "desc": desc,
            "schema": {"type": "function", "function": {
                "name": name,
                "description": f"[MCP] {desc}",
                "parameters": schema}},
            "fn": fn}
    return out
