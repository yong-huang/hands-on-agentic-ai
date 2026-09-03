# 07 · Agent Loop 完整实现：事件流、scratchpad 与三类终止

> 项目 06 的 ReAct 能跑，但它是"黑盒"：跑了几步、哪步失败、重复查询有没有
> 浪费，全都无从得知。本篇把手写循环升级到生产形态——`Event/AgentResult`
> 结构化事件流、按"工具+入参"缓存的 scratchpad、答案质量判定与催促机制，
> 三类终止（completed / max_steps / error）各自如实上报。

## 1. 为什么需要它

一个"能跑"的循环和一个"可运营"的循环之间隔着三件事：**可观测**（每一步
发生了什么）、**可复用**（同一工具同一参数不该问模型两遍）、**可判定**
（任务到底完成了没有）。这三件事分别对应事件流、scratchpad、终止条件——
它们也是所有 Agent 框架（LangGraph 的 state、LangSmith 的 trace）的内核。
本篇用 500 行纯 Python 把它们造出来。

## 2. 总览：核心机制一图看懂

![Agent Loop 状态机](images/agent_loop_states.lifecycle.svg)

**怎么看这张图**：主轨四步——接收任务 → 执行单步（事件流在此发射）→ 终止
判定 → 组织答案 → completed。未终止就带着 scratchpad 摘要回到单步；"步数
≥ max_steps"是强制出口；"LLM 无响应"是异常出口。

心智模型一句话：**Agent Loop = ReAct 循环 + 黑匣子（事件流）+ 记事本
（scratchpad）+ 三岔路口（终止判定）。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/07_agent_loop/images/agent_loop_states.lifecycle.html)（或本地打开 [`images/agent_loop_states.lifecycle.html`](images/agent_loop_states.lifecycle.html)）。

## 3. 快速开始

```bash
cd agents/07_agent_loop
python agent_loop.py                    # 默认：上海人均 GDP（多步推理）
python agent_loop.py --demo             # 离线模式：三种终止场景各演一遍
```

脚本依次做三件事（默认模式）：

1. 第 1 步查人口（`GetPopulation(shanghai)`）；
2. 第 2 步查 GDP（`GetGDP(shanghai)`）、第 3 步计算（`Calculator(47218/2487)`）；
3. 第 4 步给出 `Answer: 上海2023年人均GDP约为18.99万元`，打印
   `完成 — 共 4 步（调用 3 次工具）`。

`--demo` 会依次演示 completed、一步直答、max_steps 强停三种终止。

## 4. 核心概念

### 4.1 事件流：把执行轨迹变成数据

```python
class EventType(Enum): THINK / ACTION / OBSERVATION / ANSWER / ERROR / MAX_STEPS

@dataclass
class Event:
    step: int; event_type: EventType; content: str
    tool: str; tool_input: str; timestamp: float
```

每执行一步就 `_emit()` 一条事件。有了事件流：终端打印只是它的一个订阅者，
可视化（时序图/火焰图）、调试回放、成本统计全都成了简单消费。**Agent 的
可观测性是设计出来的，不是事后 log 出来的。**

### 4.2 scratchpad：按"工具+入参"缓存

`_execute_tool()` 先查 `scratchpad[tool][input]`，命中直接返回缓存——同一
问题里第二次问"上海人口"零成本。更妙的是 `_scratchpad_summary()`：解析失败
或催促时，把"已获取：人口=2487 万；GDP=4.72 万亿"注入消息，让模型**知道自己
已经拿到了什么**，避免重复行动或凭空编造。

### 4.3 三类终止，各自如实

| reason | 触发 | 设计细节 |
| :--- | :--- | :--- |
| completed | 解析出 Answer 且长度 ≥10 | 防止"答案：略"式敷衍 |
| max_steps | 步数 ≥ max_steps(8) | 强制停止，结果里如实标注未完成 |
| error | API 调用失败 | 立即终止，不静默吞异常 |

催促机制：工具已调 ≥3 次时，Observation 里附"已调用 N 次，数据够就直接
Answer"——**给循环装上预算意识**，专治模型"再查一下"的强迫症。

### 4.4 `AgentResult`：一次运行的完整体检报告

`answer / steps / events / success / reason` 五字段概括一次运行。有了它，
"这个任务 agent 跑了几步、为什么停"变成一次字段访问。项目 30 的评估框架
会直接复用这个结构跑批量评估。

## 5. 代码关键部分

```python
def _emit(self, event_type, content, tool=None, tool_input=None):
    self.events.append(Event(step=self.step, event_type=event_type, content=content,
                             tool=tool, tool_input=tool_input, timestamp=time.time()))

def run(self, question):
    self.messages.append({"role": "user", "content": question})
    for self.step in range(1, self.max_steps + 1):
        text = self._call_llm()                      # 失败返回 None → reason=error
        parsed = parse_react_output(self._clean_response(text))
        if parsed["type"] == "answer":
            return AgentResult(answer=parsed["content"], success=True, reason="completed", ...)
        # Action: 执行(带 scratchpad) → Observation 回喂 → 下一轮
    return AgentResult(success=False, reason="max_steps", ...)
```

坑清单：

- `<think>` 标签必须先剥再解析，否则正则会把思考内容当 Action；
- Answer 长度阈值（≥10）按业务调：阈值太低挡不住敷衍，太高误杀短答案；
- 事件时间戳用 `time.time()`，跨场景统计时要统一时钟源。

## 6. 文件结构

```
07_agent_loop/
├── README.md                            # 本篇教程
├── agent_loop.py                        # 主脚本（约 520 行）：事件流 + scratchpad + 循环
└── images/
    ├── agent_loop_states.lifecycle.json # 图源：lifecycle 类型（状态机）
    ├── agent_loop_states.lifecycle.html # 交互版架构图
    └── agent_loop_states.lifecycle.svg  # 双主题矢量图
```

## 7. 面试要点

- **Q: 生产级 Agent Loop 相比最小 ReAct 需要增加什么？**
  A: 结构化事件流（可观测）、中间结果缓存（scratchpad）、明确的终止判定
  与结果结构、防呆机制（步数上限、答案质量阈值、催促）。
- **Q: scratchpad 和"对话历史"有什么区别？**
  A: 历史是给模型看的完整上下文；scratchpad 是运行时的键值缓存，用于去重
  执行和生成"已获取信息"摘要，不一定全量进 prompt。
- **Q: 怎么判断 Agent "完成了任务"？**
  A: 轻量方案是格式约定（出现 Answer 且满足质量阈值）；严格方案是评审者
  模型或规则校验（项目 26 的反思工作流）。
- **Q: max_steps 触发后应该返回什么？**
  A: 如实返回 `success=False, reason=max_steps` 并附已有 scratchpad 摘要，
  让调用方决定重试/降级，而不是把半成品当答案。
- **Q: 事件流和日志的区别？**
  A: 事件流是结构化、有类型、带语义的第一方数据，可程序化消费；日志是
  面向人的文本。可观测体系应从事件流设计开始。

## 8. 总结

事件流让循环可观测，scratchpad 让它不浪费，三类终止让它诚实。手写的这个
循环，就是 LangGraph 状态机的"裸金属版"。下一篇换一种活法：把这些全部
交给 LangChain 框架托管，对比着理解框架到底替你做了什么。
