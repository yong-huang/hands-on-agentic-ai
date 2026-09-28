# 14 · MCP 协议集成：工具的"USB 接口"

> MCP（Model Context Protocol）把工具搬进独立进程：Agent 通过 JSON-RPC 2.0
> 与 Server 握手、动态发现工具、远程调用——**不写一行工具代码，接上就有
> 四个文件工具可用**。本篇用 70 行手写一个 MCP Client，讲透三阶段握手。

## Background

在没有 MCP 之前，工具通常注册在 Agent 进程内部：一张 Registry（工具
注册表，"工具名 → 函数"的进程内字典），工具函数与 Agent 代码同生共死。

这种形态在三件事上撞墙：想跨语言复用就得重写，或者自己搭 RPC（远程
过程调用）通道；第三方发布的工具没有统一接入方式，每接一个都要手写
一段适配代码；工具崩溃会连带 Agent 主进程一起挂。

MCP 由 Anthropic 发起，把"工具提供"从 Agent 中剥离成独立进程，并规定
统一的接入协议：任何语言写的 MCP Server，任何支持 MCP 的 Agent 都能
即插即用。

生态里现成的 Server（文件系统、数据库、浏览器、GitHub……）
可以直接挂进你的 Agent——这是 2025 年以来 Agent 工具生态最重要的事实
标准。

## What

MCP（Model Context Protocol，模型上下文协议）是一种开放协议标准，规定
Agent 端与工具进程端如何握手、如何发现工具、如何调用工具。两端角色
固定：

| 部件 | 职责 |
| :--- | :--- |
| Client（Agent 侧） | 发起握手、发现工具、代模型发起调用 |
| Server（工具侧） | 独立进程，暴露工具清单并执行工具 |
| JSON-RPC 2.0 | 双方共用的消息格式（以 JSON 编码的远程调用协议） |
| stdio | 本地传输通道：子进程的标准输入/输出 |

类比：可以把 MCP 想象成 USB 接口——统一接口，设备（工具）插上即被
发现和使用。但和 USB 不同的是，MCP 连上后要先完成一次握手协商，双方
确认协议版本与能力之后才会交换数据。

心智模型一句话：**MCP = 工具界的 USB：统一接口，插上即被发现和使用。**

## When to Use

判断标准：工具要不要跨进程、跨语言、跨团队复用。

典型场景：

- 想给 Agent 接现成生态能力时（文件系统、数据库、浏览器、GitHub），
  不自己写工具代码，挂一个现成 MCP Server；
- 团队里多个 Agent、多种语言要共享同一批工具，工具只维护一份；
- 工具需要与主进程隔离时（权限边界独立、崩溃不连坐）。

何时不用：

- 只有几个简单本地工具、单一语言单一 Agent：进程内注册表（12 实验
  的 Registry 主题）更简单，没有进程与协议开销；
- 工具集固定且全部自己维护，直接手写 Function Calling（函数调用，模型点名要用哪个工具的机制）工具即可。

同类方案对比：

| 方案 | 差异 | 什么时候选它 |
| :--- | :--- | :--- |
| 进程内工具注册表 | 工具与 Agent 同进程同语言，零协议开销 | 少量本地工具、单人项目 |
| 手写 Function Calling 工具 | 每个工具自己定义参数结构（schema）与执行体 | 固定的小工具集 |
| MCP（本实验） | 开放标准、独立进程、生态现成 Server | 接第三方工具或多 Agent 复用 |

## Quick Start

前置条件：真实模式需要 npx（Node.js 自带的包执行命令）与 Ollama（本地
大模型运行环境）；`--demo` 离线完整模拟握手/发现/调用，两者都不需要。

```bash
cd agents/14_mcp_integration
python mcp_integration.py --demo       # 离线：完整模拟握手/发现/调用（无需 npx）
python mcp_integration.py "列出当前目录的文件"   # 真实模式：npx 拉起 filesystem server
```

真实模式首次运行时，npx 会下载
`@modelcontextprotocol/server-filesystem` 包，**可能耗时 30 秒以上**
（客户端已带超时等待，属预期行为）。

预期输出：`Found N tools:`（N 随 Server 版本浮动，当前为 14：
read_text_file / list_directory / search_files / write_file 等，工具数量
以实际运行为准），随后模型调用 `list_directory` 并总结结果。

**诚实预期**：Server 只允许访问 `workspace/` 目录（启动参数指定）；问
"当前目录"时模型传入 `.`，实际列出的是允许目录内容。

## How It Works

### 握手时序与消息格式

一条完整的交互时序，分握手与工具两个阶段。握手：`initialize`（带协议
版本与能力协商）→ Server 回 `serverInfo` → 客户端补发
`notifications/initialized`（无 id 的通知）。

工具：`tools/list` 拿到工具清单与 inputSchema（JSON Schema，描述工具
参数结构的规范），转换成 Ollama 的 function schema 喂给模型；模型点名
工具时 `tools/call` 到 Server，实际文件操作发生在 `workspace/` 允许
目录内。

传输是 JSON-RPC 2.0 over stdio——"一行 JSON 进、一行 JSON 出"：请求带
`id`，**通知（notification）不带 `id`**——这就是握手要多发一条
`notifications/initialized` 的原因：它只是告知，不等回复。

帧边界 = 换行符，`readline()` 即可解析：

```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize",
 "params": {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
            "clientInfo": {"name": "agent-mcp-client", "version": "0.1.0"}}}
```

三阶段握手（合规关键；C = Client 客户端，S = Server 服务端）：

| 步骤 | 方向 | 说明 |
| :--- | :--- | :--- |
| 1. initialize | C→S / S→C | 协商协议版本与能力，Server 回 serverInfo |
| 2. notifications/initialized | C→S | 无 id 通知，宣告握手完成 |
| 3. tools/* | C→S | 之后才能发现/调用工具 |

你在 Quick Start 看到的 `Found N tools:` 就来自 `tools/list` 的返回；模型
调用 `list_directory` 的那一步，走的是 `tools/call`。

工具发现与 schema 适配：`get_tools_schema()` 一个循环把每个工具的
`inputSchema` 填进 Ollama function 的 `parameters`。

**协议适配层**的价值：任意 MCP Server 的工具直接接入 11 实验的
Function Calling 循环，Agent 代码零改动。

### 读取与调用实现

读取与调用的核心实现：

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

`_read_response` 用 `select` 每秒轮询一次并检查总超时，对应上面"首次
下载可能 30 秒以上"的现象——裸 `readline()` 没有超时能力，Server 起不
来时客户端会永久卡死。

### 安全边界：允许目录

filesystem Server 的权限边界由**启动参数**决定
（`mcp-server-filesystem <dir>`），模型传什么都逃不出白名单（仅放行
清单内路径的访问控制）——这和 09 实验的 `_safe_path` 是同一个思想，
只是边界划在了独立进程里。

## Pitfalls & Q&A

踩坑清单（现象 + 原因 + 解法）：

- **握手拿到空响应**。现象：`initialize` 发出后读不到任何返回。原因：
  包名用了已废弃的旧名 `@anthropic-ai/...`，npx 解析失败。解法：用
  `@modelcontextprotocol/server-filesystem`。
- **首次运行卡住不动**。现象：握手长时间无响应。原因：npx 首次下载
  远超固定 sleep，裸等 1 秒不够。解法：读取带总超时轮询（见上面
  `_read_response`），而不是裸等。
- **`tools/list` 响应读不全**。现象：工具清单解析失败。原因：十几个
  工具的 schema 是一行超大 JSON，小缓冲预设装不下。解法：按行读取，
  读取前不做小缓冲预设。
- **脚本退出后进程残留**（僵尸进程——父进程已退出但未被回收的子进程）。
  原因：Server 是独立进程，不会随脚本自动终止。解法：`finally:
  mcp.disconnect()` 确保清理。

**Q1: MCP 握手为什么是三步？**

initialize 协商版本与能力（有 id，有响应）；notifications/initialized 是
无 id 通知宣告就绪；此后 tools/* 才合规。跳过第 2 步直接调工具，多数
Server 会拒绝——**握手未完成不算 ready**。

**Q2: MCP 的传输方式有哪些？**

stdio（本地子进程，行分隔 JSON）与 Streamable HTTP（远程服务）；本篇用
stdio 实现最小 Client。

**Q3: MCP 的安全边界在哪里？**

机制见 How It Works 的允许目录：边界由 Server 自己实现并暴露给用户确认
（如 filesystem 的启动参数）。Client 侧还应做审批层——见 15 实验
（HITL 人工审批主题）。
