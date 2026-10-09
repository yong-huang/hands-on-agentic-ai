# 05 · StateGraph 三件套：State、Reducer 与条件边

> StateGraph 是 LangGraph 的状态图：把工作流声明成"节点读写共享状态、边控制流向"的图。
> 它由三件套构成——State（共享状态）、Node（读写状态的函数）、Edge（连接节点的线，决定下一步谁执行；其中条件边按状态值选择下一跳，也支持绕回形成循环）。
> 本篇是纯离线实验：先复现"两个并行分支写同一 key"的失败现场，再用 reducer（同名 key 的合并规则）修复；随后用 `add_messages` 管理消息、用条件边写一个带轮次上限的循环。
> 读完你能为任意流程画出"状态 + 节点 + 边"的骨架，并知道并行写状态时框架的合并规则从哪来。

## Background

多步流程最朴素的做法是函数串行调用：上一步的返回值传给下一步。一旦出现分支和循环，控制流就开始散落——`if score < 8: 回去重写` 写在函数体里，状态是手工维护的字典，加一个并行分支要改所有相关函数。

并行让问题更加尖锐：两个分支同时"给 state 加一条日志"，后写的会覆盖先写的，或者干脆报错——到底该保留谁的？这其实是"合并策略"问题，散在业务代码里每次都要重新决定。

LangGraph 把三件事显式化：状态用带类型的字典声明、每个 key 的合并规则挂在类型上（reducer）、流向用边声明（含条件边）。控制流从代码里抽出来变成图结构，并行合并成为声明式配置。

## What

StateGraph 是一种"节点读写同一个共享状态、边决定下一步谁执行"的流程编排模型。核心抽象：

| 抽象 | 是什么 | 实验中的体现 |
|:--|:--|:--|
| State | 共享状态，用 TypedDict（Python 的类型标注写法：用字典的形状声明一个类型，键名和类型写死在类体里）声明，各节点返回"增量" | `{"logs": [...], "total": int}` |
| Reducer | 同一 key 被多次写入时的合并函数，声明在 `Annotated`（Python 类型标注的包装语法，格式为 `Annotated[原类型, 附加信息]`，此处把合并函数挂在类型上）注解上 | `Annotated[list, operator.add]` |
| Node | 读写状态的普通函数 | `write` / `critic` / `revise` |
| Edge / 条件边 | 声明下一跳；条件边按状态值路由 | `route()` 返回 `done/revise/give_up` |

可以把 State 想象成一块多人共写的白板：每个节点上来只写自己那部分，reducer 是"两个人同时写同一行时怎么合并"的规则。但和白板不同的是：合并规则不是现场商量，而是**声明在状态类型上、对所有节点一致生效**——节点里不需要任何防冲突代码。

## When to Use

典型场景：

1. 带并行分支的流程：一个任务拆成多个分析/审查步骤同时跑（fan-out，扇出，一对多分发），最后再汇总回一处（fan-in，扇入，多对一汇聚）。
2. 带循环的流程：评审不过回炉重写、检索不到就重试，需要轮次上限。
3. 为后续能力打底：持久化、中断、流式都建立在"状态图 + 检查点"之上（06-08 实验）。

何时不用：单条线性链用 LCEL（LangChain Expression Language，用管道符 `|` 把步骤串成链的写法）更简洁；没有状态流转的一次性脚本，函数调用足够。

同类方案对比：

| 方案 | 状态管理 | 什么时候选它 |
|:--|:--|:--|
| 函数串行调用 | 参数传递/闭包 | 线性、无循环 |
| LCEL 链 | 无显式状态 | 管道式数据处理 |
| StateGraph（本篇） | 显式 State + reducer | 并行、循环、后续要持久化 |

## Quick Start

以下命令从仓库根目录（clone 后的 `hands-on-agentic-ai/`）执行。纯离线，不需要 Ollama；依赖已装在仓库根 `.venv`（见 [docs/langchain.md](../../docs/langchain.md) 的「环境配置」节）。

```bash
cd langchain/05_state_graph               # 在仓库根目录执行
source ../../.venv/bin/activate           # 也可直接用 ../../.venv/bin/python
python3 state_graph.py
```

真实输出（节选：省略分隔线，以空行代替）：

```text
[05] StateGraph 三件套：State、Reducer 与条件边（纯离线）

[A] 复现：无 reducer 的并行写入报 InvalidUpdateError
  报错原文: At key 'logs': Can receive only one value per step. Use an Annotated key to handle multiple values.
  ✅ 无 reducer 并行写报 InvalidUpdateError

[B] 修复：加 Annotated reducer 后正确合并
  合并结果: total=2, logs=['a', 'b', "merged:['a', 'b']"]
  ✅ 并行分支写入被 reducer 合并

[C] add_messages reducer：消息只追加不覆盖
  消息序列: [('HumanMessage', '你好'), ('AIMessage', '收到 1 条消息')]
  ✅ 两次节点写入被合并为两条消息

[D] 条件边循环：达标退出
  路径: write → critic → revise#1 → critic → revise#2 → critic → done
  最终: score=14 rounds=2
  ✅ 循环在 score≥10 时经 done 退出 — 实际轮数=2

[E] 轮次上限守卫：不达标时强制收束
  路径: write → critic → revise#1 → critic → give_up
  ✅ 达到 max_rounds 后经 give_up 收束 — 实际轮数=1

验收: 5/5 通过 ✅
```

诚实预期：全程无网络与模型调用，任意机器可复现（`critic` 用"字数"模拟评分，保证确定性）。退出码：0 全部通过，1 有断言失败。

## How It Works

### Reducer 是声明在状态上的合并契约

两个并行分支同时返回 `{"logs": [...], "total": 1}`，合并规则完全由状态类型注解决定，结构如下图：

![Reducer 合并：两个并行分支写同一份 State](images/reducer.architecture.svg)

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/langchain/05_state_graph/images/reducer.architecture.html)
> （或本地打开 [`images/reducer.architecture.html`](images/reducer.architecture.html)）。

不声明 reducer 时，框架发现同一个 step 里同一 key 收到两个写入，直接抛 `InvalidUpdateError` 并提示"使用 `Annotated` key"——先复现失败、再加修复，这是理解它最直接的方式。

`Annotated[list, operator.add]` 的含义是"每次写入都追加"；`Annotated[int, operator.add]` 是"每次写入都相加"。对照 `[B]` 输出：`total=2`（1+1），`logs` 里两条分支数据都在。

### add_messages：消息专用的 reducer

消息列表用 `langgraph.graph.message.add_messages`：它不只追加，还会按消息 id 去重、支持更新已有消息（比如模型重发同 id 的修正版）。`[C]` 段两次节点写各自一条消息，最终列表长度 2——没有覆盖。

### 条件边与循环守卫

`add_conditional_edges` 接收一个路由函数，返回的字符串映射到下一个节点。`[D]` 段的循环契约是"评审达标就退出"：`critic` 节点给分、`route` 判断三条出路，`revise` 把边回到 `critic` 形成闭环。

循环必须有第二道出口：`[E]` 段把上限压到 1 轮，路由在"不达标但轮数用尽"时走 `give_up`。路径打印里 `write → critic → revise#1 → critic → give_up` 就是守卫生效的证据——没有它，不达标的输入会让图永远转下去。

## Pitfalls & Q&A

### 踩坑清单

1. **并行写同一 key 必须声明 reducer**。现象：`InvalidUpdateError: At key 'logs': Can receive only one value per step.` 原因：框架不知道两个写入该保留谁。解法：给该 key 加 `Annotated[..., 合并函数]`；串行写同一 key 不会触发这条限制。
2. **`operator.add` 的合并顺序不保证**。现象：并行分支的日志顺序偶尔不同。原因：合并按任务完成顺序应用，不按边声明顺序。解法：对顺序敏感的聚合改用带序号的写入，或聚合成 dict 再排序。
3. **循环没有守卫就是无限循环**。现象：图一直转、进程不退出。原因：条件边永远返回回炉分支。解法：路由函数里同时检查"达标"与"轮数上限"两个条件（本篇做法），上限值放进 state 便于测试。

### 深入问答

**Q：reducer 定义在节点上还是状态上？**

状态上。它是类型的属性，不是某个节点的行为——这样无论谁写、写几次，合并规则都一致。想让某个 key"最后写入者胜"，就不加 reducer（串行时默认覆盖；并行时框架会报冲突，逼你显式决策）。

**Q：什么时候该用 `add_messages` 而不是 `operator.add`？**

状态里放对话消息时用 `add_messages`：它是为消息语义定制的 reducer（按 id 去重、可更新）。普通列表（日志、结果集）用 `operator.add` 就够。

**Q：条件边和 `Command` 有什么区别？**

条件边把"路由函数"从节点里拿出来，声明在图上；`Command(goto=...)` 让节点自己决定下一跳（还能顺带更新状态）。前者适合结构清晰的分支，后者适合节点内部才知道去哪的场景——07 实验的 `Command(resume=...)` 与 09 实验的 `Command(goto=...)` 都会用到。
