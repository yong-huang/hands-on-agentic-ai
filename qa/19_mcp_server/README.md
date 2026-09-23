# 19 · MCP Server 实战

> 用官方 Python SDK 写书店库存 Server（mcp 2.x，MCPServer）：3 Tools
> （查询/下单/统计）+ 1 Resource（库存只读视图）+ 1 Prompt（订单话术
> 模板），stdio 传输，客户端连通测试列出并调用全部能力。

## What

MCP 把"工具方实现一次 Server"变成"任何支持 MCP 的模型/客户端都能用"——
发现（list）、调用、传输全有协议约定。三种原语的控制方不同：

| 原语 | 控制方 | 用途 | 本例 |
|:--|:--|:--|:--|
| Tools | 模型决定调用 | 动作/查询 | 下单、查库存、统计 |
| Resources | 应用决定拉取 | 只读数据视图 | 库存表 |
| Prompts | 用户/应用选择 | 可复用话术模板 | 订单处理模板 |

心智模型一句话：**MCP 是工具接入协议层，FC 是模型能力层——正交，
可叠加。**

## Why

没有协议时每个工具要为每个模型/框架手写适配（M×N）；MCP 把它变成
M+N：工具方实现一次 Server，接入问题交给协议。

## How

```bash
cd qa/19_mcp_server
python3 mcp_server.py serve    # 起服务器 (stdio, 通常由客户端拉起)
python3 mcp_server.py test     # 连通测试: 子进程拉起 server + ClientSession
```

实测（mcp 2.2.0）：协议握手成功，客户端 list 到全部能力
`Tools(3): query_stock/place_order/sales_stats`、
`Resources(1): inventory://view`、`Prompts(1): order_help`；
逐个调用验证业务闭环：下单 A1×2 → 订单 O001 ¥178 → 库存 12→10 →
统计口径同步；零库存下单返回结构化错误；resource 只读视图与 prompt
模板读取正常。

## Deep Dive

**MCP 与 Function Calling 各管一层**：FC 是模型能力层（模型吐参数），
MCP 是工具接入协议层（参数如何被发现与传输）——同一套工具可以既走
MCP 接入又用 FC 调用。三原语的选择本质是"谁控制"：模型该决策的做
Tools，应用该主动拉的做 Resources，用户该选的做 Prompts。

踩坑清单：

- **mcp 2.x 已把 FastMCP 改名 MCPServer**（`from mcp.server.mcpserver
  import MCPServer`），装饰器用法不变——网上大量教程还在用旧名。

## Q&A

**Q1: 什么时候用 Resources 而不是 Tools？**

看控制方：数据是应用该主动拉取的只读视图（库存表、配置）→ Resources；
模型需要决策"调不调、怎么调"的动作与查询 → Tools。把只读数据包成
Tools 会把决策权错交给模型。
