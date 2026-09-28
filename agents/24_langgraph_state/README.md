# 24 · LangGraph 状态管理：带条件边与循环的工作流

> 把"写作→评审→修订"这种带**条件跳转与循环**的流程交给 LangGraph（一个
> 把工作流编排成图结构的框架）：状态在节点间流动，条件边按评审分数决定
> "定稿还是回炉"。两种模式都真机验证——demo（离线演示）走循环支
> （7 分→修订→9 分），real（真实模型）首稿 8 分直接走通过支。读完你能用
> "图 + 共享状态"表达任意带回路的智能体工作流（Agent：能自主调用工具、
> 按目标行动的 LLM 应用）。

## Background

不带分支的工作流用函数串行就够：函数 A 调函数 B、B 调 C，20 实验的
RAG 管线（加载 → 切分 → 索引 → 查询）就是这么写的。

Agent 工作流很快长出更复杂的控制流：生成的内容要评审、评审不过要回炉、
重试次数有上限、状态不同走不同分支。手写这些逻辑（08 实验用 if/while）
在节点变多后会失控——状态是手工拼装的字典，分支散落在各个函数里，
整个流程画不成一张图，改动一处要在心里推演全部路径。

LangGraph 把控制流翻转成声明式的**图**：节点读写共享状态，边声明流向，
条件边封装分支逻辑——结构即代码，代码即结构图。流程长什么样，代码里
看得见。

## What

**LangGraph 状态管理是一种用"图 + 共享状态"组织多步工作流的方式：每个
步骤读写同一个状态对象，流向由边声明，分支由条件边按状态值决定。**

LangGraph 的核心抽象是三件东西：**State**（TypedDict 共享状态）、**Node**
（读写状态的函数，返回增量）、**Edge/Conditional Edge**（声明式控制流），
图编译后 `invoke` 执行。

其中 TypedDict 是 Python 类型系统里声明"字典有哪些键、各是什么类型"的
工具——State 的完整定义见下面的代码。

State 是共享白板——节点返回 **partial update**（只写自己负责的字段），
LangGraph 负责合并进全局状态：

```python
class ArticleState(TypedDict):
    topic: str; outline: str; draft: str
    critique: str; score: int
    iterations: int        # 修订计数器——防死循环的关键
    final: str
```

图结构：写作层三个节点（大纲 → 初稿 → 修订）与评审层的 critique 构成
循环——critique 的条件边按分数分岔：`score<8 且 次数<2` 走回炉，
`score≥8 或 次数用尽` 走定稿。退出条件二选一，两条分支都真实触达。

可以把这套结构想象成一条生产线：State 是车间共享白板，节点是各工位的
工人（只填写自己负责的栏目），边是车间主任的调度规则。但和固定生产线
不同的是，下一步走哪个工位不是焊死的传送带，而是条件边在运行时读白板上
的分数现场决定；同时所有可选路线仍是预先声明好的，运行时只做"选择"。

心智模型一句话：**State 是共享白板，节点是工人，边是车间主任的调度
规则。**

## When to Use

在流程长出回路或分岔的时候用：生成类任务需要"评审不过就回炉"（写作—
评审—修订、代码生成—测试—修复）；同一入口要按输入特征路由到不同处理
分支；多个工作流要复用同一批节点组件，或需要检查点（保存每步状态以便
回放）与可视化调试。

不用的情况：两三个节点的线性流程（Background 里函数串行的做法就够）；
不涉及共享状态的一次性脚本。

| | 手写 Plan-and-Execute（08 实验） | LangGraph |
| :--- | :--- | :--- |
| 状态管理 | 自己拼 dict | TypedDict + 自动合并 |
| 分支/循环 | if/while | 条件边声明 |
| 可视化/调试 | 手工 | 内置图结构与检查点 |
| 学习成本 | 低（无框架） | 中（框架概念） |

## Quick Start

前置条件：`pip install langgraph`；真实模式还需本地 Ollama
（localhost:11434，本地运行大模型的工具）已拉取 `qwen3.8:latest`——
每个节点都是一次 LLM（大语言模型）任务。

```bash
pip install langgraph
cd agents/24_langgraph_state
python langgraph_state.py --demo   # 离线：确定性节点, 图结构照常运行
python langgraph_state.py          # 真实：节点即 qwen3.8（写作/评审/修订）
```

`--demo` 把每个节点换成确定性的文本变换（不调用模型），图结构与真实模式
完全相同。双模式实测：demo 模式完整走了一次循环（首评 7 分 → revise →
再评 9 分 → finalize）；真实模式首稿即获 8 分，条件边直接走通过支定稿
（修订 0 次）——两条分支都被真实触达。

诚实预期：真实模式的分数由 LLM 评审给出，每次运行可能不同（8 分定稿是
本次实测，不代表每次都会直接通过）；demo 模式的分数是预置的，每次运行
一致。想稳定观察到循环支，先跑 demo。

## How It Works

建图函数把节点和边装配成一张图——流程结构在这里一目了然：

```python
def build_graph(nodes):
    g = StateGraph(ArticleState)
    for name, fn in nodes.items():
        g.add_node(name, fn)
    g.set_entry_point("outline")
    g.add_edge("outline", "draft")
    g.add_edge("draft", "critique")
    g.add_conditional_edges("critique", should_continue,
                            {"revise": "revise", "finalize": "finalize"})
    g.add_edge("revise", "critique")       # 回炉循环
    g.add_edge("finalize", END)
    return g.compile()
```

普通边（`add_edge`）固定流向；条件边（`add_conditional_edges`）挂一个
路由函数 `should_continue`，它读当前状态返回路由键，映射表把键翻译成
目标节点——`{"revise": ..., "finalize": ...}`。

分支逻辑集中在一个纯函数（同样输入必得同样输出、无副作用的函数）里，
可独立测试。

**循环的保险丝必须显式设计**：`iterations` 计数器放进 State，条件边检查
它——`score<8 且 次数<2` 才回炉。没有它，评审员永远不满意就会无限回炉。

Quick Start 的两个实测正好对应两条分支：demo 首评 7 分低于 8 且次数未
用尽，走 `revise` 回炉，二评 9 分走 `finalize`；真实模式 8 分一步触达
`finalize`，`iterations` 保持 0。

## Pitfalls & Q&A

踩坑清单（每条：现象 → 原因 → 解法）：

- **节点更新静默丢失**。现象：某节点明明返回了数据，后续节点读不到。
  原因：返回 dict 的键必须在 State 定义里，拼错键名不报错、直接丢弃。
  解法：新字段先补进 TypedDict 定义，再在节点里使用。
- **条件边处 KeyError**。现象：图一启动就在路由函数处报 KeyError。
  原因：`invoke` 传入的初始状态也要符合 State 结构，缺 `iterations`
  这类被条件边读取的键就会炸。解法：初始状态补全全部键。
- **State 越滚越大**。现象：工作流变慢、每个节点响应迟钝。原因：节点间
  传大对象全塞进 State，每个节点都看到巨大上下文且序列化变重。解法：
  State 只传引用（路径/id），大内容放外部存储。

**Q1: 分支和循环除了条件边还有别的表达方式吗？**

本篇的模式已覆盖分支（条件边多映射）与循环（回边加计数器）；更复杂的
并行分支见 LangGraph 官方文档的 Send 与子图特性，本篇不展开。
