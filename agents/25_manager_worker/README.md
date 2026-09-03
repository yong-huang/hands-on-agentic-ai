# 25 · Manager-Worker：任务分解与并行协作

> 单个 Agent 做复杂任务时，上下文会超载——调研、分析、撰写全堆在一个对话里，
> 后面的内容挤掉前面的。Manager-Worker 模式把"分工"与"执行"分离：Manager
> (LLM) 把任务分解成带角色的子任务，多个 Worker（各自带角色提示词）用线程池
> **真并行**执行，Manager 再合并所有产出。真机实测：两个 Worker 并行，墙钟
> 50.8s vs 串行 77.9s，合并产出结构化入门文档。

## 1. 为什么需要它

上下文窗口是共享的稀缺资源：一个 Agent 干三件事，每件事的中间产物都在互相
抢占空间。Manager-Worker 让每个 Worker 只看到自己的子任务（上下文干净、
专注单一职责），Manager 只处理"分解"与"合并"两个轻环节。这也是
Claude Code 的 subagent、AutoGen 的 group chat 背后的同一模式。

## 2. 总览：核心机制一图看懂

![Manager-Worker 协作](images/manager_worker.workflow.svg)

**怎么看这张图**：用户任务进入管理泳道，Manager 先分解成带角色的子任务
（JSON），每个子任务分派到独立的 Worker 泳道**并行**执行（ThreadPoolExecutor），
全部完成后产出回流管理泳道，由 Manager 合并成最终产出。

心智模型一句话：**Manager 只分工与合并，Worker 只管自己那一摊——上下文
隔离就是并行协作的全部秘密。**

🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/25_manager_worker/images/manager_worker.workflow.html)（或本地打开 [`images/manager_worker.workflow.html`](images/manager_worker.workflow.html)）。

## 3. 快速开始

```bash
cd agents/25_manager_worker
python manager_worker.py --demo   # 离线：预置产出，编排结构真实运行（含并行计时）
python manager_worker.py          # 真实：asyncio 调研任务，2 Worker 并行
```

**真机实测**（默认任务：asyncio 入门调研）：Manager 分解出 researcher
（收集概念）与 analyst（分析场景与坑）两个子任务；两 Worker 并行执行
（50.8s / 27.1s，墙钟 50.8s vs 串行合计 77.9s）；Manager 合并出带
事件循环 / 协程 / 常见陷阱的完整入门文档。demo 模式用模拟延迟展示 2.0x
并行加速。

## 4. 核心概念

### 4.1 三段编排

| 阶段 | 角色 | 做什么 |
| :--- | :--- | :--- |
| 分解 | Manager | 任务 → 2-3 个带角色的子任务（JSON） |
| 执行 | Workers | 各自带角色提示词，ThreadPoolExecutor 真并行 |
| 合并 | Manager | 去重、消解冲突、组织成最终产出 |

### 4.2 角色提示词：上下文隔离的关键

每个 Worker 的 system 提示词只描述自己的职责（researcher 只输出事实清单、
analyst 只输出分析要点）——**Worker 之间互相不可见**，所以上下文互不污染、
结果天然去冗余。角色池可扩展（writer/critic/...），Manager 按任务挑角色。

### 4.3 并行：为什么线程就够

LLM 调用是 IO 密集型（等模型生成），`ThreadPoolExecutor` 即可实现真并行
——实测两个 Worker 墙钟时间 ≈ 最慢者而非之和。**易错点**：Worker 内再开
线程无意义，瓶颈在模型推理而非 CPU。

### 4.4 已知边界

- Worker 数量受本地模型并发能力限制（Ollama 默认串行排队，墙钟加速来自
  请求重叠）；生产环境多实例部署才能线性扩展；
- 子任务有依赖时不适用（先串行，或 08 的 Plan-and-Execute + 拓扑排序）；
- 合并阶段 Manager 的上下文 = 所有 Worker 产出之和，产出过大需分段合并。

## 5. 代码关键部分

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

坑清单：

- Manager 的分解 JSON 要做两级回退提取（同项目 08），解析失败降级为单 Worker；
- Worker 产出合并时要"去重消解"——不同 Worker 可能写出重复内容；
- 子任务描述要自包含（Worker 看不到原始任务），别写"同上""如前所述"。

## 6. 文件结构

```
25_manager_worker/
├── README.md                            # 本篇教程
├── manager_worker.py                    # 主脚本（约 190 行）：分解 + 并行 + 合并
└── images/
    ├── manager_worker.workflow.json     # 图源：workflow 类型（管理/Worker 泳道）
    ├── manager_worker.workflow.html     # 交互版架构图
    └── manager_worker.workflow.svg      # 双主题矢量图
```

## 7. 面试要点

- **Q: Manager-Worker 模式的核心收益是什么？**
  A: 上下文隔离（每个 Worker 上下文干净且专注）+ 真并行（IO 密集的 LLM
  调用可线程池并发）+ 职责复用（角色提示词可沉淀复用）。
- **Q: Worker 之间需要通信吗？**
  A: 经典形态不需要——Worker 只看自己的子任务，通过 Manager 交换信息；
  需要 Worker 互看产出的场景应改用群聊式（如 AutoGen group chat）编排。
- **Q: 并行用什么原语？为什么？**
  A: LLM 调用是 IO 密集，ThreadPoolExecutor 即可真并行；CPU 密集才需要
  进程池。注意本地推理服务的实际并发上限。
- **Q: 子任务之间有依赖怎么办？**
  A: 拓扑排序后分层并行（无依赖层并行，层间串行），或退回 Plan-and-Execute
  顺序执行 + 显式 {{N}} 引用。
- **Q: Manager 合并时的最大风险？**
  A: 上下文超载——所有 Worker 产出之和要进 Manager 的窗口；产出过大应
  分段合并（map-reduce），或让 Worker 直接产出高度压缩的摘要。

## 8. 总结

Manager 负责分工与合并，Worker 负责并行与专注——上下文隔离换来了质量与
速度的双重收益。至此第六过半：你已经有状态图（24）和多 Agent 协作（25）
两把编排武器。下一篇是辩论式多 Agent（27 的前置是 26 的工作流编排）——
继续第六阶段。
