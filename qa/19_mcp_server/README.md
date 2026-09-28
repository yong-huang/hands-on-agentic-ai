# 19 · MCP Server 实战

> 用官方 Python 库写一个书店库存 MCP（Model Context Protocol，模型上下文协议）Server（mcp 2.x）：3 个 Tools（查询/下单/统计）+ 1 个 Resource（库存只读视图）+ 1 个 Prompt（订单话术模板），stdio（标准输入输出）传输，客户端连通测试列出并调用全部能力。读完你能说清 MCP 三种原语的分工，并照着写出最小可用的 Server。

## Background

在 MCP 出现之前，把"查库存、下订单"这类工具接给 AI 应用用，靠的是应用自己写胶水代码：把工具的名称和参数说明拼进提示词，再手工解析模型输出、调用真实函数。

痛点在于这套接法每个客户端各不相同。一家公司有 5 个内部工具、要接 3 个不同的 AI 客户端（比如 IDE 助手和桌面聊天应用），就得写 15 份互不通用的适配代码；任何一端升级，相关格子都要重写。

MCP（Model Context Protocol，模型上下文协议）因此应运而生：2024 年 11 月由 Anthropic 开源的开放协议，把上面的 M×N 适配矩阵变成 M+N——工具方实现一次 Server，"怎么发现、怎么调用"交给协议统一约定。

## What

MCP 是一个约定"AI 应用如何使用外部工具与数据"的开放协议：发现（list）、调用、传输都有标准格式。它把能力分成三种原语（primitive，协议里最基础的能力单元），三者的控制方不同：

| 原语 | 控制方 | 用途 | 本例 |
|:--|:--|:--|:--|
| Tools | 模型决定调用 | 动作/查询 | 下单、查库存、统计 |
| Resources | 应用决定拉取 | 只读数据视图 | 库存表 |
| Prompts | 用户/应用选择 | 可复用话术模板 | 订单处理模板 |

心智模型一句话：**MCP 是工具接入协议层，FC 是模型能力层——正交，可叠加。** FC（Function Calling，函数调用）指模型直接生成"该调哪个工具、参数是什么"的能力；MCP 则约定这些工具如何被发现和传输。同一套工具可以既走 MCP 接入、又由模型用 FC 调用。

可以把 MCP 想象成 AI 应用的 USB-C 接口：设备厂商做一次接口，任何符合标准的线都能插。但和 USB-C 不同的是，USB-C 只保证物理连通，MCP 还约定了"对方有什么能力、怎么调"的语义（list 与 call 的消息格式）。

## When to Use

典型场景，判断依据是"同一套能力要不要跨客户端复用"：

- 给多个 AI 客户端（IDE 助手、桌面应用）接同一批内部系统时——Server 写一次，各客户端都能 list 到并调用。
- 想把只读数据（库存表、配置）作为视图供应用侧拉取展示，而不占用模型的调用额度时——用 Resource。
- 团队要沉淀可复用的话术模板（客服口径、订单处理流程）供用户一键选用时——用 Prompt。

何时不用：只服务单一模型、工具只有两三个的原型，直接用框架自带的 Function Calling 更省事；引入 MCP Server 要多维护一个进程和一层协议依赖。

| 方案 | 差异 | 什么时候选它 |
|:--|:--|:--|
| 框架自带 Function Calling | 工具格式由各框架定义，换客户端要重写接入 | 单一框架、少量工具的原型 |
| 自研 HTTP API + 手写适配 | 完全自定义，但发现、调用、传输都要自己定 | 已有成熟后端 API 且只有一个消费端 |
| MCP Server | 一次实现，任何支持 MCP 的客户端可发现并调用 | 同一套能力要被多客户端复用 |

## Quick Start

前置条件：Python 3.10+，并安装官方库 mcp：`pip install "mcp>=2.2"`（本实验在 mcp 2.2.0 实测）。

```bash
cd qa/19_mcp_server
python3 mcp_server.py serve    # 起服务器 (stdio, 通常由客户端拉起)
python3 mcp_server.py test     # 连通测试: 子进程拉起 server + ClientSession
```

连通验证用 `test` 子命令：它会以子进程方式拉起 server，再模拟一个客户端逐项检查。实测（mcp 2.2.0）结果：

- 协议握手成功，客户端 list 到全部能力：`Tools(3): query_stock/place_order/sales_stats`、`Resources(1): inventory://view`、`Prompts(1): order_help`；
- 逐个调用验证业务闭环：下单 A1×2 → 订单 O001 ¥178 → 库存 12→10 → 统计口径同步；
- 零库存下单返回结构化错误（JSON 形式的"库存不足"信息，而非进程崩溃）；
- resource 只读视图与 prompt 模板读取正常。

诚实预期：`test` 会完整跑完上述清单；直接运行 `serve` 时终端没有输出、看似卡住，属于正常现象（原因见 Pitfalls 第 2 条）。

## How It Works

机制分两半：能力如何注册，以及客户端如何连上来。

**第一步：用装饰器注册能力。** 装饰器（decorator，Python 里写在函数定义上方、以 `@` 开头的语法）在这里的用途是把普通函数登记进 Server 的能力清单。以本例的查询工具为例：

```python
@mcp.tool()
def query_stock(sku: str) -> str:
    """查询图书库存与价格"""
```

这段在做什么：`@mcp.tool()` 把函数名、参数类型签名和 docstring（函数首行的说明文字）注册为一个 Tool——客户端 list 到的 `query_stock` 就来自这里。

同类注册还有 `@mcp.resource('inventory://view')`（URI，统一资源标识符，类似网址的寻址串）和 `@mcp.prompt()`，正好对应 What 节表格里的三种原语。

**第二步：stdio 传输与测试链路。** stdio 传输指 Server 通过标准输入/输出两条流收发 JSON-RPC 消息（JSON-RPC，一种用 JSON 文本表达"远程过程调用"的消息格式）。`test` 子命令的流程是：

1. 用 `StdioServerParameters` 把 `mcp_server.py serve` 拉起为子进程；
2. 建立 `ClientSession`（客户端会话对象），先 `initialize()` 握手（通信双方交换版本与能力信息）；
3. 依次 `list_tools()` / `list_resources()` / `list_prompts()` 列能力，再 `call_tool` / `read_resource` / `get_prompt` 逐个调用。

你在实测里看到的"握手成功"与能力清单，分别来自第 2、3 步；零库存下单返回的"库存不足: 需要 X, 现有 Y"则来自 `place_order` 里的 JSON 返回——错误也是协议内的正常消息，客户端能读到并决定下一步。

## Pitfalls & Q&A

**坑 1：照旧教程写 `FastMCP`，启动报 ImportError。**

- 现象：`from mcp.server.fastmcp import FastMCP` 在 mcp 2.x 下找不到模块。
- 原因：mcp 2.x 已把 FastMCP 改名 MCPServer（`from mcp.server.mcpserver import MCPServer`），而网上大量教程还在用旧名。
- 解法：改用新名导入；装饰器用法不变。

**坑 2：手动运行 `serve` 后终端像卡死。**

- 现象：`python3 mcp_server.py serve` 执行后没有任何输出。
- 原因：stdio 传输靠标准输入/输出与客户端通信，通常由客户端拉起并接管这两条流；人工运行时它在等待输入。
- 解法：连通验证改用 `test` 子命令。

**Q1：什么时候用 Resources 而不是 Tools？**

看控制方：数据是应用该主动拉取的只读视图（库存表、配置）→ Resources；模型需要决策"调不调、怎么调"的动作与查询 → Tools。把只读数据包成 Tools 会把决策权错交给模型——本例把库存表做成 Resource、下单做成 Tool，正是按这条线划分的。
