# 15 · MCP 动态工具：外部工具先过权限门

> interview/19-20 教了"MCP 是什么、怎么 guard"；本篇把两课接进 `mh/` 的
> 工具表协议：`mh/mcp_client.py` 启动外部书店 MCP server、动态发现 3 个
> 工具、映射 schema 注册——然后**每一条都先过 07 权限门**。真机一单完整
> 交易：query_stock 直通、place_order 被 ask 拦截 → 脚本批准 → 订单 O001
> 落地 → audit.log 留痕。外部工具不可直接信，这是信任边界，不是口号。

## 1. 为什么需要它

MCP 让 agent 能"即插即用"外部能力，也意味着**外部能力即插即用地获得
副作用权**。Salesforce 权限五步（拦截→验证→执行→净化→反馈）在 MCP 场景
不是可选优化而是生存条件——一个恶意 server 的 `delete_everything` 工具
若直通注册表，前面 6 个实验的防线全部白搭。本篇是 02 解剖图"扩展机制"
的最后一块：动态注册 + 治理打包。

## 2. 总览：核心机制一图看懂

![MCP 动态工具](images/mcp_client.workflow.svg)

**怎么看这张图**：左侧外部进程（书店 server，stdio 传输），中间 `mh`
工具表——`list_tools` 发现的每个工具经 schema 映射注册，**注册即包门**；
右侧治理层：query_stock 走 allow 直通，place_order 命中 ask 挂起等人工，
全部判定写 audit.log。

心智模型一句话：**外部工具进注册表的第一件事，是领一张权限门的门票。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/harness/15_mcp_client/images/mcp_client.html)
> （或本地打开 [`images/mcp_client.html`](images/mcp_client.html)）。

## 3. 快速开始

```bash
cd harness/15_mcp_client
python3 demo.py    # 真机: 发现→治理调用→交易验收（依赖 interview/19 夹具）
```

真机实测（2026-09-20，qwen3.8）：

```text
① MCP 发现 3 个工具: ['query_stock', 'place_order', 'sales_stats'] ✅
② place_order 被 ask 拦截→批准→成功 ✅
   [ask] place_order {"sku":"A1","qty":2} → y
   place_order → {"ok":true,"order_id":"O001","amount":178.0}
③ audit.log MCP 记录: ✅ (2 条)
最终回答: 交易完成：订单号 O001，购买《深入理解TCP/IP》2 本，金额 178.0 元
```

## 4. 核心概念

### 4.1 桥接的工程坑：anyio 上下文生命周期

第一版桥把 `stdio_client(...).__aenter__()` 的结果存起来跨协程用——
**Connection closed**。anyio 的异步上下文绑定在创建它的任务上，协程返回
即触发清理、子进程被收掉。解法是经典模式：后台线程跑独立 event loop，
**一个永不返回的 `_session_main` 协程持有整个会话生命周期**，其余调用
用 `run_coroutine_threadsafe` 投递进同一 loop。这个坑 M 蟹官方示例不会
告诉你（示例都在单个 `async with` 里）。

### 4.2 权限匹配串的泛化

07 的权限门按 `args.command` 匹配（bash 语义）；MCP 工具没有 command。
`wrap_tool` 泛化为：**优先 command，否则 "工具名 + 参数 JSON"**——规则
`place_order*` 两种工具通吃。第一版真机翻车现场：query_stock 被兜底
deny 拦截，模型很聪明地**暂停了下单**（"信息不全不执行交易"）——治理
过严时 agent 表现出的克制本身也是 harness 质量的证据。

### 4.3 schema 是协议，不是文档

MCP 的 `inputSchema` 直接映射为 OpenAI function calling 格式——外部工具
的参数契约无缝进入 05 的校验体系。这就是 MCP 的价值：**工具的发现、描述、
调用、治理全部走同一套协议**，不用为每个 server 手写适配。

## 5. 代码关键点

```python
bridge = MCPBridge(server_script); bridge.start()   # 常驻会话(后台线程)
mcp_tools(bridge)                                   # 发现→注册(未包门)
wrap_tool(entry, gate, name=name)                   # 逐个包权限门
bridge.call(name, args)                             # 实际执行(经 MCP)
```

## 6. 文件结构

```
harness/
├── mh/
│   └── mcp_client.py    # ⛓️ 本篇: MCPBridge / mcp_tools
└── 15_mcp_client/
    ├── README.md
    ├── demo.py          # 发现→治理调用→交易验收
    └── images/          # 工作流图三件套
```

## 7. 深入要点

- **为什么 place_order 是 ask 而 query_stock 是 allow？** 判定标准是
  **副作用方向**：只读放行、写操作挂起——02 解剖图"执行前拦截"的位置
  原则，加上最小权限的粒度原则。
- **ask 批准后呢？** 批准是一次性票据（本实现），生产可加 TTL/次数白名单；
  audit.log 记录的是"谁在何时批准了什么"（本 demo 是脚本，生产是人）。
- **MCP 工具要不要过 05 契约校验？** schema 已经是 MCP 侧的契约，mh 侧
  再校验是双保险；对不可信 server 反而更要——server 的 schema 可能撒谎。
- **权限过严模型会怎样？** 本次真机给出了教科书答案：查询被拦后模型
  **主动暂停交易**而非硬闯——治理信息回喂（07）的行为红利在外部工具场景
  再次应验。

## 8. 总结

扩展机制收官：子代理（算力隔离）、Skills（知识注入）、MCP（能力接入），
三者都过同一套治理协议。`mh/` 包 12 个模块，工具表协议完成最终形态：
**契约 → 权限 → hooks → 沙箱，任何来源的工具一视同仁。**下一篇进入
第六阶段：[16_eval](../16_eval/README.md) Harness 评测台——固定任务集
回归，量化从 v0.1 到现在的每一步演进。
