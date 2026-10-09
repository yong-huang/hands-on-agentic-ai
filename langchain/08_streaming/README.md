# 08 · 流式输出：四种 stream_mode 与事件流

> `graph.stream()` 让同一次运行支持四种消费视角：values（状态快照）、updates（节点增量）、messages（token 分片——token 是模型生成文本的最小单位，可能是一个字、一个词或标点；流式输出即模型每生成一个 token 就立即返回一段）、custom（自定义事件）；`astream_events` 则把内部一切活动暴露成事件流。
> 本篇离线段用假模型验证四种模式的结构与"流式结果 = invoke 结果"；真机段拿到 token 级流并过滤模型事件。
> 读完你能为聊天界面、进度条、调试面板各选对一种流式视角，并知道 token 级输出的来源。

## Background

一次 `invoke` 是"等模型把整段话写完再返回"。聊天界面要打字机效果、长任务界面要进度条——都需要"边跑边拿"。最早的实现各自为政：模型调用处手动切分文本、工具轮询进度、日志另开一路，同一件事写三套。

流式机制要解决的其实是"给不同的消费者提供不同粒度的增量"：看聊天的人关心逐字输出，看进度的人关心到哪一步了，调试的人关心每个组件的进出事件。粒度不同，但来源是同一次运行。

LangGraph 把这个需求归一到 `stream()` 的四种模式：同一次执行可以分别按"整状态快照 / 节点增量 / 模型 token / 自定义事件"消费；更细的内部活动则由 `astream_events` 统一暴露。

## What

`stream_mode` 是 `stream()` 的模式参数：同一次运行，用它选择按哪种粒度"消费"（读取并处理流式产出）。它有四种取值：

| 模式 | 每次产出 | 典型消费者 |
|:--|:--|:--|
| `values` | 当前完整状态快照 | 需要"最新全量状态"的看板 |
| `updates` | `{节点名: 增量}` | 进度跟踪、逐步渲染 |
| `messages` | `(消息分片, 元数据)` | 聊天界面打字机、TTFT（Time To First Token，首 token 延迟：从发起请求到收到第一个 token 的时间）统计 |
| `custom` | 节点里 `get_stream_writer()` 发出的事件 | 业务进度（"已完成 3/10 篇"） |

可以把四种模式想象成同一场比赛的四种转播机位：全场全景（values）、记分牌变化（updates）、明星跟拍（messages）、解说席（custom）。但和转播不同的是：四种机位不是同时铺开的，你在开播前选机位——所以先想清楚消费者需要什么。

`astream_events` 是更底层的事件总线——把运行中每个组件的开始、结束与流式产出都变成一条带类型名的事件，交给同一个循环处理。

事件名如 `on_chain_start`（组件开始）、`on_chat_model_stream`（模型产出分片）、`on_tool_start`（工具开始），适合"什么都想记录"的可观测场景。

## When to Use

典型场景：

1. 聊天类界面：`messages` 模式拿 token 流，边生成边渲染（12 的服务化实验会把它接上 SSE——Server-Sent Events，服务器持续单向推送数据给浏览器的协议，网页打字机效果常用）。
2. 长流程进度：`updates` 逐步亮节点，`custom` 报业务进度（第几篇、百分比）。
3. 调试与观测：`astream_events` 记录每个组件的事件与耗时。

何时不用：批处理与离线评测直接用 `invoke`（流式只增加复杂度）；只关心最终结果的调用方没有增量可消费。

同类方案对比：

| 方案 | 增量粒度 | 什么时候选它 |
|:--|:--|:--|
| `invoke` | 无（一次性） | 只要最终结果 |
| `stream(mode)`（本篇） | 四种固定粒度 | 交互界面、进度、业务事件 |
| `astream_events` | 原始事件流 | 深度观测、自定义过滤 |

## Quick Start

以下命令从仓库根目录（clone 后的 `hands-on-agentic-ai/`）执行。

依赖已装在仓库根 `.venv`（见 [docs/langchain.md](../../docs/langchain.md) 的「环境配置」节）；真机段需要本机 Ollama（在本地运行大语言模型的服务）已启动且已拉取 `qwen3.8:latest`。

```bash
cd langchain/08_streaming                  # 在仓库根目录执行
source ../../.venv/bin/activate            # 也可直接用 ../../.venv/bin/python
python3 streaming.py                       # 真机：A 离线 + B 调模型
python3 streaming.py --demo                # 离线：只跑 A 段
```

真实输出（节选：省略分隔线，以空行代替）：

```text
[08] 流式输出：四种 stream_mode 与事件流
模式: 真机（qwen3.8:latest）

[A] 四种 stream_mode 的结构（离线）
  values 快照 3 个，最终: 杭州是浙江省会，以西湖闻名。
  ✅ values：快照逐层生长，最终状态与 invoke 一致
  updates 增量节点: ['prepare', 'generate']
  ✅ updates：按节点给出增量
  messages 分片 14 个，来源节点: {'generate'}
  ✅ messages：token 级分片且带节点元数据
  custom 事件: [{'stage': 'generate', 'progress': 0.5}, {'stage': 'generate', 'progress': 1.0}]
  ✅ custom：图内自定义进度事件按序到达

[B] 真机：messages token 流与 astream_events（真机）
  messages: 21 个 token 分片，拼接: 杭州是一座以西湖美景闻名于世，兼具深厚历史文化底蕴与现代互联网科技活力的江南名城。
  ✅ 真机 token 级流式分片数 ≥ 5
  invoke 对照: 杭州是一座以西湖美景闻名于世，兼具深厚历史文化底蕴与现代互联网科技活力的江南名城。
  ✅ 流式拼接结果与 invoke 一致
  astream_events: 21 个模型 token 事件；事件种类 ['on_chain_end', 'on_chain_start', 'on_chain_stream', 'on_chat_model_end', 'on_chat_model_start', 'on_chat_model_stream']
  ✅ astream_events 捕获模型 token 事件

验收: 7/7 通过 ✅
```

诚实预期：真机段的单次运行由三个请求组成（messages 流、invoke 对照、astream_events 流），总耗时约 5-10 秒。

`messages` 分片数与模型逐 token 切分方式相关（一个 token 可能包含多个字），`≥5` 是下限而非固定值。Ollama 未启动时真机部分跳过（退出码 2），`--demo` 只跑 A 段（4/4）。

## How It Works

### values 与 updates：同一份状态的两个视角

`values` 在每个超步（superstep：图的一次推进，当前所有就绪节点执行完一轮）后吐一次完整状态——快照数是"节点数 + 1"（含初始），`[A]` 段 3 个快照对应初始、prepare 后、generate 后。断言"最终快照 = `invoke` 结果"是验收流式正确性的通用手法。

`updates` 吐 `{节点名: 该节点返回的增量}`。看输出：`{'prepare': {'steps': [...]}}`、`{'generate': {'answer': ..., 'steps': [...]}}`——节点返回什么就流什么，适合做"当前进行到哪个节点"的进度条。

### messages：token 从哪来

`messages` 模式拦截图内所有模型调用的流式回调（回调：框架在模型每产出一段时自动调用的钩子函数），产出 `(AIMessageChunk, 元数据)`。

AIMessageChunk 是模型消息 AIMessage 的分片，只含本次增量内容。元数据里的 `langgraph_node` 告诉你 token 来自哪个节点——`[A]` 段断言它等于 `generate`。

这也是 01 实验"首 token 延迟"的底层：模型一边生成，回调一边产出分片。

### custom：业务事件自己发

节点内 `writer = get_stream_writer()` 拿到写入函数，`writer({...})` 的内容会出现在 `custom` 模式里。不需要流式展示时（比如直接 `invoke`），writer 是空操作，节点代码无需分支——实验的 `invoke` 对照路径验证了这一点。

### astream_events：原始事件与过滤

事件流包含 `on_chain_start/end`、`on_chat_model_start/stream/end` 等。`[B]` 段过滤 `on_chat_model_stream` 收集 token，并断言流的拼接与 `invoke` 一致。四种模式与事件流的关系如下图：

![一次运行，四种流式消费视角](images/stream_modes.architecture.svg)

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/langchain/08_streaming/images/stream_modes.architecture.html)
> （或本地打开 [`images/stream_modes.architecture.html`](images/stream_modes.architecture.html)）。

## Pitfalls & Q&A

### 踩坑清单

1. **流式与 invoke 是两次独立请求**。现象：把流式拼接结果与 `invoke` 结果对照时不一致。原因：两次请求各自生成，采样有随机性。解法：对照检查时 `temperature=0`（脚本按此设置）；生产代码不做这种对照，改做结构断言。
2. **messages 的产物是分片不是整消息**。现象：拿到 `AIMessageChunk` 后直接当 `AIMessage` 用，字段缺失。原因：分片只含增量内容，要拼接后才等价于完整消息。解法：需要完整消息时用 `+` 合并分片，或改用 `invoke`。
3. **custom 事件依赖流式上下文**。现象：平时代码里 `writer(...)` 好像"没反应"。原因：不是流式消费时 writer 是空操作——这是设计，不是故障。解法：调试自定义事件时用 `stream_mode="custom"` 跑一次。

### 深入问答

**Q：四种模式怎么选？**

按消费者倒推：界面要逐字渲染 → `messages`；进度条要"走到哪一步" → `updates`（或业务进度用 `custom`）；状态看板要最新全量 → `values`；观测平台要全部细节 → `astream_events`。

本实验每次只选一种模式消费；`stream_mode` 也支持传列表一次消费多种模式（每次产出 `(模式名, 内容)` 对），更彻底的统一方案是事件总线（11/12 实验的话题）。

**Q：流式会影响最终结果的正确性吗？**

不会。四种模式读的是同一次执行的同一份状态，区别只在"以什么粒度送出"。`values` 的最终快照与 `invoke` 逐字段相等，就是本篇的验证方式。

**Q：token 级流式对性能有什么要求？**

分片越多并不意味着更慢：模型输出的总 token 数不变，流式只是把"等待"变成"边等边显示"，首 token 延迟（TTFT）决定体感速度。UI 侧要做批量合并渲染（比如 30-50ms 一帧），否则高频增量会拖慢前端。
