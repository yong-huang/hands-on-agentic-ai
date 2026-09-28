# 07 · Agent Loop 完整实现：事件流、scratchpad 与三类终止

> 把最小可用的模型-工具循环补齐到可运营形态：每一步留下可回放的结构化记录、
> 重复查询不再重复消耗模型调用、三种停止原因如实上报。读完本篇，你能用纯
> Python 写出一个可观测、可复用、能判定"任务完成了没有"的完整智能体循环。

## Background

在没有本篇这层封装之前，一个手写的智能体（Agent，能自主决定调用哪些工具来完成任务的大模型程序）循环通常是这样的：把用户问题发给大模型，模型输出"思考 + 要调的工具名"，代码解析后执行工具，把结果拼回对话再问模型，如此往复直到模型给出答案。过程信息全靠 `print` 打到终端，跑完返回一个字符串。

这种写法在演示里能跑，接到真实任务时会在三处撞墙：

- **出了问题只能翻终端滚屏。** `print` 出来的文字没有类型、没有步骤号，无法程序化分析，也回放不出"第 3 步模型到底看见了什么"。
- **同一个工具被反复调用。** 模型常有"再查一下"的倾向：同一参数查两遍，每次都是一次真实的 API 调用（API 即程序访问外部服务的接口，这里指按次计费的大模型服务），付出真实费用和时延。
- **循环不知道任务是否真的完成。** 模型可能回一句"答案：略"就停，也可能无限查下去，直到调用方失去耐心。

生产级 Agent 框架正是围绕这三个缺口构建的：LangGraph（把智能体流程编排成图结构的框架）用状态对象承载循环进度，LangSmith（大模型应用的追踪与观测平台）负责记录每次调用。本实验不引入框架，用 500 行纯 Python 把这三块内核实现出来。

## What

本篇主题是生产级 Agent Loop（智能体循环）。定义：**Agent Loop 是一种让大模型反复"思考 → 调用工具 → 看结果"直到给出最终答案的控制结构；生产级形态 = 最小 ReAct 循环 + 三件增补。**

先解释 ReAct（Reason + Act，"先思考、后行动"的循环范式）：模型每轮输出思考（Thought）和动作（Action，通常是一次工具调用），代码执行动作后，把工具返回的内容（Observation，观察结果）回喂给模型，进入下一轮。

三件增补：

- **事件流**：每执行一步，用 `_emit()` 发出一条结构化事件——类型为
  `THINK/ACTION/OBSERVATION/ANSWER/ERROR/MAX_STEPS` 之一，附带步骤号
  （step）、工具名（tool）、入参和时间戳（timestamp）；
- **scratchpad**（草稿纸）：按"工具+入参"为键的运行期缓存表。可以把
  scratchpad 想象成侦探破案时摊在桌上的记事本：查过的线索记一笔，再遇到
  同样的问题直接翻本子，不去重问证人；
- scratchpad 的第二个用途是**让模型知道自己拿到了什么**：`_scratchpad_summary()`
  把缓存汇总成"已获取：人口=2487 万；GDP=4.72 万亿"这样的摘要注入消息，
  但和普通记事本只供人翻阅不同的是，摘要会跟随下一步请求一起发给模型——
  同一问题里第二次问"上海人口"因此零成本；
- **三类终止**，各自如实：

| reason | 触发 | 设计细节 |
| :--- | :--- | :--- |
| completed | 解析出 Answer 且长度 ≥10 | 防止"答案：略"式敷衍 |
| max_steps | 步数 ≥ max_steps(8) | 强制停止，结果里如实标注未完成 |
| error | API 调用失败 | 立即终止，不静默吞异常 |

主轨：接收任务 → 执行单步（事件流在此发射）→ 终止判定 → 组织答案 →
completed；未终止就带着 scratchpad 摘要回到单步。

心智模型一句话：**Agent Loop = ReAct 循环 + 黑匣子（事件流）+ 记事本
（scratchpad）+ 三岔路口（终止判定）。** 黑匣子指飞机上的飞行记录仪——
但与它"失事后才取出读取"不同的是，事件流在运行过程中就持续产出，可以
边跑边消费。

## When to Use

这节回答：什么场合值得给循环加上这三件增补，什么场合不必。

典型场景：

- **要把 Agent 接进业务系统**：调用方需要的不是一段终端打印，而是"跑了
  几步、为什么停、成功了没"这样的结构化结果；
- **工具按次计费或响应慢**（搜索、付费 API）：scratchpad 的去重与催促
  机制直接决定成本和时延；
- **线上排查"为什么答错"**：需要按步骤回放模型每一步看见了什么，事件流
  让回放成为一次列表遍历。

何时不用：

- 只验证一个想法、跑一次性脚本：最小 ReAct 循环加 `print` 更省事，三件
  增补在此时是纯开销；
- 团队已选定成熟框架、也不要求理解内部机制：直接使用框架的编排与观测
  能力，不必手写。

同类方案对比：

| 方案 | 差异 | 什么时候选它 |
| :--- | :--- | :--- |
| 最小 ReAct 循环 | 只有主流程，过程靠 `print`，无缓存、无终止判定 | 学原理、写一次性脚本 |
| 本实验的生产级循环 | 500 行纯 Python，自带事件流、scratchpad、三类终止 | 要逐行掌控行为，不想引入框架依赖 |
| LangGraph | 把循环编排成状态图，自带检查点（把运行状态存盘以便断点续跑）、分支与持久化（数据存盘、重启不丢） | 生产系统需要复杂流程编排与状态恢复 |
| LangSmith | 托管式追踪平台（记录一次请求的完整调用链），不改代码即可采集 | 系统已上线，需要集中监控与评估 |

## Quick Start

前置条件：本地装有 Python 3；默认模式需要本地 Ollama 已启动且已执行 ollama pull qwen3.8:latest（脚本请求 localhost:11434，无需 API Key）；--demo 为离线模式，不调用外部接口。

```bash
cd agents/07_agent_loop
python agent_loop.py                    # 默认：上海人均 GDP（多步推理）
python agent_loop.py --demo             # 离线模式：三种终止场景各演一遍
```

默认模式的诚实预期：任务是"上海人均 GDP"，循环分三步走——查人口
（`GetPopulation(shanghai)`）→ 查 GDP、计算（`Calculator(47218/2487)`）→
`Answer: 上海2023年人均GDP约为18.99万元`，最后打印
`完成 — 共 4 步（调用 3 次工具）`。

`--demo` 会依次演示 completed、
一步直答、max_steps 强停三种终止。

你在输出里看到的"完成 — 共 4 步（调用 3 次工具）"，就是主循环结束时对
`events` 列表的汇总统计——它为什么能被这样统计，见 How It Works。

两个内建机制，跑之前值得知道：

- **催促机制**：工具已调用 ≥3 次时，程序在 Observation 里附加
  "已调用 N 次，数据够就直接 Answer"。这给循环装上预算意识，抑制模型
  "再查一下"的倾向。
- **`AgentResult`：一次运行的完整体检报告**——`answer / steps / events /
  success / reason` 五字段概括一次运行。"这个任务 agent 跑了几步、为什么
  停"变成一次字段访问。30 实验的评估框架直接复用这个结构跑批量评估。

## How It Works

这节按执行顺序拆开 `run()` 主循环，再解释两处关键设计，并与你刚在终端
看到的现象互相印证。

一次运行的执行顺序：

1. 用户问题进入对话消息列表 `messages`；
2. 进入步数受限的循环（最多 `max_steps = 8` 步），每步先调用模型；
3. 模型调用失败返回 `None`，循环立即以 `reason="error"` 终止——这就是
   上表第三类终止"不静默吞异常"的落点；
4. 解析模型输出：是 answer 则返回 `reason="completed"` 的结果；是 action
   则执行工具、发射事件、把 Observation 回喂、进入下一轮；
5. 步数耗尽仍未得到答案 → `reason="max_steps"`。

核心代码与执行顺序一一对应：

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

`_emit` 只做一件事：把当前步骤号、事件类型、内容、工具信息与时间戳装进
一个 `Event` 对象，追加到 `events` 列表；单步路径上的思考、动作、观察各
调用它一次。

你在终端看到的每一行过程，都是这份列表的一个订阅者；
"共 4 步"就是 `self.step` 的终值，"调用 3 次工具"就是 `events` 里
ACTION 事件的计数。

**事件流不是日志**：事件流是结构化、有类型、带语义的第一方数据，可程序
化消费——终端打印只是它的一个订阅者，可视化（时序图/火焰图，后者是一种
按调用栈层级展示耗时分布的图表）、调试回放、成本统计全都成了简单消费。
**Agent 的可观测性是设计出来的，不是事后 log 出来的。**

**scratchpad 与对话历史的区别**：历史是给模型看的完整上下文；scratchpad
是运行时的键值缓存，用于去重执行和生成"已获取信息"摘要，不一定全量进
prompt。

## Pitfalls & Q&A

踩坑清单，每条按"现象 → 原因 → 解法"：

- **现象：解析出的 Action 里混着模型的思考文字。** 原因：`<think>` 标签
  的内容没有先剥掉，正则会把思考内容当 Action。解法：先剥离 `<think>`
  标签，再进解析函数。
- **现象：明显的短答案被拒，循环继续空转。** 原因：Answer 长度阈值（≥10）
  过高，误杀合法短答案。解法：按业务调阈值——太低挡不住"答案：略"式
  敷衍，太高误杀短答案。
- **现象：跨机器统计事件耗时出现偏差。** 原因：事件时间戳取自
  `time.time()`，依赖系统时钟。解法：跨场景统计时统一时钟源。

深入问答：

**Q: 怎么判断 Agent"完成了任务"？**

轻量方案是格式约定：出现 Answer 且满足质量阈值（本实验的做法）。严格
方案是引入评审者模型（用一个额外的模型实例来评判答案质量）或规则校验
（26 实验的反思工作流即此类）。

**Q: max_steps 触发后应该返回什么？**

如实返回 `success=False, reason=max_steps`，并附已有 scratchpad 摘要，
让调用方决定重试或降级——而不是把半成品当答案。
