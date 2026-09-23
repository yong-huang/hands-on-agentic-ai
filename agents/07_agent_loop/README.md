# 07 · Agent Loop 完整实现：事件流、scratchpad 与三类终止

> 把手写循环升级到生产形态——`Event/AgentResult` 结构化事件流、按
> "工具+入参"缓存的 scratchpad、答案质量判定与催促机制，三类终止
> （completed / max_steps / error）各自如实上报。

## What

生产级循环 = ReAct 循环 + 三件增补：

- **事件流**：每执行一步 `_emit()` 一条结构化事件
  （`THINK/ACTION/OBSERVATION/ANSWER/ERROR/MAX_STEPS` + step/tool/timestamp）；
- **scratchpad**：按"工具+入参"缓存的键值表——同一问题里第二次问
  "上海人口"零成本；`_scratchpad_summary()` 还能把"已获取：人口=2487 万；
  GDP=4.72 万亿"注入消息，让模型**知道自己已经拿到了什么**；
- **三类终止**，各自如实：

| reason | 触发 | 设计细节 |
| :--- | :--- | :--- |
| completed | 解析出 Answer 且长度 ≥10 | 防止"答案：略"式敷衍 |
| max_steps | 步数 ≥ max_steps(8) | 强制停止，结果里如实标注未完成 |
| error | API 调用失败 | 立即终止，不静默吞异常 |

主轨：接收任务 → 执行单步（事件流在此发射）→ 终止判定 → 组织答案 →
completed；未终止就带着 scratchpad 摘要回到单步。

心智模型一句话：**Agent Loop = ReAct 循环 + 黑匣子（事件流）+ 记事本
（scratchpad）+ 三岔路口（终止判定）。**

## Why

一个"能跑"的循环和一个"可运营"的循环之间隔着三件事：**可观测**（每
一步发生了什么）、**可复用**（同一工具同一参数不该问模型两遍）、**可
判定**（任务到底完成了没有）。这三件事也是所有 Agent 框架（LangGraph
的 state、LangSmith 的 trace）的内核——本篇用 500 行纯 Python 把它们
造出来。

## How

```bash
cd agents/07_agent_loop
python agent_loop.py                    # 默认：上海人均 GDP（多步推理）
python agent_loop.py --demo             # 离线模式：三种终止场景各演一遍
```

默认模式三步走：查人口（`GetPopulation(shanghai)`）→ 查 GDP、计算
（`Calculator(47218/2487)`）→ `Answer: 上海2023年人均GDP约为18.99万元`，
打印 `完成 — 共 4 步（调用 3 次工具）`。`--demo` 会依次演示 completed、
一步直答、max_steps 强停三种终止。

**催促机制**：工具已调 ≥3 次时，Observation 里附"已调用 N 次，数据够就
直接 Answer"——**给循环装上预算意识**，专治模型"再查一下"的强迫症。

**`AgentResult`：一次运行的完整体检报告**——`answer / steps / events /
success / reason` 五字段概括一次运行。"这个任务 agent 跑了几步、为什么
停"变成一次字段访问。项目 30 的评估框架直接复用这个结构跑批量评估。

核心结构：

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

## Deep Dive

**事件流不是日志**：事件流是结构化、有类型、带语义的第一方数据，可
程序化消费——终端打印只是它的一个订阅者，可视化（时序图/火焰图）、调试
回放、成本统计全都成了简单消费。**Agent 的可观测性是设计出来的，不是
事后 log 出来的。**

**scratchpad 与对话历史的区别**：历史是给模型看的完整上下文；scratchpad
是运行时的键值缓存，用于去重执行和生成"已获取信息"摘要，不一定全量进
prompt。

踩坑清单：

- `<think>` 标签必须先剥再解析，否则正则会把思考内容当 Action；
- Answer 长度阈值（≥10）按业务调：阈值太低挡不住敷衍，太高误杀短答案；
- 事件时间戳用 `time.time()`，跨场景统计时要统一时钟源。

## Q&A

**Q1: 生产级 Agent Loop 相比最小 ReAct 需要增加什么？**

结构化事件流（可观测）、中间结果缓存（scratchpad）、明确的终止判定与
结果结构、防呆机制（步数上限、答案质量阈值、催促）。

**Q2: 怎么判断 Agent"完成了任务"？**

轻量方案是格式约定（出现 Answer 且满足质量阈值）；严格方案是评审者模型
或规则校验（项目 26 的反思工作流）。

**Q3: max_steps 触发后应该返回什么？**

如实返回 `success=False, reason=max_steps` 并附已有 scratchpad 摘要，让
调用方决定重试/降级，而不是把半成品当答案。
