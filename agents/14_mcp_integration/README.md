# 14 · MCP 协议集成：工具的"USB 接口"

> 项目 12 的 Registry 再优雅，工具也只能和 Agent 活在同一个进程里。MCP
> （Model Context Protocol）把工具搬进独立进程：Agent 通过 JSON-RPC 2.0 与
> Server 握手、动态发现工具、远程调用——**不写一行工具代码，接上就有四个
> 文件工具可用**。本篇用 70 行手写一个 MCP Client，讲透三阶段握手。

## 1. 为什么需要它

Registry 的工具与 Agent 同生共死：换语言要重写、跨进程要 RPC、第三方发布
的工具没有统一接入方式。MCP 是 Anthropic 发起的开放标准，把"工具提供"从
Agent 中剥离：任何语言写的 MCP Server，任何支持 MCP 的 Agent 都能即插即用。
生态里现成的 Server（文件系统、数据库、浏览器、GitHub……）可以直接挂进你的
Agent。**这是 2025 年以来 Agent 工具生态最重要的事实标准。**

## 2. 总览：核心机制一图看懂

![MCP 握手与工具调用时序](images/mcp_handshake.sequence.svg)

**怎么看这张图**：前段是三阶段握手——`initialize`（带协议版本与能力协商）
→ Server 回 `serverInfo` → 客户端补发 `notifications/initialized`（无 id
的通知）；中段 `tools/list` 拿到工具清单与 inputSchema，转换成 Ollama 的
function schema 喂给模型；后段模型点名工具，`tools/call` 到 Server，
实际文件操作发生在 `workspace/` 允许目录内。

心智模型一句话：**MCP = 工具界的 USB：统一接口，插上即被发现和使用。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/14_mcp_integration/images/mcp_handshake.sequence.html)（或本地打开 [`images/mcp_handshake.sequence.html`](images/mcp_handshake.sequence.html)）。

## 3. 快速开始

```bash
cd agents/14_mcp_integration
python mcp_integration.py --demo       # 离线：完整模拟握手/发现/调用（无需 npx）
python mcp_integration.py "列出当前目录的文件"   # 真实模式：npx 拉起 filesystem server
```

真实模式依赖 npx 与 Ollama。首次运行 npx 会下载 `@modelcontextprotocol/
server-filesystem` 包，**可能耗时 30 秒以上**（客户端已带超时等待，属预期
行为）。预期输出：`Found N tools:`（N 随 Server 版本浮动，当前为 14：
read_text_file / list_directory / search_files / write_file 等，工具数量
以实际运行为准），随后模型调用 `list_directory` 并总结结果。

**诚实预期**：Server 只允许访问 `workspace/` 目录（启动参数指定）；问
"当前目录"时模型传入 `.`，实际列出的是允许目录内容。

## 4. 核心概念

### 4.1 JSON-RPC 2.0 over stdio

```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize",
 "params": {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
            "clientInfo": {"name": "agent-mcp-client", "version": "0.1.0"}}}
```

传输就是"一行 JSON 进、一行 JSON 出"：请求带 `id`，**通知（notification）
不带 `id`**——这就是握手要多发一条 `notifications/initialized` 的原因：
它只是告知，不等回复。帧边界 = 换行符，`readline()` 即可解析。

### 4.2 三阶段握手（合规关键）

| 步骤 | 方向 | 说明 |
| :--- | :--- | :--- |
| 1. initialize | C→S / S→C | 协商协议版本与能力，Server 回 serverInfo |
| 2. notifications/initialized | C→S | 无 id 通知，宣告握手完成 |
| 3. tools/* | C→S | 之后才能发现/调用工具 |

跳过第 2 步直接调工具，多数 Server 会拒绝——**握手未完成不算 ready**。

### 4.3 工具发现与 schema 适配

`tools/list` 返回的工具带 `inputSchema`（JSON Schema），`get_tools_schema()`
一个循环把它填进 Ollama function 的 `parameters`——**协议适配层**让任意
MCP Server 的工具直接接入项目 11 的 Function Calling 循环，Agent 代码零改动。

### 4.4 安全模型：允许目录

filesystem Server 的权限边界由**启动参数**决定（`mcp-server-filesystem
<dir>`），模型传什么都逃不出白名单——这和项目 09 的 `_safe_path` 是同一个
思想，只是边界划在了独立进程里。

**本篇修复的真实坑**：包名是 `@modelcontextprotocol/server-filesystem`
（旧名 `@anthropic-ai/...` 已废弃，npx 解析失败会让握手拿到空响应）；
npx 首次下载远超固定 sleep，读取要带超时重试而不是裸等 1 秒。

## 5. 代码关键部分

```python
def _read_response(self, timeout: float = 90.0) -> str:
    """按行读一条响应；npx 首次拉包可能很慢，select 轮询代替裸 readline。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if self._proc.poll() is not None:
            return ""
        ready, _, _ = select.select([self._proc.stdout], [], [], 1.0)
        if ready:
            line = self._proc.stdout.readline()
            if line.strip():
                return line
    return ""

def call_tool(self, name, arguments):
    resp = self.rpc.send("tools/call", {"name": name, "arguments": arguments})
    texts = [c.get("text", "") for c in resp.get("result", {}).get("content", [])
             if c.get("type") == "text"]
    return {"result": "\n".join(texts)}
```

坑清单：

- Server 起动时间不定（npx 冷缓存），握手读取必须带总超时；
- `tools/list` 的响应可能非常大（十几个工具的 schema 一行 JSON），按行读取
  前不要做小缓冲预设；
- Server 是独立进程，`finally: mcp.disconnect()` 确保不留僵尸进程。

## 6. 文件结构

```
14_mcp_integration/
├── README.md                            # 本篇教程
├── mcp_integration.py                   # 主脚本（约 430 行）：JsonRpcClient + MCPClient + Agent
├── workspace/                           # filesystem Server 的允许目录
└── images/
    ├── mcp_handshake.sequence.json      # 图源：sequence 类型（4 参与方握手时序）
    ├── mcp_handshake.sequence.html      # 交互版架构图
    └── mcp_handshake.sequence.svg       # 双主题矢量图
```

## 7. 面试要点

- **Q: MCP 解决了什么问题？**
  A: 工具与 Agent 的耦合。协议化后工具可跨语言、跨进程复用，第三方 Server
  生态即插即用——类比 USB 之于外设。
- **Q: MCP 握手为什么是三步？**
  A: initialize 协商版本与能力（有 id，有响应）；notifications/initialized
  是无 id 通知宣告就绪；此后 tools/* 才合规。缺第 2 步多数 Server 拒绝服务。
- **Q: MCP 的传输方式有哪些？**
  A: stdio（本地子进程，行分隔 JSON）与 Streamable HTTP（远程服务）；本篇
  用 stdio 实现最小 Client。
- **Q: MCP 工具怎么接入已有 Function Calling Agent？**
  A: `tools/list` 拿 inputSchema → 映射为 API 的 tools 参数；tool_calls 到来
  时转发 `tools/call`。Agent 循环零改动（适配层模式）。
- **Q: MCP 的安全边界在哪里？**
  A: 由 Server 自己实现并暴露给用户确认（如 filesystem 的允许目录参数）。
  Client 侧还应做审批层——这正是下一篇 HITL 的主题。

## 8. 总结

MCP 用"一行 JSON 一条消息"的朴素传输，换来了工具生态的开放标准：三步握手、
动态发现、远程调用。Agent 从"自带工具"进化到"接入工具"。但工具越开放越
需要监管——下一篇给所有工具调用装上分级审批门。
