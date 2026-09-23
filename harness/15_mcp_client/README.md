# 15 · MCP 动态工具：外部工具先过权限门

> `mh/mcp_client.py` 把外部 MCP server 接进 `mh/` 工具表协议：启动外部
> 书店 server、动态发现 3 个工具、映射 schema 注册——然后**每一条都先过
> 07 权限门**。真机一单完整交易：query_stock 直通、place_order 被 ask
> 拦截 → 脚本批准 → 订单 O001 落地 → audit.log 留痕。外部工具不可直接信，
> 这是信任边界，不是口号。

## What

MCP 动态工具接入：左侧外部进程（书店 server，stdio 传输），中间 `mh`
工具表——`list_tools` 发现的每个工具经 schema 映射注册，**注册即包门**；
右侧治理层：query_stock 走 allow 直通，place_order 命中 ask 挂起等人工，
全部判定写 audit.log。

心智模型一句话：**外部工具进注册表的第一件事，是领一张权限门的门票。**

## Why

MCP 让 agent 能"即插即用"外部能力，也意味着**外部能力即插即用地获得
副作用权**。Salesforce 权限五步（拦截→验证→执行→净化→反馈）在 MCP 场景
不是可选优化而是生存条件——一个恶意 server 的 `delete_everything` 工具
若直通注册表，前面 6 个实验的防线全部白搭。本篇是 02 解剖图"扩展机制"
的最后一块：动态注册 + 治理打包。

## How

```bash
cd harness/15_mcp_client
python3 demo.py    # 真机: 发现→治理调用→交易验收（依赖 qa/19 夹具）
```

真机实测：

```text
① MCP 发现 3 个工具: ['query_stock', 'place_order', 'sales_stats'] ✅
② place_order 被 ask 拦截→批准→成功 ✅
   [ask] place_order {"sku":"A1","qty":2} → y
   place_order → {"ok":true,"order_id":"O001","amount":178.0}
③ audit.log MCP 记录: ✅ (2 条)
最终回答: 交易完成：订单号 O001，购买《深入理解TCP/IP》2 本，金额 178.0 元
```

实现代码：

```python
bridge = MCPBridge(server_script); bridge.start()   # 常驻会话(后台线程)
mcp_tools(bridge)                                   # 发现→注册(未包门)
wrap_tool(entry, gate, name=name)                   # 逐个包权限门
bridge.call(name, args)                             # 实际执行(经 MCP)
```

权限匹配串的泛化：07 的权限门按 `args.command` 匹配（bash 语义）；MCP
工具没有 command。`wrap_tool` 泛化为：**优先 command，否则"工具名 + 参数
JSON"**——规则 `place_order*` 两种工具通吃。

## Deep Dive

**schema 是协议，不是文档。**MCP 的 `inputSchema` 直接映射为 OpenAI
function calling 格式——外部工具的参数契约无缝进入 05 的校验体系。这就是
MCP 的价值：**工具的发现、描述、调用、治理全部走同一套协议**，不用为每个
server 手写适配。

踩坑清单：

- **anyio 上下文生命周期**：第一版桥把 `stdio_client(...).__aenter__()`
  的结果存起来跨协程用——**Connection closed**。anyio 的异步上下文绑定在
  创建它的任务上，协程返回即触发清理、子进程被收掉。解法是经典模式：后台
  线程跑独立 event loop，**一个永不返回的 `_session_main` 协程持有整个
  会话生命周期**，其余调用用 `run_coroutine_threadsafe` 投递进同一 loop。
  这个坑官方示例不会告诉你（示例都在单个 `async with` 里）。
- **第一版权限匹配翻车**：query_stock 被兜底 deny 拦截（匹配串没对上
  规则），模型很聪明地**暂停了下单**（"信息不全不执行交易"）——治理过严
  时 agent 表现出的克制本身也是 harness 质量的证据（07 治理信息回喂的
  行为红利在外部工具场景再次应验）。

## Q&A

**Q1: 为什么 place_order 是 ask 而 query_stock 是 allow？**

判定标准是**副作用方向**：只读放行、写操作挂起——02 解剖图"执行前拦截"
的位置原则，加上最小权限的粒度原则。

**Q2: ask 批准后呢？**

批准是一次性票据（本实现），生产可加 TTL/次数白名单；audit.log 记录的是
"谁在何时批准了什么"（本 demo 是脚本，生产是人）。

**Q3: MCP 工具要不要过 05 契约校验？**

schema 已经是 MCP 侧的契约，mh 侧再校验是双保险；对不可信 server 反而
更要——server 的 schema 可能撒谎。
