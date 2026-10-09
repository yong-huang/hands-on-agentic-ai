# 09 · 编排原语：Send 动态扇出与 Command 监督者路由

> Send 与 Command 是 LangGraph 两个"反静态"的编排原语：Send 让扇出数量在运行时才定（输入几篇文档就开几条并行分支）；Command 让节点自己决定下一跳（路由与交接不必由边预先画死）。
> 本篇纯离线：A 段用 N=3 与 N=7 验证动态扇出数随输入变化、子图作为节点可独立运行；B 段用 Command 搭一个监督者 + 两个 worker（处理具体任务的角色），演示按问题类型路由与 worker 间的交接（handoff：把未完成的任务连同上下文转交给另一个角色）。
> 读完你能把"数量不定"和"去向不定"的流程从 if/else 里解放出来。

## Background

05 实验的条件边（conditional edge：按条件判断下一步走哪条边的出边）已经能路由分支，但它有两个限制。第一，分几路是**代码里写死**的：`Send` 出现之前，要给"输入的文档列表"每篇开一个分支，只能在图里预画一堆边——列表长度变了图就废了。

第二，路由决策写在**边的路由函数**里：节点返回"我改了什么状态"，路由函数再决定去哪。当"去哪里"只有节点自己知道时（比如研究者判断这个问题该自己答还是交给统计员），决策被拆到节点外面，封装就破了。

LangGraph 的补法很直接：Send 在运行时"开工单"——每个工单带着自己的输入去跑同一个节点；Command 让节点返回"下一步去哪 + 顺手更新什么状态"，路由决策回到知道答案的人手里。

## What

两个原语各管一类"不确定"：

| 原语 | 管的不确定 | 形态 | 实验中的用法 |
|:--|:--|:--|:--|
| `Send` | 分支**数量**运行时才知道 | 路由函数返回 `[Send(节点, 载荷), ...]` | 每篇文档一个工单进 `process` |
| `Command(goto=..., update=...)` | 去向**节点自己**才知道 | 节点返回导航 + 状态更新 | supervisor 路由 / worker 交接 |

可以把 Send 想象成主管开工单：来几件事开几张单，每张单带着材料去同一个工位；把 Command 想象成对讲机：工位干完活，自己呼叫下一个工位，而不是等流程图指挥。

但和真实工厂不同的是：两者都在**同一张状态图**里发生——工单的结果由 reducer（归约器：把各并行分支返回的增量合并回同一份状态的函数）汇总回同一份状态，交接后读到的还是同一份上下文。

另一个要点：编译好的**子图可以直接当节点**——子图是独立可运行的图，嵌进父图后输入输出与普通节点无异。

## When to Use

典型场景：

1. 数量不定的批处理：一批文档做摘要、一批候选做打分，几篇就开几条分支。
2. 多角色路由：按问题类型分派给不同专长的 worker（客服/技术/财务）。
3. 交接（handoff）：处理到一半发现任务属于另一个角色，连同上下文一起转交。

何时不用：分支数固定且拓扑清晰时，普通边/条件边更直白；只有一个"机器"在干活时，这些原语是多余的抽象。

同类方案对比：

| 方案 | 分支数 | 去向决策 | 什么时候选它 |
|:--|:--|:--|:--|
| 普通边 / 条件边 | 写死在图里 | 路由函数 | 拓扑固定的流程 |
| `Send`（本篇 A 段） | 运行时动态 | 路由函数 | 批处理、map-reduce |
| `Command`（本篇 B 段） | — | 节点自己 | 角色路由、交接 |

## Quick Start

以下命令从仓库根目录（clone 后的 `hands-on-agentic-ai/`）执行。纯离线，不需要 Ollama；依赖已装在仓库根 `.venv`（见 [docs/langchain.md](../../docs/langchain.md) 的「环境配置」节）。

```bash
cd langchain/09_orchestration             # 在仓库根目录执行
source ../../.venv/bin/activate           # 也可直接用 ../../.venv/bin/python
python3 orchestration.py
```

真实输出（节选：省略分隔线，以空行代替）：

```text
[09] 编排原语：Send 动态扇出与 Command 监督者路由（纯离线）

[A] Send 动态扇出 + 子图 map-reduce（离线）
  N=3: process 事件 3 个, total=3, 聚合 3 条
  ✅ N=3 时并行分支数 = 3（按事件计数）
  ✅ N=3 时聚合结果完整
  N=7: process 事件 7 个, total=7, 聚合 7 条
  ✅ N=7 时并行分支数 = 7（按事件计数）
  ✅ N=7 时聚合结果完整
  子图独立运行: {'doc': 'solo', 'results': ['摘要(solo)'], 'total': 1}
  ✅ 子图独立编译、可单独运行；父图最终只含自身 key

[B] Command 监督者：路由、交接与审计（离线）
  文本问题 audit: ['supervisor → researcher', 'researcher 完成', 'aggregate 汇总']
  ✅ 文本问题路由到 researcher
  数学问题 audit: ['supervisor → statistician', 'statistician 完成', 'aggregate 汇总']
  ✅ 数学问题路由到 statistician
  交接场景 audit: ['supervisor → researcher', 'researcher ⇢ statistician（交接）', 'statistician 完成', 'aggregate 汇总']
  交接场景 draft: 统计结果（基于问题「把 12 公里换算成英里」）：42 ｜ 已汇总
  ✅ worker 间 handoff 且上下文不丢
  ✅ 每次 goto 目标可从 audit 逐条列举

验收: 9/9 通过 ✅
```

诚实预期：全程无网络与模型调用，任意机器可复现（路由条件是关键词判断，保证确定性）。退出码：0 全部通过，1 有断言失败。

## How It Works

### Send：把"来几件开几张单"交给运行时

`fanout` 路由函数按 `len(state["docs"])` 返回等量的 `Send("process", {"doc": d})`。每个 Send 是一个独立分支任务：同一节点 `process` 被并发调用 N 次，每次收到自己的载荷。

证据链：`[A]` 段用 `stream_mode="updates"` 数 `process` 事件数——N=3 时 3 个、N=7 时 7 个，说明分支数真的跟着输入走。

聚合靠 reducer：`results` 用 `operator.add` 把每个分支的列表追加合并、`total` 把每份 1 相加，最终 `total == N` 且内容完整。

这就是 map-reduce 模式：fanout 是 map——把 N 篇文档映射成 N 个并行分片；reducer 是 reduce——把 N 份分片结果归并成一份。

`process` 节点本身是一张独立编译的子图：它单独运行时输入输出自洽，嵌进父图后与普通节点无异。这是"把子流程封装成组件"的标准姿势。

### Command：路由与交接都由节点自己发话

`supervisor` 节点检查问题里的关键词，返回 `Command(goto=..., update={"audit": [...]})` 决定去向。

workers 处理完也不是被边牵着走，而是自己发下一跳：researcher 发现"换算"类问题就直接 `Command(goto="statistician")` 完成交接，并把审计记录追加进 `audit`。

`[B]` 段前三条断言对应三件事：文本问题到 researcher、数学问题到 statistician、交接场景的 draft 里保留了原始问题（**上下文不丢**——handoff 传的是同一份状态，不是新建一张空表）。

第四条断言验证 `audit` 列表按序记录了每一次 goto，路由轨迹可逐条复述。结构如下图：

![Command 监督者：路由到 worker，再汇总（含 handoff）](images/supervisor.workflow.svg)

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/langchain/09_orchestration/images/supervisor.workflow.html)
> （或本地打开 [`images/supervisor.workflow.html`](images/supervisor.workflow.html)）。

## Pitfalls & Q&A

### 踩坑清单

1. **`Send` 只能从路由函数返回**。现象：把 `[Send(...)]` 当普通节点返回值，报 `InvalidUpdateError: Expected dict`。原因：Send 是"分支任务的描述"而非状态增量，框架只在条件边/路由函数的返回值里解释它。解法：让节点返回状态、把 Send 放进条件边的路由函数。
2. **`Command` 的 goto 写错节点名不会报错**。现象：流程走到一半静默结束，日志里只有一行 `wrote to unknown channel branch:to:ghost, ignoring it`（实测原文）。原因：框架把未知目标当作"没有后续任务"忽略。解法：审计 `audit` 列表断在最后一段就是信号——检查目标节点名拼写与注册。
3. **handoff 不等于复制上下文**。现象：以为交接要手动搬运数据。原因：worker 共享同一份状态，原始问题、已有产出都在里面。解法：别"搬运"，直接读状态；需要隔离时再考虑把 worker 做成独立子图（状态边界不同）。

### 深入问答

**Q：`Send` 和"并行边"（START 扇出多个固定节点）有什么区别？**

固定扇出是拓扑写死：图里画几条边就有几条分支。Send 的分支数由运行时的数据决定，N 可以是 3、7 或 1000；另外每个 Send 可以带**不同的载荷**（每篇文档不同），固定边做不到。

**Q：`Command` 和条件边怎么选？**

看"谁知道答案"：路由规则只依赖状态、与节点实现无关 → 条件边（把路由集中在一处，图结构清晰）；去向由节点的处理结果决定（干完才知道下一个该找谁）→ Command。两者可以混用，同一个图里有些跳转来自边、有些来自 Command。

**Q：Send/Command 这套编排原语和 03 的 `create_agent` 循环是什么关系？**

同一套原语的封装关系：`create_agent` 的自循环就是"模型节点用 Command 式的决策回到工具节点"的固定模式。当循环需要多个角色、动态批处理或多级路由时，就该像本篇这样用 Send/Command 自己编排——10-12 的实验都建立在这一层上。
