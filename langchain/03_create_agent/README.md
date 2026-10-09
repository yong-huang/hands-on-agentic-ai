# 03 · create_agent：工具绑定与 Agent Loop 内核

> `create_agent`（LangChain 的 Agent 构造器）把"模型决定调用哪个工具、代码执行、结果回填、再决策"的循环整个托管起来，开发者只写工具与提示词。
> 本篇从最底层的工具契约开始：`@tool` 生成 schema（机器可读的参数结构描述：每个参数的类型与用途）、`bind_tools` 让模型返回结构化 tool_calls（调用请求：调哪个工具、参数是什么）、`create_agent` 组装完整循环；并用"查询工具失败 → 改用估算工具"的真实任务验证失败回退。
> 读完你能分清循环里每一步由谁负责，以及框架出错策略的默认行为。

## Background

裸调模型接口时，模型只输出文本。"让模型用工具"的早期做法是自己约定一套文本协议：提示词要求输出 `动作: 搜索 / 参数: xxx`，代码用正则解析、执行、把结果拼回对话，再进下一轮——仓库里 06/07 实验的手写循环就是这套做法。

痛点在规模上来后暴露：解析器、循环控制、消息拼接全是与业务无关的样板代码；模型换一种措辞，正则就要跟着改。这类"把文本当协议"的脆弱性正是模型厂商推出 function calling 的动机。

function calling 让模型按结构化格式（JSON 的 tool_calls 字段）声明"我要调用哪个工具"，框架负责生成工具说明书、执行调用、把结果回填。LangChain 把这条链路收进一个构造函数：`create_agent`。

## What

`create_agent` 是一个 Agent 构造器：输入模型、工具列表与系统提示词，输出一个 LangGraph 状态机（用共享状态驱动的流程引擎）；状态就是消息列表，节点决定每一步做什么。

可以把循环想象成调度台：模型是调度员，拿到"任务 + 工具说明书"，每次只决定"下一步做什么"；代码是执行员，照着调度指令把活干了、把结果贴回任务单。但和人类调度台不同的是：调度员是概率模型，它可能选错工具、跳过工具甚至编造结果——这是所有工程手段要处理的现实。

四个部件的分工：

| 部件 | 职责 | 证据 |
|:--|:--|:--|
| `@tool` 装饰器 | 从函数签名生成参数 schema | `[A]` 段打印的 `expression` 描述 |
| `bind_tools` | 把工具 schema 绑进模型请求 | `[B]` 段模型返回的 tool_calls |
| `ToolNode` | 执行 tool_calls、把结果变成工具消息 | `[A]` 段的错误 ToolMessage |
| 消息列表 | 循环的共享状态，逐轮追加 | `[C]` 段打印的完整轨迹 |

## When to Use

典型场景：

1. 任务步骤不确定：如"查价格，查不到就想别的办法"，需要模型根据中间结果临场决策。
2. 工具选择由语义决定：多个查询工具中调哪个，写 if/else 不如让模型读问题后选。
3. 快速搭原型：一个函数得到一个可用的 ReAct 风格 Agent（ReAct：模型交替进行推理与工具调用的经典 Agent 工作模式），再逐步加约束。

何时不用：单次调用就能完成的任务（一次 `invoke` 足够）；流程完全确定的管线（写死函数调用更便宜、更可测）。

同类方案对比：

| 方案 | 控制粒度 | 什么时候选它 |
|:--|:--|:--|
| 手写文本协议 + while 循环 | 全部自己写 | 学习原理（见仓库 06/07 实验） |
| `bind_tools` + 自己写循环 | 循环自己管 | 循环要加特殊逻辑（统计、审计、熔断——连续失败达到阈值时主动中止循环） |
| `create_agent`（本篇） | 工具与提示词 | 标准 tool-calling 循环够用时 |
| LangGraph 自定义图 | 每个节点与边 | 循环外还有复杂编排（见后续实验） |

## Quick Start

前置条件：依赖已装在仓库根 `.venv`（版本清单见 [docs/langchain.md](../../docs/langchain.md) 的「环境配置」节）。

真机模式需要本机 Ollama（在本地运行大语言模型的服务）已启动且已拉取 `qwen3.8:latest`。

```bash
cd langchain/03_create_agent
source ../../.venv/bin/activate         # 依赖装在仓库根 .venv；也可直接用 ../../.venv/bin/python
python3 create_agent.py                 # 真机：A 离线 + B/C 调模型
python3 create_agent.py --demo          # 离线：A 段 + 手动装配一次循环
```

真实输出（节选：省略全部分隔线）：

```text
[03] create_agent：工具绑定与 Agent Loop 内核
模式: 真机（qwen3.8:latest）

[A] 工具契约与 ToolNode 错误策略（离线）
  calculator schema 属性: ['expression']
    expression 描述: 要计算的数学表达式，如 '6 * 7'
  ✅ @tool 从函数签名与注解生成参数 schema
  ✅ ToolNode 默认策略：工具异常原样抛出 — RuntimeError(价格服务不可用 (503))
  handle_tool_errors=True -> ToolMessage status=error
    content: Error: RuntimeError('价格服务不可用 (503)')
 Please fix your mistakes.
  ✅ handle_tool_errors=True 转成错误 ToolMessage

[B] bind_tools：模型返回结构化 tool_calls（真机）
  tool_calls: [('calculator', {'expression': '6 * 7'})]
  ✅ 模型按工具请求格式返回 tool_calls

[C] create_agent：查询失败 → 改用估算 → 汇报（真机）
  消息轨迹：
    HumanMessage 帮我查一下 apple 的价格。
    AIMessage    -> tool_calls ['fetch_price']
    ToolMessage  [fetch_price] ERROR: 实时价格服务不可用 (503)。请调用 estimate_price 工具获取估算
    AIMessage    -> tool_calls ['estimate_price']
    ToolMessage  [estimate_price] 4.5
    AIMessage    Apple 的实时价格服务暂不可用，根据历史数据估算其价格约为 4.5 元。
  ✅ 查询失败后模型改用估算工具 — 工具调用=['fetch_price', 'estimate_price']
  ✅ 最终报告包含估算价格 4.5 — final=Apple 的实时价格服务暂不可用，根据历史数据估算其价格约为 4.5 元。
  ✅ 消息序列呈现 模型→工具→模型 循环 — 模型发起工具调用 2 次

验收: 7/7 通过 ✅
```

诚实预期：`[C]` 段依赖模型的工具选择行为，属概率性输出；脚本连跑多次均 7/7，但换更小的模型可能失败（见踩坑 3）。整轮真机约 5-15 秒（本机实测：模型已加载约 4.5 秒，冷启动约 11 秒；换机或首次加载可能更慢）。Ollama 未启动时真机部分跳过（退出码 2），`--demo` 全程离线。

## How It Works

### 工具说明书是怎么生成的

`@tool` 读取函数签名与 `Annotated` 注解（Python 的类型标注语法，可附加参数说明），生成 JSON Schema。`[A]` 段打印的 `expression 描述: 要计算的数学表达式…` 就是模型实际看到的说明书内容——模型选错工具时，先检查这里写得是否清楚。

### 循环的三段结构

一次 `agent.invoke` 内部是"模型决策 → 工具执行 → 结果回填"的循环，任务在两步工具调用后收敛：

![create_agent 的 Agent Loop：查询失败后回退估算](images/agent_loop.sequence.svg)

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/langchain/03_create_agent/images/agent_loop.sequence.html)
> （或本地打开 [`images/agent_loop.sequence.html`](images/agent_loop.sequence.html)）。

循环的终止条件是"某轮模型不再返回 tool_calls，而是给出文本"——`[C]` 段最后一条 `AIMessage` 就是终止信号。整个轨迹可从 `result["messages"]` 逐条核对，这也是调试 Agent 的第一手段。

### 工具出错时的两种策略

ToolNode（LangGraph 中执行工具调用的节点）对"工具抛异常"有两种策略，对应 `[A]` 段的两条断言：

- **默认**：异常原样抛出，整个 Agent 运行中断——适合"工具坏了就该停"的场景；
- **`handle_tool_errors=True`**：把异常转成一条 `status="error"` 的工具消息，模型能读到"这一步失败了"并调整。

`create_agent` 底层用的是默认策略。所以工具自己应尽量把可预期的失败**以文本返回**（如 `fetch_price` 返回 `ERROR:` 开头的话），把异常留给真正意外的情况。`[C]` 段里模型能改用估算工具，靠的就是这条错误文本。

错误文本要"可执行"：实验最初只返回 `ERROR: 实时价格服务不可用 (503)`，模型回复"我改用估算"却直接编了个 8.5 元——它知道要换算，但没意识到要调用工具；把错误文本改成"请调用 estimate_price 工具获取估算价格"，模型才稳定地发起第二次工具调用。

## Pitfalls & Q&A

### 踩坑清单

1. **工具抛异常会让整个 Agent 崩**。现象：`RuntimeError` 直接冒泡，循环中断。原因：`ToolNode` 默认不吞异常，`create_agent` 也沿用默认。解法：工具内返回错误文本，或自建 ToolNode 时配 `handle_tool_errors=True`。
2. **模型可能绕过工具直接编结果**。现象：错误文本含糊时，模型嘴上说"改用估算"，实际输出了自己编的数字。原因：模型对"必须调用工具"的约束遵守度取决于提示强度。解法：系统提示词写死"数字必须来自工具返回值"；工具错误文本直接给出下一步指令。
3. **小模型不触发工具调用**。现象：换 `qwen3:4b` 后模型直接输出文本答案，tool_calls 始终为空。原因：参数规模小的模型 function calling 能力弱。解法：工具类实验统一用 `qwen3.8:latest`；4b 留给纯文本任务。

### 深入问答

**Q：`create_agent`、`bind_tools` 手写循环、LangGraph 自定义图怎么选？**

按控制粒度递进：标准循环够用选 `create_agent`；需要在循环里插统计、审计、熔断等逻辑，可以 `bind_tools` 后自己写 while 循环。

需要循环之外的编排（条件分支、人工审批、断点恢复）再上 LangGraph 自定义图。三者不互斥，`create_agent` 产物本身就是一张 LangGraph 图。

**Q：工具数量多了怎么保证选对？**

两类手段：提升说明书质量（名称、docstring、参数描述都写成"给模型的文档"）；控制候选数量——把 20 个工具全部暴露会稀释模型的注意力，可以按场景动态筛选（后续 04 实验的中间件会演示工具级控制）。改完务必用固定任务集回归，而不是凭感觉。
