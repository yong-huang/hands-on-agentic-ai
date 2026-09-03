# 30 · 可观测性与评估框架：给 Agent 装上眼睛（系列收官）

> "改了提示词到底变好还是变坏？"没有评估框架，这个问题只能靠感觉。收官篇给
> Agent 装上两样东西：**可观测性**（轻量 trace/span 模型，每次运行记录
> llm_call / tool_call 的耗时与结果，导出 JSON 可回放）和**评估框架**（6 条
> 带预期关键词的用例，对 Agent 的 v1/v2 两个版本各跑一遍对比通过率）。

## 1. 为什么需要它

Agent 开发的每次改动（提示词、工具、模型）都可能是回归。本篇的价值不在某个
技术点，而在建立**两个可迁移的基础设施**：Trace 让"慢在哪、错在哪"可回放
分析；评估集让"哪个版本更好"变成可复现的测量。生产对应物是 OpenTelemetry
SDK + 评估集 CI——模型与结构完全一致，本篇是它们的微缩版。

## 2. 总览：核心机制一图看懂

![可观测性与评估框架](images/observability_eval.architecture.svg)

**怎么看这张图**：被测 Agent（v1/v2 两个版本）在评估运行器上跑同一组用例，
全程打 span（llm_call / tool_call / agent_run）；评估器按预期关键词判分，
输出通过率 / token / 耗时对照表；每个 trace 落盘为 JSON 可回放。

心智模型一句话：**Trace 回答"发生了什么"，评估集回答"好不好"——缺一不可。**

🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/30_observability_eval/images/observability_eval.architecture.html)（或本地打开 [`images/observability_eval.architecture.html`](images/observability_eval.architecture.html)）。

## 3. 快速开始

```bash
cd agents/30_observability_eval
python observability_eval.py --demo   # 离线：MockLLM 演示优化对比（v1 2/6 → v2 5/6）
python observability_eval.py          # 真实：qwen3.8 两版本各跑 6 用例
```

**真机实测**（诚实数据）：v1 与 v2 都是 6/6——qwen3.8 对这 6 道简单题太强，
v2 的 calculator 工具只增加了 token（1220 vs 1065）与耗时（+10s）。**这本身
是重要的实验素养**：优化没有收益时要如实报告，并说明"工具的价值要在更大
数字、更易错的算式上才显形"（demo 的 MockLLM 用可复现的方式演示了这一点）。
每次运行导出完整 span 树到 `traces/`。

## 4. 核心概念

### 4.1 Trace/Span：可回放的执行档案

```python
tracer = Tracer("eval_v2")
span = tracer.start_span("tool_call", tool="calculator", expression="45*12")
tracer.end_span(span, result="540")
```

span 记录名称、耗时、属性与结果，整棵树导出 JSON。定位"哪次调用慢了 3 秒、
哪个用例答错时模型说了什么"不再靠翻日志。**生产对应 OpenTelemetry 的
trace/span 语义**，字段设计保持一致便于迁移。

### 4.2 评估集：确定性的回归防线

6 条用例 = 3 条算术（考察工具调用）+ 3 条概念（考察知识），预期用关键词
判分（确定性、零成本、可复现）。**评估集是回归防线**：任何提示词/工具/模型
改动都重跑一遍，通过率下降即回归告警。

### 4.3 优化迭代对比：数据驱动的版本决策

v1（无工具）vs v2（calculator 工具 + 强制说明）的双版本对比给出三个数：
通过率、token、耗时。**真机数据**显示简单任务上 v2 是纯成本——这正是
"优化要按任务画像选型"的实证。demo 的 MockLLM 则用可复现方式演示了工具
缺失时的质量塌方（v1 2/6 → v2 5/6）。

### 4.4 已知边界

- 关键词判分会漏判同义正确回答（生产可加 LLM 裁判，代价是噪声）；
- 6 条用例太少——真实评估集要几十条并覆盖边界与历史回归；
- 手写 Tracer 无采样/上报生态，生产换 OpenTelemetry。

## 5. 代码关键部分

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

坑清单：

- Trace 的时间戳用 `time.time()`，跨机器统计需统一时钟源；
- 评估判分的 expect 关键词要覆盖同义写法，否则评分失真；
- traces/ 目录纳入 gitignore（运行产物），评估结果表才进文档。

## 6. 文件结构

```
30_observability_eval/
├── README.md                                    # 本篇教程
├── observability_eval.py                        # 主脚本（约 210 行）：Tracer + 评估集 + 对比
├── traces/                                      # 运行时产物：trace JSON（gitignore）
└── images/
    ├── observability_eval.architecture.json     # 图源：architecture 类型（评估体系组件）
    ├── observability_eval.architecture.html     # 交互版架构图
    └── observability_eval.architecture.svg      # 双主题矢量图
```

## 7. 面试要点

- **Q: Agent 的可观测性要记录什么？**
  A: 结构化 trace/span（LLM 调用、工具调用、耗时、输入输出摘要）+ 业务指标
  （通过率/token/延迟）。事件流（07）是它的进程内形态。
- **Q: 评估集设计的要点？**
  A: 覆盖典型/边界/历史回归、预期可确定性判分、规模够大且稳定、任何改动
  全量重跑。
- **Q: 如何判断一个优化该不该上线？**
  A: 双指标对比（质量指标 + 成本指标）在固定评估集上的差异，并用足量样本
  排除噪声——如本篇 v1/v2 对比。
- **Q: 手写 Tracer 与 OpenTelemetry 的关系？**
  A: span/trace 语义模型一致；OTel 提供采样、导出器与生态集成。理解手写版
  的模型后迁移 OTel 只是换基建。
- **Q: 关键词评分和 LLM 裁判怎么选？**
  A: 有标准答案用关键词（确定性），开放回答用 LLM 裁判（覆盖广）+ 校准
  与抽检——混合使用是常态。

## 8. 总结

Trace 让执行可回放，评估集让质量可测量，双版本对比让优化可决策——至此
30 个项目全部完成：从裸 HTTP 调用，到 ReAct、Plan-and-Execute、工具系统、
MCP、记忆与上下文工程、RAG、多 Agent 协作，再到服务化、安全与可观测性。
把 `README.md` 的学习路线再走一遍，你会发现每一课都是下一课的地基。
