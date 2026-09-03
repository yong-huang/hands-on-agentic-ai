# 24 · LangGraph 状态管理：带条件边与循环的工作流

> 手写循环（08）自由但要自己管状态、自己防死循环。本篇把"写作→评审→修订"
> 这种带**条件跳转与循环**的流程交给 LangGraph：状态（TypedDict）在节点间
> 流动，条件边按评审分数决定"定稿还是回炉"。两种模式都真机验证——demo 走
> 循环支（7 分→修订→9 分），real 首稿 8 分直接走通过支。

## 1. 为什么需要它

线性管线（20 的 RAG 流程）用函数串行就够了；但 Agent 工作流很快会长出
**分支与循环**：评审不过要回炉、重试有上限、不同状态走不同分支。手写这些
控制流（08 里是自己 if/while）会随复杂度失控。LangGraph 把控制流变成声明式
的**图**：节点读写共享状态，边声明流向，条件边封装分支逻辑——结构即代码，
代码即结构图。

## 2. 总览：核心机制一图看懂

![LangGraph 状态图](images/langgraph_state.workflow.svg)

**怎么看这张图**：写作层三个节点（大纲 → 初稿 → 修订）与评审层的 critique
构成循环——critique 的条件边按分数分岔：`score<8 且 次数<2` 走回炉（红色），
`score≥8 或 次数用尽` 走定稿。State（TypedDict）贯穿全图，每个节点只返回增量。

心智模型一句话：**State 是共享白板，节点是工人，边是车间主任的调度规则。**

🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/24_langgraph_state/images/langgraph_state.workflow.html)（或本地打开 [`images/langgraph_state.workflow.html`](images/langgraph_state.workflow.html)）。

## 3. 快速开始

```bash
pip install langgraph
cd agents/24_langgraph_state
python langgraph_state.py --demo   # 离线：确定性节点, 图结构照常运行
python langgraph_state.py          # 真实：节点即 qwen3.8（写作/评审/修订）
```

**双模式实测**：demo 模式完整走了一次循环（首评 7 分 → revise → 再评 9 分 →
finalize）；真实模式首稿即获 8 分，条件边直接走通过支定稿（修订 0 次）——
两条分支都被真实触达。

## 4. 核心概念

### 4.1 State：共享白板

```python
class ArticleState(TypedDict):
    topic: str; outline: str; draft: str
    critique: str; score: int
    iterations: int        # 修订计数器——防死循环的关键
    final: str
```

节点返回 **partial update**（只写自己负责的字段），LangGraph 负责合并进全局
状态。`iterations` 计数器是循环的保险丝——没有它，评审员永远不满意就会无限
回炉。

### 4.2 条件边：分支逻辑的声明式表达

```python
g.add_conditional_edges("critique", should_continue,
                        {"revise": "revise", "finalize": "finalize"})
```

`should_continue(state)` 读状态返回路由键。分支逻辑集中在一个纯函数里，
可独立测试——比散落在流程代码里的 if/else 可维护得多。

### 4.3 循环：修订后重新评审

`revise → critique` 的回边构成循环。退出条件二选一：评分达标（≥8）或修订
次数用尽（≥2）。**实测两种退出都真实发生**：demo 走循环支，real 走通过支。

### 4.4 手写（08）vs LangGraph（24）

| | 手写 Plan-and-Execute | LangGraph |
| :--- | :--- | :--- |
| 状态管理 | 自己拼 dict | TypedDict + 自动合并 |
| 分支/循环 | if/while | 条件边声明 |
| 可视化/调试 | 手工 | 内置图结构与检查点 |
| 学习成本 | 低（无框架） | 中（框架概念） |

## 5. 代码关键部分

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

坑清单：

- 节点返回的 dict 的键必须在 State 定义里，拼错键名会静默丢失更新；
- 循环必须有计数器/上限状态字段，否则条件边永远走回炉支；
- `invoke` 传入的初始状态也要符合 State 结构（缺 `iterations` 会在条件边
  处 KeyError）。

## 6. 文件结构

```
24_langgraph_state/
├── README.md                            # 本篇教程
├── langgraph_state.py                   # 主脚本（约 200 行）：State + 5 节点 + 条件边
└── images/
    ├── langgraph_state.workflow.json    # 图源：workflow 类型（写作-评审循环）
    ├── langgraph_state.workflow.html    # 交互版架构图
    └── langgraph_state.workflow.svg     # 双主题矢量图
```

## 7. 面试要点

- **Q: LangGraph 的核心抽象是什么？**
  A: State（TypedDict 共享状态）+ Node（读写状态的函数，返回增量）+
  Edge/Conditional Edge（声明式控制流），图编译后 `invoke` 执行。
- **Q: 条件边和普通边有什么区别？**
  A: 普通边固定流向；条件边挂一个路由函数，按当前状态返回目标节点——
  分支与循环都靠它表达。
- **Q: 图中的循环如何防止死循环？**
  A: 把退出的量化条件放进 State（如 iterations 计数），条件边检查它；
  这是状态机自带的保险丝，必须显式设计。
- **Q: 什么场景该用 LangGraph 而不是手写循环？**
  A: 分支/循环/并行结构复杂、需要检查点与可视化、或多个工作流要复用相同
  组件时；两三个节点的线性流程手写更简单。
- **Q: 节点间传递大对象有什么隐患？**
  A: 全部塞进 State 会让每个节点看到巨大上下文且序列化变重——应只传引用
  （路径/id），大内容放外部存储。

## 8. 总结

State 是白板、节点是工人、条件边是调度规则——LangGraph 把控制流变成可声明、
可测试、可视化的图。写作-评审循环的双分支在真机上都被验证触发。下一篇进入
多 Agent 世界：Manager-Worker 模式，让一个 Manager 把任务分给并行的 Worker。
