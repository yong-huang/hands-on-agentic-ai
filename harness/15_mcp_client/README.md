# 15 · MCP 动态工具：外部工具先过权限门

> 外部工具不可直接信——`mh/mcp_client.py` 接入 MCP server（MCP，Model
> Context Protocol：外部程序向模型代理统一提供工具的协议）时，动态发现
> 的每一条工具都先过权限门（工具调用前的拦截审批层，07 的主题）再
> 注册。真机一单完整交易：query_stock 直通、place_order 被拦后脚本
> 批准、订单 O001 落地、audit.log 留痕。读完本篇你能复述"发现→注册→
> 包门"全链路，以及两个经典踩坑。

## Background

要给模型代理接外部能力，此前的做法是把工具一个个手写进工具表（05 的
工具契约）：每个工具的描述、参数说明、执行函数都由本仓库自己实现。
内部工具可以这样养，第三方能力却没法一个个手写适配。

MCP 改变了供给方式：任何程序实现这个协议，代理就能"即插即用"它的
工具。但便利的另一面是**外部能力即插即用地获得副作用权**（改变外部
状态的能力：下单、删数据、发消息）。

一个恶意 server 的 `delete_everything` 工具若直通注册表，前面 6 个
实验筑起的防线全部白搭。Salesforce 提出的权限五步（拦截→验证→执行→
净化→反馈）在 MCP 场景不是可选优化，而是生存条件。15 实验因此成为
02 解剖图"扩展机制"的最后一块：动态注册与治理打包在一起交付。

## What

MCP 动态工具接入分三块：左侧是外部进程（书店 server，stdio 传输——
通过标准输入输出与子进程通信）；中间是 `mh` 工具表，`list_tools` 发现
的每个工具经 schema（参数格式说明）映射注册，**注册即包门**。

右侧是治理层：query_stock 走 allow（规则命中即直接放行）直通，
place_order 命中 ask（挂起、等人工批准），全部判定写进 audit.log
（审计日志）。

心智模型一句话：**外部工具进注册表的第一件事，是领一张权限门的门票。**
可以把权限门想成游乐园闸机，但和闸机不同的是：闸机验一次全园通用，
这里按副作用分级——只读免票直通，写操作要人工签字放行。

## When to Use

典型场景：

- 接第三方只读数据源：行情、库存、文档检索一类查询工具，发现后
  allow 直通即可。
- 接有副作用的操作：下单、发消息、删资源——注册后全部先经 ask 等
  人工批准。
- 用同一套治理管多个 server：不管外部程序是谁，注册与审批走同一条
  路，审计口径统一。

何时不用：工具全部自研且数量固定时，静态手写进工具表（05 的做法）
更简单，不值得引入外部 server 进程与协议开销；一次性 demo 里在提示
词里教模型直接调 API 也行，但没有契约校验与治理。

同类方案对比：

| 方案 | 差异 | 什么时候选它 |
|:--|:--|:--|
| 静态注册（05 的做法） | 工具手写进表，无发现协议 | 自研工具、数量固定 |
| MCP 动态接入（本篇） | 运行时发现→注册→包门 | 第三方能力、会增减 |
| 提示词里教模型调 HTTP API | 无契约校验、无治理 | 一次性演示 |

## Quick Start

前置条件：Python 3 环境；真机运行需要一个可用的模型接入（mh 经
LLM_BASE_URL/LLM_MODEL 环境变量连接模型服务，默认本地 Ollama）；
本 demo 依赖 qa/19 的夹具（预先备好的测试支撑环境），运行中会拉起
一个外部书店 server 子进程。

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

诚实预期：这是一单完整交易验收，需要夹具与外部 server 都在位；ask
环节的批准来自脚本自动输入 `y`，生产环境这一步由人来按。

实现代码：

```python
bridge = MCPBridge(server_script); bridge.start()   # 常驻会话(后台线程)
mcp_tools(bridge)                                   # 发现→注册(未包门)
wrap_tool(entry, gate, name=name)                   # 逐个包权限门
bridge.call(name, args)                             # 实际执行(经 MCP)
```

## How It Works

四行代码对应四步：`bridge.start()` 在后台线程里与 server 建立常驻
会话；`mcp_tools(bridge)` 调 `list_tools` 发现工具并注册——注意此时
**未包门**。

接着 `wrap_tool` 逐个把权限门包上去；真正执行走
`bridge.call(name, args)`，经 MCP 发给 server。

输出里的 ①②③ 三条，分别对应发现、拦截批准、审计留痕这三步。

**schema 是协议，不是文档。**MCP 的 `inputSchema` 直接映射为 OpenAI
function calling（让模型以结构化 JSON 参数调用函数的接口格式）格式
——外部工具的参数契约无缝进入 05 的校验体系。

这就是 MCP 的价值：**工具的发现、描述、调用、治理全部走同一套协议**，
不用为每个 server 手写适配。

权限匹配串也做了泛化：07 的权限门按 `args.command` 匹配（bash 语义）；
MCP 工具没有 command。`wrap_tool` 泛化为：**优先 command，否则"工具名
+ 参数 JSON"**——规则 `place_order*` 两种工具通吃。

## Pitfalls & Q&A

踩坑清单：

- **anyio 上下文生命周期**

  - 现象：第一版桥把 `stdio_client(...).__aenter__()` 的结果存起来跨
    协程（可暂停恢复的函数）使用，报 **Connection closed**。

  - 原因：anyio（Python 异步库）的异步上下文（`async with` 建立并
    配对释放的运行环境）绑定在创建它的任务上，协程返回即触发清理、
    子进程被收掉。

  - 解法：后台线程跑独立 event loop（事件循环，单线程内调度异步任务
    的机制），**一个永不返回的 `_session_main` 协程持有整个会话生命
    周期**，其余调用用 `run_coroutine_threadsafe` 投递进同一 loop。

    这个坑官方示例不会告诉你（示例都在单个 `async with` 里）。

- **第一版权限匹配翻车**

  - 现象：query_stock 被兜底 deny（没有规则命中时的默认拒绝）拦截，
    模型随即**暂停了下单**（"信息不全不执行交易"）。

  - 原因：治理过严，匹配串泛化不到位。

  - 解法：换用上文"优先 command，否则工具名 + 参数 JSON"的匹配串。
    治理过严时 agent 表现出的克制本身也是 harness 质量的证据（07
    治理信息回喂的行为红利在外部工具场景再次应验）。

Q&A：

**Q1: 为什么 place_order 是 ask 而 query_stock 是 allow？**

判定标准是**副作用方向**：只读放行、写操作挂起——02 解剖图"执行前
拦截"的位置原则，加上最小权限（只给完成任务所必需的权限）的粒度原则。

**Q2: ask 批准后呢？**

批准是一次性票据（本实现），生产可加 TTL（time-to-live，超过时限自动
失效）/次数白名单；audit.log 记录的是"谁在何时批准了什么"（本 demo
是脚本，生产是人）。

**Q3: MCP 工具要不要过 05 契约校验？**

schema 已经是 MCP 侧的契约，mh 侧再校验是双保险；对不可信 server 反而
更要——server 的 schema 可能撒谎。
