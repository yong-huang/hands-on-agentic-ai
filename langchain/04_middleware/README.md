# 04 · Middleware：Agent 运行时钩子

> Middleware（中间件：注册在 Agent 循环各环节上的钩子集合；Agent 循环指"模型调用→执行工具→再让模型决定"的重复过程，钩子即框架在固定时机回调你注册的函数）是 LangChain 1.x 的招牌能力：不用改循环代码，就能在"模型调用前""工具执行时"等位置插入计数、拦截、限次、重试等逻辑。
> 本篇写三个自定义中间件——观察计数、策略拦截、叠加顺序——再实测两个预置中间件：`ModelCallLimitMiddleware` 截断超限循环、`ToolRetryMiddleware` 自动重试瞬时失败的工具。
> 读完你能把"策略"从工具函数里搬进中间件，并知道钩子的触发次序。

## Background

写 Agent 时总有一批需求不属于任何一个工具：危险操作要拦、模型调用次数要限、瞬时失败要自动重试、每次调用要计数。03 实验的对策是在工具内返回错误文本、在提示词里写约束——能跑，但策略散落在每个工具里，改一条规则要翻多个文件。

更早的做法是改循环本身：把框架的循环代码 fork 出来插入自己的判断。代价是跟随框架升级的成本，以及每次新增一条规则就动一次核心逻辑。

LangChain 1.0 把这类"横切关注点"收进 Middleware：框架在循环的固定位置暴露钩子，逻辑注册进去即可，循环本体不动。官方在 1.0 发布说明里把它称为本次最大的新抽象。

## What

Middleware 是一组钩子的集合，每个钩子绑定循环中的一个时机；钩子可以观察状态、修改状态，也可以拦截或替换某一步的结果。

可以把钩子想象成流水线上每个工位前后的检查点：料来了先过一道（模型调用前），加工完再过一道（模型调用后）。但和固定检查点不同的是：钩子还能"截停流水线"或"把不合格件换成替代件"——限次中间件会终止循环，策略中间件会替换工具结果。

循环上的六个钩子（本篇演示 `before_model`、`wrap_tool_call`、`after_model` 三个）：

| 钩子 | 触发时机 | 典型用途 |
|:--|:--|:--|
| `before_model` | 每次模型调用前 | 计数、改提示词、裁剪上下文（删减或摘要过长的历史消息） |
| `wrap_tool_call` | 工具执行前后（包裹） | 拦截黑名单、重试失败 |
| `after_model` | 每次模型响应后 | 校验输出、记录用量 |
| `wrap_model_call` | 模型调用前后（包裹） | 改请求参数、降级模型 |
| `before_agent` / `after_agent` | 整个运行的首尾 | 加载记忆、清理资源 |

预置中间件按用途分三类。安全类：`HumanInTheLoopMiddleware`（危险工具执行前暂停、等人工审批）与 `PIIMiddleware`（PII 即个人身份信息，检测并遮蔽敏感数据）。

预算与可靠性：`ModelCallLimitMiddleware` 限制模型调用次数；`ToolRetryMiddleware` 失败自动重试；`SummarizationMiddleware` 压缩过长对话。

## When to Use

典型场景：

1. 工具级权限：把危险工具拉黑名单，触发时返回"被策略拦截"而不是执行。
2. 预算与风控：限制一次运行的模型调用次数，超限截断，防止循环失控烧钱。
3. 可靠性兜底：网络类工具瞬时失败自动重试，业务代码不用写 try/except。

何时不用：工具自身的业务校验（参数合法性、路径安全）应留在工具内；只影响一次调用的简单逻辑，直接写在调用处更直观。

同类方案对比：

| 方案 | 生效范围 | 什么时候选它 |
|:--|:--|:--|
| 工具内 if/else | 单个工具 | 业务规则，与工具强绑定 |
| 中间件（本篇） | 全部模型/工具调用 | 跨工具的横切策略 |
| 自定义 LangGraph 节点（LangGraph：配套的图编排框架；节点=图中的一个处理步骤） | 自己编排的图 | 需要改变循环走向（加分支、并行） |

## Quick Start

前置条件：依赖已装在仓库根 `.venv`（版本清单见 [docs/langchain.md](../../docs/langchain.md) 的「环境配置」节）。

真机模式需要本机 Ollama（在本地运行大语言模型的服务）已启动且已拉取 `qwen3.8:latest`。

```bash
cd langchain/04_middleware
source ../../.venv/bin/activate       # 依赖装在仓库根 .venv；也可直接用 ../../.venv/bin/python
python3 middleware_lab.py             # 真机：A 离线 + B/C/D/E 调模型
python3 middleware_lab.py --demo      # 离线：只跑 A 段（3 项断言）
```

真实输出（节选：省略全部分隔线）：

```text
[04] Middleware：Agent 运行时钩子
模式: 真机（qwen3.8:latest）

[A] 自定义中间件：拦截与放行（离线）
  拦截 delete_file -> 操作被策略拦截：delete_file 不在允许列表内。
  ✅ 黑名单工具被拦截（handler 未执行） — handler 调用=[]
  放行 calculator  -> handler-ran（handler 调用=['calculator']）
  ✅ 白名单工具正常执行
  ✅ 同类中间件实例不可重复注册 — Please remove duplicate middleware instances.

[B] SpyMiddleware：钩子次序与计数（真机）
  钩子序列: ['before_model', 'tool:calculator', 'before_model']
  ✅ 钩子按 模型前→工具→模型前 交错触发 — events=['before_model', 'tool:calculator', 'before_model']
  ✅ 计数：工具调用 1 次、模型调用 2 次

[C] 策略中间件：禁删文件、计算放行（真机）
  删除请求 -> 拦截消息 1 条，实际删除 []
  ✅ 删除请求被中间件拦截（磁盘无操作） — DELETED=[]
  计算请求 -> 工具结果 ['4']，最终答案: 2 + 2 = 4
  ✅ 计算工具不受影响，正常返回 4

[E] 叠加中间件：进入顺序、返回逆序（真机）
  钩子序列（前两轮）: ['A:before_model', 'B:before_model', 'B:after_model', 'A:after_model', 'A:before_model', 'B:before_model', 'B:after_model', 'A:after_model']
  ✅ 进入顺序 A→B、返回逆序 B→A — log[:4]=['A:before_model', 'B:before_model', 'B:after_model', 'A:after_model']
  ✅ 每轮 before/after 成对出现

[D] 预置中间件：限次与重试（真机）
  限次运行：工具结果 ['42']，结束语: Model call limits exceeded: run limit (1/1)
  ✅ 超限前工具照常执行
  ✅ 超限后被截断并给出结束语
  重试运行：工具实际被调用 3 次，最终答案: 抓取成功。工具返回结果为：**ok-after-retries**（表示在重试后成功获取了 exam
  ✅ 瞬时失败被自动重试到成功
  ✅ 模型拿到重试后的成功结果

验收: 13/13 通过 ✅
```

诚实预期：`[A]` 段全部离线；`[B]/[C]/[E]/[D]` 依赖真机模型，多次连跑均 13/13。整轮真机约 20-40 秒。Ollama 未启动时真机部分跳过（退出码 2），`--demo` 只跑 A 段。

## How It Works

### 钩子挂在循环的哪里

中间件不改变循环结构，只是在模型调用与工具执行两个位置加装关卡：

![Middleware 钩子：包裹模型调用与工具执行](images/middleware.architecture.svg)

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/langchain/04_middleware/images/middleware.architecture.html)
> （或本地打开 [`images/middleware.architecture.html`](images/middleware.architecture.html)）。

`[B]` 段的钩子序列 `['before_model', 'tool:calculator', 'before_model']` 与图一一对应：模型调用前 → 工具执行（被 `wrap_tool_call` 包裹）→ 下一轮模型调用前。

### wrap_tool_call 的契约

`wrap_tool_call(request, handler)` 收到请求对象与 handler（框架传入的"真正执行工具"的函数，也是链上的下一环）：放行就是调用 `handler(request)` 并返回它的结果。

拦截就是直接返回一条 `ToolMessage`（工具消息：对话里代表"工具执行结果"的消息类型，需带上被拦截调用的 `tool_call_id`），此时 handler 不执行。

`[A]` 段的断言"handler 调用=[]"验证的正是拦截路径没有走到执行。

`[C]` 段把这套机制装进真机 Agent：删除请求产生 1 条"策略拦截"工具消息、实际删除列表为空；计算请求照常返回 `4`——一条中间件规则只影响它针对的工具。

### 叠加多个中间件时谁先谁后

`[E]` 段注册两个观察者：进入方向 A→B，返回方向 B→A，像洋葱一样包住模型调用。

但和洋葱不同的是：任一层都能直接截住请求、不再向内传递——比如限次中间件到达上限后直接结束循环。这条次序决定多个策略的优先级：排在前面的中间件最外层，先看到请求、后看到结果。

### 两个预置中间件在做什么

- `ModelCallLimitMiddleware(run_limit=1, exit_behavior="end")`：第一次模型调用放行（工具照常执行出 `42`），第二次被截断，最终消息是框架的 `Model call limits exceeded` 结束语。
- `exit_behavior="error"`：超限时不返回结束语，改为抛出异常。
- `ToolRetryMiddleware(max_retries=3)`：`flaky_fetch` 每次调用都抛异常，中间件自动重试到第 3 次成功；模型拿到的是成功结果 `ok-after-retries`。它补上了 03 实验留的缺口——工具抛异常在默认配置下会让 Agent 崩，重试中间件是标准兜底。

## Pitfalls & Q&A

### 踩坑清单

1. **同类中间件实例不能注册两次**。现象：`AssertionError: Please remove duplicate middleware instances.` 原因：框架按类去重，防止同一策略被误装多份。解法：需要多个"同款不同参"的中间件时，用不同子类或封装成一个多目标中间件。
2. **限次截断发生在工具执行之后**。现象：`run_limit=1` 时工具确实执行了，模型却没机会做收尾回答。原因：钩子挂在"模型调用"上，计数达到上限时循环从下一轮才终止。解法：把 `run_limit` 设到能覆盖"工具轮 + 收尾轮"的值，比如 2。
3. **重试只对抛异常的工具生效**。现象：03 那种"返回 ERROR 文本"的工具不会触发 `ToolRetryMiddleware`。原因：重试策略按异常判断，返回错误文本不算失败。解法：瞬时故障用抛异常（交给重试中间件），业务失败用返回值（交给模型回退），两者别混。

### 深入问答

**Q：中间件和"工具内校验"怎么分工？**

按归属分：只对一个工具有意义的规则（参数合法性、路径范围）留在工具内；跨工具的规则（黑名单、预算、重试、审计）放中间件。判断标准是"删掉这个工具后规则还要不要"——还要的，属于中间件。

**Q：多个中间件同时改同一个东西（比如都改提示词）会怎样？**

以洋葱次序为准：外层的修改先发生，内层的修改在内层生效；返回路径上后发生的可能覆盖先发生的。写多个策略时给它们划分不重叠的职责域，或明确一个"最终裁决者"，比依赖覆盖顺序更稳。

**Q：能改一次调用用的模型吗？**

可以。`wrap_model_call` 钩子能修改请求里的模型、参数、提示词（只对当前调用生效）。把它和计数钩子组合，就能实现"超预算自动切小模型"这类降级策略——本篇没有展开，官方文档的中间件章节有完整示例。
