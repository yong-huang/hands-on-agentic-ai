# 26 · 工作流编排：扇出评审 + 反思修订循环

> 项目 25 的 Worker 是"各干各的"独立产出。本篇的编排多了两个机制：**扇出/
> 扇入**——同一份稿件并行送给 3 个不同视角的评审员（准确性/结构/风格），
> 意见与评分扇入汇总；**反思循环**——均分不达标就带着全部意见回炉修订，
> 再评，直到达标或用尽轮数。真机实测：三路评审并行 9.7s，均分 8.0 一次过。

## 1. 为什么需要它

单评审员只有单一视角，容易漏掉结构或风格问题；串行评审又太慢。扇出让多个
**异构视角**同时审视同一份产物，扇入把意见合并成多维反馈；反思循环让"生成
→批评→修改"形成闭环——这正是 Reflection 模式的落地形态，也是 AI 应用里
最可靠的自我改进手段（批评比生成容易，所以多角色批评能实质提升产物质量）。

## 2. 总览：核心机制一图看懂

![扇出评审与反思修订](images/workflow_orchestration.workflow.svg)

**怎么看这张图**：写作层的初稿扇出（Fan-out）给评审泳道的三个并行评审，
意见与评分扇入（Fan-in）到反思修订节点；修订稿回炉重新评审，条件边在
"均分 ≥8 或轮数用尽"时走向定稿。

心智模型一句话：**一个作者、三个批评家、一个循环——改到能过审为止。**

🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/26_workflow_orchestration/images/workflow_orchestration.workflow.html)（或本地打开 [`images/workflow_orchestration.workflow.html`](images/workflow_orchestration.workflow.html)）。

## 3. 快速开始

```bash
cd agents/26_workflow_orchestration
python workflow_orchestration.py --demo   # 离线：预置评审，走完两轮编排
python workflow_orchestration.py          # 真实：qwen3.8 三路并行评审 + 修订
```

**真机实测**（默认任务：撰写《如何为团队编写高质量的 Agent 开发规范》）：
初稿 254 字 → 三路评审并行（9.7s，均分 8.0：准确性 8/结构 8/风格 8，意见
集中在"缺 Agent 特有技术细节"）→ 均分达标一次过定稿。demo 模式则完整演示
了修订支：第一轮 6/7/7 分 → 带意见回炉 → 第二轮 8/8/9 定稿。

## 4. 核心概念

### 4.1 扇出/扇入（Fan-out/Fan-in）

| 阶段 | 机制 | 收益 |
| :--- | :--- | :--- |
| Fan-out | 3 个评审视角并行（ThreadPoolExecutor） | 墙钟 ≈ 最慢评审，而非之和 |
| Fan-in | 意见与评分汇总为一个反馈块 | 多维反馈一次到位 |

评审视角是**异构**的（准确性/结构/风格各有评审提示词）——同构的多份评审
只会互相重复，异构才产生增量信息。

### 4.2 反思循环（Reflection）

退出条件二选一：均分 ≥8（质量达标）或轮数用尽（预算耗尽）。修订提示词
**携带全部评审意见**——修订不是重新生成，而是带着批评针对性改进。真机首轮
三位评审员的意见高度一致（"缺 Agent 特有细节"），这种共识意见正是修订的
最佳输入。

### 4.3 与 24/25 的编排对照

| | 24 LangGraph | 25 Manager-Worker | 26 本篇 |
| :--- | :--- | :--- | :--- |
| 编排原语 | 状态图 + 条件边 | 分解 + 并行 + 合并 | 扇出评审 + 反思循环 |
| 循环 | 有（修订回炉） | 无 | 有 |
| 并行 | 无 | 有（Worker 产出独立） | 有（同一产物的多维评审） |
| 适用 | 需要检查点的复杂流程 | 任务可独立拆分 | 产物需要多维质检 |

### 4.4 已知边界

- 评审员与作者是同一个模型——存在"自己偏好自己风格"的相关性偏差；
  生产可混用不同模型当评审员；
- 轮数用尽时以当前版本定稿并如实标注均分，不假装达标。

## 5. 代码关键部分

```python
def review_once(reviewers, draft, round_no):
    """Fan-out: 三路并行评审; 返回 (均分, 汇总反馈)"""
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=len(reviewers)) as pool:
        reviews = list(pool.map(one, reviewers))
    avg = round(sum(r["score"] for r in reviews) / len(reviews), 1)
    feedback = "\n".join(f"- {r['reviewer']}({r['score']}分): {r['comment']}"
                         for r in reviews)
    return avg, feedback
```

坑清单：

- 评审 JSON 解析失败时给中位分兜底，不让一个评审员的格式抖动拖垮整轮；
- 修订提示词必须包含全部意见（而不是只有低分项）——共识意见最有指导性；
- `ThreadPoolExecutor.map` 保持结果顺序与评审列表对应，方便对照。

## 6. 文件结构

```
26_workflow_orchestration/
├── README.md                                    # 本篇教程
├── workflow_orchestration.py                    # 主脚本（约 190 行）：扇出评审 + 反思循环
└── images/
    ├── workflow_orchestration.workflow.json     # 图源：workflow 类型（扇出/扇入 + 循环）
    ├── workflow_orchestration.workflow.html     # 交互版架构图
    └── workflow_orchestration.workflow.svg      # 双主题矢量图
```

## 7. 面试要点

- **Q: Reflection 模式为什么有效？**
  A: 批评比生成容易——模型判断"哪里不好"的准确率高于"一次写好"。多维
  批评意见作为修订输入，等效于把评估信号注入生成过程。
- **Q: 评审员应该同构还是异构？**
  A: 异构（不同视角/不同模型）。同构评审产生重复意见，浪费调用且无增量。
- **Q: 扇出并行的前提是什么？**
  A: 子任务相互独立。评审恰好独立（同一输入、不同视角）；若评审之间需要
  看到彼此意见则应改为串行辩论（项目 27）。
- **Q: 反思循环如何防止无限循环？**
  A: 双退出条件：质量达标或轮数预算用尽；预算用尽时如实标注未达标版本。
- **Q: 与项目 25 的并行有何不同？**
  A: 25 的 Worker 处理互不相同的子任务（分治）；26 的评审处理同一产物的
  不同维度（多视角质检）——扇出的对象与目的不同。

## 8. 总结

扇出让多维质检并行化，扇入把意见变成修订输入，反思循环让产物在"批评-改进"
中收敛。与状态图（24）、分治并行（25）相比，编排的选择取决于任务结构——
而判断依据永远是用数据测出来的。下一篇让多个 Agent 围绕同一问题正面对辩，
用投票产生结论。
