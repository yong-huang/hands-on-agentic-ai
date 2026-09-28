# 30 · 可观测性与评估框架：给 Agent 装上眼睛

> 给 Agent 装上两样东西：可观测性（轻量 trace/span 模型，每次运行记录 llm_call / tool_call 的耗时与结果，导出 JSON 可回放）和评估框架（6 条带预期关键词的用例，对 Agent 的 v1/v2 两个版本各跑一遍对比通过率）。读完本篇你能给任意 Agent 加上执行档案与回归防线，并学会用数据判断一次优化该不该上线。

## Background

在没有这两件东西的做法里，判断一个 Agent 的好坏靠肉眼：改完提示词，跑两三次，看看输出，凭印象说"好像好了一点"。执行过程则散落在控制台日志里，要靠人从头翻到尾。

痛点在两个日常场景同时出现：排查问题时，"哪次调用慢了 3 秒、哪个用例答错时模型说了什么"没有结构化记录可查；评估改动时，提示词、工具、模型的每次调整都可能悄悄破坏已有能力，"改了提示词到底变好还是变坏"没有评估框架只能靠感觉。

生产世界的对应物早已存在：可观测性领域的 OpenTelemetry，以及软件测试里的回归用例集加 CI（持续集成，代码提交后自动跑测试的机制）。本篇把这两者微缩成轻量版：一个手写 Tracer 加 6 条带预期关键词的用例，机制与结构与生产版一致。

## What

本篇是两件基础设施：Trace/Span 与评估集。

**Trace/Span：可回放的执行档案。** trace（一次完整运行的执行轨迹）由多个 span（其中一次调用的记录段）组成，span 记录名称、耗时、属性与结果，整棵树导出 JSON（键值对形式的文本数据格式）。

生产系统对应 OpenTelemetry（业界通用的可观测性标准与 SDK）的 trace/span 语义，本篇字段设计保持一致，便于日后迁移。

可以把 trace 想象成车辆的行车记录仪：span 是每一段行程的记录条目。但和行车记录仪不同的是：span 树是结构化字段，可以按名称查询、按耗时排序、整体导出回放，而不是一段只能从头看的连续视频。

最小用法三行：

```python
tracer = Tracer("eval_v2")
span = tracer.start_span("tool_call", tool="calculator", expression="45*12")
tracer.end_span(span, result="540")
```

**评估集：确定性的回归防线。** 6 条用例 = 3 条算术（考察工具调用）+ 3 条概念（考察知识），预期用关键词判分——确定性、零成本、可复现。任何提示词/工具/模型改动都重跑一遍，通过率下降即回归（新改动破坏已有功能）告警。

心智模型一句话：**Trace 回答"发生了什么"，评估集回答"好不好"——缺一不可。**

## When to Use

适合在三类时候请出这两件基础设施：

- 排查"哪次调用慢了、答错时模型说了什么"时：span 树给出每次 llm_call / tool_call 的耗时与结果，不用翻日志。
- 改提示词、换工具、换模型的前后：固定评估集各跑一遍，通过率、token（模型计长与计费的最小文本单位）、耗时三数对比。
- 上线前做质量把关时：通过率低于历史水平即拦截发布。

可以暂缓的情况：一次性玩具脚本不值得搭这两件东西；评估集只有几条、关键词又覆盖不了同义写法时，结论会失真，不如不评。

| 方案 | 差异 | 什么时候选它 |
| :--- | :--- | :--- |
| 肉眼抽查 | 快，但不可复现、不可比较 | 原型期的粗看 |
| print 日志 | 有记录但非结构化、难回放 | 简单脚本的临时调试 |
| 轻量 Tracer + 关键词评估集（本篇） | 结构化回放 + 确定性判分 | 个人与小型项目的起步配置 |
| OpenTelemetry + LLM 裁判 + CI | 采样上报生态 + 覆盖开放回答 | 生产系统 |

## Quick Start

前置条件：Python 3 环境，`pip install requests`（脚本启动即导入，`--demo` 也需要）；`--demo` 模式用 MockLLM（用预置回答代替真实模型的替身）离线可跑，真实模式需要已配置可用的模型访问（真机实测用的是 qwen3.8）。

```bash
cd agents/30_observability_eval
python observability_eval.py --demo   # 离线：MockLLM 演示优化对比（v1 2/6 → v2 5/6）
python observability_eval.py          # 真实：qwen3.8 两版本各跑 6 用例
```

诚实预期（真机实测）：v1 与 v2 都是 6/6——qwen3.8 对这 6 道简单题太强，v2 的 calculator 工具只增加了 token（1220 vs 1065）与耗时（+10s）。

这本身是重要的实验素养：优化没有收益时要如实报告，并说明"工具的价值要在更大数字、更易错的算式上才显形"（demo 的 MockLLM 用可复现的方式演示了这一点：v1 2/6 → v2 5/6）。

每次运行都会导出完整 span 树到 `traces/` 目录，可以先打开看结构。

## How It Works

被测 Agent 的实现——全程打 span，这是本篇最核心的一处代码：

```python
def agent_answer(version, question, tracer):
    """被测 Agent: 组装 prompt -> (可选)工具调用 -> 最终回答, 全程打 span"""
    span = tracer.start_span("llm_call", version=version, question=question)
    raw = llm([{"role": "system", "content": PROMPTS[version]},
               {"role": "user", "content": question}])
    tracer.end_span(span, raw=raw)
    m = re.search(r'"expression"\s*:\s*"([^"]+)"', raw)
    if m:                                            # 模型请求计算器
        span = tracer.start_span("tool_call", expression=m.group(1))
        result = calculator(m.group(1))
        tracer.end_span(span, result=result)
        return llm([{"role": "user", "content": f"计算结果: {result}…"}])
    return raw
```

`agent_answer` 的每个动作前后都包一对 `start_span` / `end_span`：一次 llm_call、一次 tool_call 各成一个 span，名称、耗时、属性、结果全部入档——Quick Start 里 `traces/` 下导出的 JSON 树就是这些 span 拼出来的。

你在 demo 输出里看到的"v1 2/6 → v2 5/6"，则是评估集拿预期关键词对 `agent_answer` 的返回逐条判分的结果。

v1（无工具）与 v2（calculator 工具 + 强制说明）的对比给出三个数：通过率、token、耗时。

真机数据里 v2 多出的 155 个 token 与 10 秒，就来自工具路径多出的"解析算式 → 调 calculator → 带结果再调一次模型"这一整段——这也解释了为什么简单题上工具反而更贵。

评估集的判分是纯字符串包含检查：6 条用例的预期各配若干关键词，回答命中即通过。它的价值在确定性——同一段回答永远得到同一个分数，两次实验的差异才能归因于被测对象本身。

## Pitfalls & Q&A

踩坑清单（现象 / 原因 / 解法）：

- 同义的正确回答被判错。现象：回答意思对、换了个说法，评分判失败。原因：expect 关键词没覆盖同义写法。解法：关键词覆盖常见同义形式；生产可加 LLM 裁判，代价是引入噪声。
- 跨机器统计耗时时对不上。现象：同一代码在不同机器测出的耗时没有可比性。原因：Trace 的时间戳用 `time.time()`，依赖各机器的本地时钟。解法：跨机器统计需统一时钟源。
- 仓库被运行产物塞满。现象：`traces/` 下文件越积越多进了版本库。解法：`traces/` 纳入 gitignore（声明哪些文件不入版本库的配置文件），评估结果表才进文档。

已知边界：关键词判分会漏判同义正确回答（见上）；6 条用例太少，真实评估集要几十条并覆盖边界与历史回归；手写 Tracer 没有采样与上报生态，生产换 OpenTelemetry。

**Q1: Agent 的可观测性要记录什么？**

结构化 trace/span（LLM 调用、工具调用、耗时、输入输出摘要）+ 业务指标（通过率/token/延迟）。事件流（07 实验的主题）是它的进程内形态。

**Q2: 如何判断一个优化该不该上线？**

双指标对比（质量指标 + 成本指标）在固定评估集上的差异，并用足量样本排除噪声——本篇 v1/v2 的三个数就是这套决策的输入。

**Q3: 关键词评分和 LLM 裁判怎么选？**

有标准答案用关键词（确定性），开放回答用 LLM 裁判（覆盖广）+ 校准与抽检——混合使用是常态。
