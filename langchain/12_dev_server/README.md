# 12 · 🏁 本地服务化：langgraph dev 与 SDK 总装

> 前十一个实验都在一个进程里跑图；这一篇把它变成服务：`langgraph dev` 加载图后，任何客户端都能通过 HTTP 创建 thread（会话：保存这轮交互的状态）、发起 run（一次执行：从输入跑到产出）、处理中断与恢复。
> 总装图把三个能力合成一个"迷你研究助手"：检索工具（10 的 RAG）、危险工具审批（07 的 HITL）、追踪回调（11 的 trace）；验证脚本用 SDK（`langgraph_sdk`：把服务的 thread/run 接口封装成 Python 可调用函数的官方客户端库）走完"问答 → 中断 → 审批 → 重启后状态仍在"的全流程，零云依赖。
> 读完你能把一个 LangGraph 图部署成本地服务，并用 SDK 编程调用它。

## Background

此前每个实验的用法都是"`python 脚本.py`"：图和调用方在同一个进程，状态活在内存里。一旦要给别人用（前端、另一个服务、同事的脚本），这套就散了——别人没法 import 你的进程。

最直接的补法是拿 FastAPI 把图包一层 HTTP：每来一个请求调一次 `graph.invoke`。但很快会撞上一串基础设施问题：会话状态存哪（不能每次新建图）、并发 run 怎么管、中断了怎么让客户端挂起再恢复、流式怎么推给浏览器。这些和业务无关，却是每个 Agent 服务都要的骨架。

`langgraph dev` 的解法是"图直接当服务跑"：读取 `langgraph.json` 声明的图，自动提供一套标准资源接口（assistant 部署好的图 / thread 会话 / run 一次执行），持久化、中断恢复、流式全部由服务处理。

客户端用 `langgraph_sdk` 以编程方式驱动，不需要知道服务内部。

## What

服务化之后，调用方打交道的对象从"图的 invoke"变成三种资源：

| 资源 | 是什么 | 实验中的用法 |
|:--|:--|:--|
| assistant | 服务加载的一个图（部署单元） | `research_agent`（langgraph.json 声明） |
| thread | 一条会话及其状态（持久化在服务侧） | 问答、删除各建一条 |
| run | 对 thread 的一次执行 | `runs.wait(...)` 同步等待结果 |
| interrupt / resume | run 中途暂停，客户端带决定继续 | 删除请求 → `command={"resume": ...}` |

可以把这套模型想象成"把图变成一个有档案柜的办事大厅"：窗口（assistant）接待，档案（thread）按编号保存，每次办事（run）都有记录；办事员中途要请示（interrupt）时，档案不会丢，客户随时回来接着办（resume）。

但和真实大厅不同的是：**开发态服务只在一台机器上**——`langgraph dev` 是开发/测试用的单机服务，不是生产集群。

`langgraph.json` 就是这个大厅的"窗口清单"，一行声明图的位置：

```json
{ "dependencies": ["."], "graphs": { "research_agent": "./research_agent.py:graph" } }
```

## When to Use

典型场景：

1. 给前端/其他服务提供统一入口：客户端只认 thread/run 协议，不关心图内部。
2. 长等待与人工介入：中断可跨进程、跨天恢复（服务侧持久化）。
3. 多客户端共享一个图：同一份部署被多个会话使用，状态互相隔离。

何时不用：自己一个人跑脚本（直接 `invoke` 更省事）；生产级部署（要 PostgreSQL、鉴权、扩容——`langgraph dev` 之上的平台能力，超出本线零云约束）。

同类方案对比：

| 方案 | 需要自己写什么 | 什么时候选它 |
|:--|:--|:--|
| 进程内 `invoke` | 无 | 单机脚本、批处理 |
| FastAPI 自封装 | 会话存储、并发、SSE（Server-Sent Events：服务器持续单向推送数据给浏览器的 HTTP 协议）、中断协议 | 深度定制接口 |
| `langgraph dev`（本篇） | 一个 `langgraph.json` | 本地开发、测试、演示 |

## Quick Start

以下命令从仓库根目录（clone 后的 `hands-on-agentic-ai/`）执行。

依赖已装在仓库根 `.venv`（含 `langgraph-cli[inmem]`，见 [docs/langchain.md](../../docs/langchain.md) 的「环境配置」节）。

需要本机 Ollama（在本地运行大语言模型的服务）已启动且已拉取 `qwen3.8:latest` 与 `nomic-embed-text`。

```bash
cd langchain/12_dev_server                 # 在仓库根目录执行
source ../../.venv/bin/activate            # 也可直接用 ../../.venv/bin/python
python3 dev_server.py                      # 自动：起服务 → SDK 全流程 → 重启验证 → 停服务
```

脚本会占用本地 `:2030` 端口；重复运行前它会自动清掉上一轮的 trace、审计文件与 `.langgraph_api/` 持久化残留。若上次异常退出留下服务，先 `pkill -f "langgraph dev"`。

真实输出（节选：省略分隔线，以空行代替；本机绝对路径缩写为 …）：

```text
[12] 本地服务化总装：langgraph dev + SDK（真机，零云依赖）

[1] 启动本地服务（无云 key）
  /ok 存活；日志: /var/folders/.../langchain12_server.log
  ✅ langgraph dev 本地起服务成功且无需云 key

[2] SDK 场景：检索问答 + 危险工具审批
  检索问答: 根据仓库文档，**不需要云 key 也能本地起服务**：

- 官方文档称 `langgraph dev` 需要免费的 LangSmith key；
- 但实测
  ✅ 检索工具被调用且答案含正确来源与结论
  删除请求中断: True
  ✅ 危险工具执行前中断（中断载荷含 delete_note）
  approve 后审计文件: 'old-note.md' | 最终回复: 已删除笔记 old-note.md。
  ✅ approve 后工具才执行（审计文件取证）

[3] 追踪回调 JSONL
  事件数: 16，类型: ['llm_end', 'llm_start', 'tool_end', 'tool_start']
  ✅ llm 与工具事件均落盘 JSONL

[4] 重启服务：thread 状态仍在
  等待 dev 持久化刷盘（约 8 秒）…
  ✅ 服务已停止
  重启后同 thread 快照末条: 根据仓库文档，**不需要云 key 也能本地起服务**：

- 官方文档称 `langgraph dev` 需要免费的 
  ✅ 重启后同 thread 状态仍可查（平台持久化）

验收: 7/7 通过 ✅
```

诚实预期：整轮约 40-60 秒（服务两次启动 + 三次 run 交互，实测 5 次模型调用）；服务日志在系统临时目录（脚本输出路径）。

dev 服务偶发内部错误时重跑一次即可（脚本会先清理残留状态）。检索索引在服务进程内首次调用时构建（约 3 秒）。本实验没有 `--demo`——没有服务就没有可验的东西。退出码：0 通过，1 失败或端口被占用。

## How It Works

### 图入口：三个能力合一

`research_agent.py` 用 03 的 `create_agent` 组装，再叠三层能力。

第一层是检索工具：复用 10 的切分 + 嵌入 + Chroma（懒加载，避免服务启动就依赖嵌入模型）；第二层是 `HumanInTheLoopMiddleware` 拦 `delete_note`（07 的机制）。

第三层是追踪回调：用 `agent.with_config({"callbacks": [ServerTracer(...)]})` 挂在图级——它返回的仍是 `CompiledStateGraph`，可被服务直接加载。

服务侧的调用链与三个能力的位置如下图：

![服务总装：SDK → langgraph dev → 三个能力合一的图](images/server.architecture.svg)

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/langchain/12_dev_server/images/server.architecture.html)
> （或本地打开 [`images/server.architecture.html`](images/server.architecture.html)）。

### SDK 的一问一审批

问答场景：`client.threads.create()` 建会话，`client.runs.wait(thread_id, "research_agent", input=...)` 阻塞拿到结果——断言里同时检查"检索工具的输出含 `langchain.md`"与"答案含结论"，证明检索真的被调用且被用上。

审批场景：`runs.wait` 返回的字典里有 `__interrupt__`（`[2]` 段的 `True`）——run 停在删除工具执行前。

客户端读取决策所需信息后，用 `command={"resume": {"decisions": [{"type": "approve"}]}}` 再次 `runs.wait`，工具才真正执行。

审计文件 `deleted_notes.txt` 是"审批前没执行"与"审批后才执行"的磁盘取证（07 的 resume 协议在服务端原样可用）。

### 重启持久化：平台接管 checkpointer

验证脚本停掉服务、重新启动，再对同一 thread 调 `threads.get_state`——问答记录完整读回。这靠的是服务自动注入的持久化。

注意两件事：图定义里**不能自带 checkpointer**（会被服务拒绝，见踩坑 1）；`langgraph dev` 的落盘是**周期性刷盘**，脚本在停止前等 8 秒让最新快照写完（踩坑 2）。

## Pitfalls & Q&A

### 踩坑清单

1. **自备 checkpointer 的图会被服务拒绝**。现象：服务启动失败，报 `Heads up! Your graph ... includes a custom checkpointer ... persistence is handled automatically by the platform`（实测原文）。原因：服务把持久化接管了，等价于替你挂了 checkpointer。解法：图定义里去掉 `checkpointer=...`；本地直连调图（不走服务）时才需要自己挂。
2. **dev 持久化是周期刷盘，不是每次超步立即落盘**。现象：运行完立刻重启，`get_state` 读到的是稍早的快照（比如最后一个工具消息而非最终回答）。原因：开发态服务隔一段时间把内存态刷到 `.langgraph_api/`。解法：演示/取证前等一拍（本篇等 8 秒）；生产场景用真正的持久化后端。
3. **服务残留占用端口**。现象：重复运行时报端口被占用或行为异常。原因：`langgraph dev` 会拉起多个子进程，简单 kill 父进程可能留下监听者。解法：脚本用进程组（同一次启动拉起的全部相关进程的集合，可一次性发终止信号）整体终止（`os.killpg`）；手动清理用 `pkill -f "langgraph dev"`。

4. **dev 持久化会在下次启动重放残留任务**。现象：连续运行时，上一轮的删除任务被重放——审计文件出现两行、验收从 7/7 变 6/7（实测）。原因：`.langgraph_api/` 里留有未终结的任务记录，服务启动时恢复执行。解法：脚本在启动前自动清理该目录；手动操作时删除实验目录下的 `.langgraph_api/` 再起服务。

### 深入问答

**Q：这跟"用 FastAPI 把图包起来"相比，省了什么？**

省掉的是"服务骨架"：thread 的状态存储与读取、run 的生命周期与并发、interrupt 的挂起/恢复协议、流式输出接口——FastAPI 方案这些都要自己实现一遍，还要保证它们和 LangGraph 的中断语义对齐。

`langgraph dev` 的代价是接受它的资源模型与约定（比如不能自带 checkpointer）。

**Q：assistant / thread / run 和前面实验的概念怎么对应？**

thread 就是 06 实验的 `thread_id`（会话状态），run 就是一次 `invoke`/`stream`（现在有独立的生命周期与状态查询），assistant 就是"部署好的图"（06 里图是进程内对象，现在是服务资源）。

07 的 interrupt/resume 协议不变，只是决策载荷从进程内改成经 HTTP 传递。

**Q：这套服务能直接上生产吗？**

不能。`langgraph dev` 定位是开发/测试：内存态持久化、无鉴权、单机。生产路径是同一张图换运行后端（自托管 Docker/Postgres 或托管平台），服务协议与 SDK 调用方式不变——你的客户端代码不用改。本线在零云约束下止步于本地服务，这一步与生产的距离值得知道。
