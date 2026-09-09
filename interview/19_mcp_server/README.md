# 19 · MCP Server 实战

> 覆盖面试题：MCP 解决了什么问题？三种原语（Resources/Tools/Prompts）？
> 如何设计一个 MCP Server？
> 用官方 Python SDK 写书店库存 Server（mcp 2.x，MCPServer）：3 Tools
> （查询/下单/统计）+ 1 Resource（库存只读视图）+ 1 Prompt（订单话术
> 模板），stdio 传输，客户端连通测试列出并调用全部能力。

## 1. 运行与实测

```bash
python mcp_server.py serve    # 起服务器 (stdio, 通常由客户端拉起)
python mcp_server.py test     # 连通测试: 子进程拉起 server + ClientSession
```

实测（2026-09-09，mcp 2.2.0）：协议握手成功，客户端 list 到全部能力
`Tools(3): query_stock/place_order/sales_stats`、
`Resources(1): inventory://view`、`Prompts(1): order_help`；
逐个调用验证业务闭环：下单 A1×2 → 订单 O001 ¥178 → 库存 12→10 →
统计口径同步；零库存下单返回结构化错误；resource 只读视图与 prompt
模板读取正常。

## 2. 三种原语怎么选

| 原语 | 控制方 | 用途 | 本例 |
|:--|:--|:--|:--|
| Tools | 模型决定调用 | 动作/查询 | 下单、查库存、统计 |
| Resources | 应用决定拉取 | 只读数据视图 | 库存表 |
| Prompts | 用户/应用选择 | 可复用话术模板 | 订单处理模板 |

## 3. 面试要点

- MCP 解决的问题：M×N 集成变 M+N——工具方实现一次 Server，任何
  支持 MCP 的模型/客户端都能用；发现(list)、调用、传输全有协议约定。
- MCP vs Function Calling：FC 是模型能力层（模型吐参数），MCP 是
  工具接入协议层（参数如何被发现与传输）——正交，可叠加。
- 注意：mcp 2.x 已把 FastMCP 改名 MCPServer（`from mcp.server.mcpserver
  import MCPServer`），装饰器用法不变。

## 4. 文件结构

```
interview/19_mcp_server/
├── README.md            # 本篇
└── mcp_server.py        # Server(3T+1R+1P) + 客户端连通测试（约 150 行）
```
