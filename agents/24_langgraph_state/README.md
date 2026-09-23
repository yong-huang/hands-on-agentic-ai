# 24 · LangGraph 状态管理：带条件边与循环的工作流

> 把"写作→评审→修订"这种带**条件跳转与循环**的流程交给 LangGraph：状态
> （TypedDict）在节点间流动，条件边按评审分数决定"定稿还是回炉"。两种模式
> 都真机验证——demo 走循环支（7 分→修订→9 分），real 首稿 8 分直接走
> 通过支。

## What

LangGraph 的核心抽象是三件东西：**State**（TypedDict 共享状态）、**Node**
（读写状态的函数，返回增量）、**Edge/Conditional Edge**（声明式控制流），
图编译后 `invoke` 执行。

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

与手写（08）的对照：

| | 手写 Plan-and-Execute | LangGraph |
| :--- | :--- | :--- |
| 状态管理 | 自己拼 dict | TypedDict + 自动合并 |
| 分支/循环 | if/while | 条件边声明 |
| 可视化/调试 | 手工 | 内置图结构与检查点 |
| 学习成本 | 低（无框架） | 中（框架概念） |

心智模型一句话：**State 是共享白板，节点是工人，边是车间主任的调度
规则。**

## Why

线性管线（20 的 RAG 流程）用函数串行就够了；但 Agent 工作流很快会长出
**分支与循环**：评审不过要回炉、重试有上限、不同状态走不同分支。手写这些
控制流（08 里是自己 if/while）会随复杂度失控。LangGraph 把控制流变成
声明式的**图**：节点读写共享状态，边声明流向，条件边封装分支逻辑——结构
即代码，代码即结构图。

## How

```bash
pip install langgraph
cd agents/24_langgraph_state
python langgraph_state.py --demo   # 离线：确定性节点, 图结构照常运行
python langgraph_state.py          # 真实：节点即 qwen3.8（写作/评审/修订）
```

**双模式实测**：demo 模式完整走了一次循环（首评 7 分 → revise → 再评
9 分 → finalize）；真实模式首稿即获 8 分，条件边直接走通过支定稿（修订
0 次）——两条分支都被真实触达。

**条件边：分支逻辑的声明式表达**——`should_continue(state)` 读状态返回
路由键，分支逻辑集中在一个纯函数里，可独立测试：

```python
g.add_conditional_edges("critique", should_continue,
                        {"revise": "revise", "finalize": "finalize"})
```

建图函数：

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

## Deep Dive

**循环的保险丝必须显式设计**：`iterations` 计数器放进 State，条件边检查
它——没有它，评审员永远不满意就会无限回炉。

踩坑清单：

- 节点返回的 dict 的键必须在 State 定义里，拼错键名会静默丢失更新；
- `invoke` 传入的初始状态也要符合 State 结构（缺 `iterations` 会在条件边
  处 KeyError）；
- 节点间传大对象全部塞进 State 会让每个节点看到巨大上下文且序列化变重
  ——应只传引用（路径/id），大内容放外部存储。

## Q&A

**Q1: 条件边和普通边有什么区别？**

普通边固定流向；条件边挂一个路由函数，按当前状态返回目标节点——分支与
循环都靠它表达。

**Q2: 什么场景该用 LangGraph 而不是手写循环？**

分支/循环/并行结构复杂、需要检查点与可视化、或多个工作流要复用相同组件
时；两三个节点的线性流程手写更简单。
