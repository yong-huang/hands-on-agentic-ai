# 25 · Manager-Worker：任务分解与并行协作

> Manager-Worker 是一种"一个管理者分解任务、多个执行者并行处理、管理者再合并结果"的多 Agent 编排模式。读完本篇你能理解上下文隔离与真并行这两个核心收益，跑通一个双 Worker 并行实验，并学会判断哪些任务适合拆、哪些不适合。

## Background

在没有编排模式的做法里，一个 Agent（能自主调用大模型完成任务的程序）包揽全部工作：调研、分析、成文，全部在同一个对话里顺序完成。

这种做法在任务变复杂时撞墙。以"写一份 asyncio 入门文档"为例：收集概念、分析场景、整理陷阱的中间产物全堆进同一个上下文窗口（模型单次能读入的文本长度上限），互相挤占空间；角色来回切换让不同部分的输出互相污染；串行执行还让总耗时等于各步之和。

Manager-Worker 模式因此被引入 Agent 框架：把"分解—执行—合并"拆开，让执行者各自持有一份干净的上下文，彼此隔离、并行工作。

这一思路承接分布式计算里"调度者分工、工人干活"的传统，Claude Code 的 subagent（主 Agent 派生出的子 Agent）、AutoGen 的 group chat（群聊式多方对话）背后都是同一模式的变体。

## What

Manager-Worker 是一种多 Agent 编排模式（编排：组织多个 Agent 协同完成任务的流程设计）：一个 Manager 负责任务分解与结果合并，多个 Worker 各自带角色提示词、真并行处理各自分到的子任务。

真并行由线程池实现——ThreadPoolExecutor，复用固定数量线程并发执行任务的 Python 标准库设施。

可以把 Manager 想象成一个只做分工与验收的项目经理，Worker 是各管一摊的专才。但和真实团队不同的是：Worker 彼此完全不可见，任何信息交换都必须经过 Manager。

三段编排：

| 阶段 | 角色 | 做什么 |
| :--- | :--- | :--- |
| 分解 | Manager | 任务 → 2-3 个带角色的子任务（JSON，一种键值对形式的文本数据格式） |
| 执行 | Workers | 各自带角色提示词，ThreadPoolExecutor 真并行 |
| 合并 | Manager | 去重、消解冲突、组织成最终产出 |

隔离的关键在角色提示词（system 提示词，设定模型角色与职责的系统级指令）：每个 Worker 的提示词只描述自己的职责——researcher 只输出事实清单，analyst 只输出分析要点。互不可见带来两个直接结果：上下文互不污染，结果天然去冗余。

心智模型一句话：Manager 只分工与合并，Worker 只管自己那一摊——上下文隔离就是并行协作的全部秘密。

## When to Use

适合在三类时候选它：

- 做多角色综合产出时：一份调研文档既需要事实收集（researcher）又需要场景与风险分析（analyst），两类视角分开产出再合并，好于单次混合生成。
- 子任务相互独立、可以并行时：批量处理互不依赖的条目，并行能压缩墙钟时间（wall-clock，真实流逝的时间，本篇实测数字均按它计）。
- 单 Agent 上下文接近塞满时：把中间产物分流到各 Worker 的独立上下文，Manager 只在分解与合并两个轻环节接触它们。

三种情况不要用：

- 子任务之间有依赖顺序：先串行执行，或改用 Plan-and-Execute（先生成完整计划再按依赖执行的模式，见 08 实验）加拓扑排序（按依赖关系排出执行顺序的算法）。
- Worker 需要互相看到产出才能推进：改用群聊式编排（见下表）。
- 本地模型并发能力有限：Ollama（本地运行大模型的工具）默认把请求串行排队，多 Worker 带不来真加速。

| 方案 | 差异 | 什么时候选它 |
| :--- | :--- | :--- |
| 单 Agent 串行 | 全程一个上下文，顺序执行 | 任务简单、中间产物少 |
| Manager-Worker | 分解 + 并行 + 合并，上下文隔离 | 子任务独立、需要多角色视角 |
| 群聊式（AutoGen group chat） | 所有参与者互相可见，共同推进对话 | Worker 需要互看产出、协作修正 |
| Plan-and-Execute | 先生成完整计划，再按依赖逐步执行 | 子任务间有明确依赖顺序（见 08 实验） |

## Quick Start

前置条件：Python 3 环境；`--demo` 模式完全离线可跑，真实模式需要已配置可用的模型访问。

```bash
cd agents/25_manager_worker
python manager_worker.py --demo   # 离线：预置产出，编排结构真实运行（含并行计时）
python manager_worker.py          # 真实：asyncio 调研任务，2 Worker 并行
```

真实模式的诚实预期（默认任务：asyncio（Python 标准库的异步编程模块）入门调研）：Manager 分解出 researcher（收集概念）与 analyst（分析场景与坑）两个子任务。

两 Worker 并行执行（耗时 50.8s / 27.1s，墙钟 50.8s，而串行合计为 77.9s）；Manager 合并出带事件循环 / 协程（Python 异步编程的核心概念）与常见陷阱的完整入门文档。

demo 模式用预置产出加模拟延迟展示 2.0x 并行加速，不需要模型访问，适合先看编排结构是否按预期运转。

## How It Works

执行顺序就是 What 节表格的三段：分解、并行执行、合并。最核心的一处代码是执行层的线程池分发：

```python
def run_workers(subtasks):
    with ThreadPoolExecutor(max_workers=len(subtasks)) as pool:
        futures = [pool.submit(worker_execute, st) for st in subtasks]
        return [f.result() for f in futures]

def worker_execute(subtask):
    role = subtask.get("role", "researcher")
    prompt = ROLE_PROMPTS.get(role, ROLE_PROMPTS["researcher"])
    output = chat([{"role": "user", "content": f"{prompt}\n\n子任务: {subtask['task']}"}])
    return {"role": role, "task": subtask["task"], "output": output}
```

`run_workers` 把每个子任务提交进线程池，再用 `f.result()` 逐个收结果。

`worker_execute` 先按子任务的 `role` 字段查出角色提示词，再拼接子任务描述调用模型——每个 Worker 的输入只有自己的角色与子任务，看不到其他 Worker，也看不到原始任务全文，这就是 What 节所说的上下文隔离在代码层的形态。

为什么线程就能真并行：LLM（大语言模型）调用是 IO 密集型（大部分时间在等模型生成，而非占 CPU 计算），线程在等待网络返回时会让出执行权，多个请求得以同时在途。

这与 Quick Start 的现象互相印证：实测墙钟 50.8s ≈ 两个 Worker 中最慢者（50.8s）而非两者之和（77.9s），正是因为两个请求同时在途；demo 输出里的 2.0x 加速同样来自这处线程池。

合并阶段则由 Manager 接收全部产出，做去重、消解冲突、组织成最终文档。

## Pitfalls & Q&A

踩坑清单（现象 / 原因 / 解法）：

- 分解 JSON 解析失败。现象：Manager 返回的分解结果无法按 JSON 解析。原因：模型输出混入解释文字或格式漂移。解法：对分解输出做两级回退提取（同项目 08 的做法），解析失败降级为单 Worker 串行。
- 合并阶段上下文超载。现象：Worker 产出越多，合并质量越差甚至超出窗口。原因：Manager 的上下文等于所有 Worker 产出之和。解法：分段合并（map-reduce，先分块汇总再归并的思想），或让 Worker 直接产出高度压缩的摘要。
- 合并结果内容重复。现象：不同 Worker 写出雷同段落。原因：角色边界重叠导致产出交叠。解法：合并时强制去重消解，不做直接拼接。
- Worker 输出偏题。现象：Worker 跑出子任务范围。原因：子任务描述不自包含，写了"同上"这类指代——Worker 看不到原始任务，指代无处解析。解法：每条子任务描述都写成自包含的完整语句。
- 并行没有加速。现象：多 Worker 墙钟时间不下降。原因：本地模型（如 Ollama）默认串行排队，加速只来自请求重叠；生产环境多实例部署才能线性扩展。解法：换支持并发的推理服务，或接受排队等待。
- 在 Worker 内再开线程。现象：加速不变。原因：瓶颈在模型推理而非 CPU，线程内再并行没有收益。解法：并行度放在 Worker 这一层即可。

**Q1: Worker 之间需要通信吗？**

经典形态不需要——Worker 只看自己的子任务，通过 Manager 交换信息。需要 Worker 互看产出的场景应改用群聊式编排（AutoGen group chat，见 When to Use 的对比表）。
