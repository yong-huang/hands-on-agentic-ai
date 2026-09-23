# 30 · 可观测性与评估框架：给 Agent 装上眼睛（系列收官）

> 给 Agent 装上两样东西：**可观测性**（轻量 trace/span 模型，每次运行记录
> llm_call / tool_call 的耗时与结果，导出 JSON 可回放）和**评估框架**（6 条
> 带预期关键词的用例，对 Agent 的 v1/v2 两个版本各跑一遍对比通过率）。

## What

两件基础设施：

- **Trace/Span：可回放的执行档案**——span 记录名称、耗时、属性与结果，
  整棵树导出 JSON。定位"哪次调用慢了 3 秒、哪个用例答错时模型说了什么"
  不再靠翻日志。生产对应 OpenTelemetry 的 trace/span 语义，字段设计保持
  一致便于迁移：

```python
tracer = Tracer("eval_v2")
span = tracer.start_span("tool_call", tool="calculator", expression="45*12")
tracer.end_span(span, result="540")
```

- **评估集：确定性的回归防线**——6 条用例 = 3 条算术（考察工具调用）+
  3 条概念（考察知识），预期用关键词判分（确定性、零成本、可复现）。任何
  提示词/工具/模型改动都重跑一遍，通过率下降即回归告警。

心智模型一句话：**Trace 回答"发生了什么"，评估集回答"好不好"——缺一
不可。**

## Why

Agent 开发的每次改动（提示词、工具、模型）都可能是回归。"改了提示词到底
变好还是变坏？"没有评估框架只能靠感觉。生产对应物是 OpenTelemetry SDK +
评估集 CI——模型与结构完全一致，本篇是它们的微缩版。

## How

```bash
cd agents/30_observability_eval
python observability_eval.py --demo   # 离线：MockLLM 演示优化对比（v1 2/6 → v2 5/6）
python observability_eval.py          # 真实：qwen3.8 两版本各跑 6 用例
```

**真机实测**（诚实数据）：v1 与 v2 都是 6/6——qwen3.8 对这 6 道简单题太强，
v2 的 calculator 工具只增加了 token（1220 vs 1065）与耗时（+10s）。**这
本身是重要的实验素养**：优化没有收益时要如实报告，并说明"工具的价值要在
更大数字、更易错的算式上才显形"（demo 的 MockLLM 用可复现的方式演示了
这一点：v1 2/6 → v2 5/6）。每次运行导出完整 span 树到 `traces/`。

**优化迭代对比**：v1（无工具）vs v2（calculator 工具 + 强制说明）的双版本
对比给出三个数：通过率、token、耗时——"优化要按任务画像选型"的实证。

被测 Agent 的实现——全程打 span：

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

## Deep Dive

**已知边界**：关键词判分会漏判同义正确回答（生产可加 LLM 裁判，代价是
噪声）；6 条用例太少——真实评估集要几十条并覆盖边界与历史回归；手写
Tracer 无采样/上报生态，生产换 OpenTelemetry。

踩坑清单：

- Trace 的时间戳用 `time.time()`，跨机器统计需统一时钟源；
- 评估判分的 expect 关键词要覆盖同义写法，否则评分失真；
- traces/ 目录纳入 gitignore（运行产物），评估结果表才进文档。

## Q&A

**Q1: Agent 的可观测性要记录什么？**

结构化 trace/span（LLM 调用、工具调用、耗时、输入输出摘要）+ 业务指标
（通过率/token/延迟）。事件流（07）是它的进程内形态。

**Q2: 如何判断一个优化该不该上线？**

双指标对比（质量指标 + 成本指标）在固定评估集上的差异，并用足量样本排除
噪声——如本篇 v1/v2 对比。

**Q3: 关键词评分和 LLM 裁判怎么选？**

有标准答案用关键词（确定性），开放回答用 LLM 裁判（覆盖广）+ 校准与抽检
——混合使用是常态。
