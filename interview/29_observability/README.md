# 29 · Agent 可观测性（Tracing + 回放）

> 覆盖面试题：设计 Agent 的可观测性系统（生产级必问）
> 给一次确定性 Agent 执行（规划 → 3 个工具调用，含一次异常重试）埋点：
> JSONL 事件流落盘 → trace 树 CLI 渲染 → 成本/延迟统计面板 → 时间旅行
> 回放（读回事件，不调任何模型逐步重放）。全流程离线可跑。

## 1. 运行与实测

```bash
python observability.py    # 生成事件 -> 渲染 -> 统计 -> 回放
```

实测（2026-09-09，全离线确定）：5 个 span 落盘并一致回放（5=5 ✓）。
trace 树一眼看清调用结构与异常：

```
[agent] root (0ms)
  [llm] planner (25ms, 180 tok)
  [tool] 查库存 (24ms, 40 tok)
  [tool] 查价格 (42ms, 40 tok) ⚠ 第一次尝试失败: 价格服务 503
  [tool] 下单 (23ms, 40 tok)
```

统计面板：spans=5，总 token=300，估算成本 ¥0.0006，P99 延迟 39ms，
工具调用 {查库存:1, 查价格:1, 下单:1}，异常 span 1（重试后成功）。

## 2. 深入要点

- 一切皆事件：每个 span 记 类型/父子关系/输入输出/token/耗时/异常，
  JSONL 落盘——事后一切分析（树/统计/回放）都从它派生。
- trace 树回答"谁调了谁"：排障先找异常 span 再下钻输入输出；统计面板
  回答"贵不贵、慢不慢"（token 成本 + P99 延迟）。
- 时间旅行 = 确定性重放：用记录的事件离线复现执行路径，不调模型——
  调试、回归测试、故障复盘都靠它。
- 对应生产工具：LangSmith/Langfuse/OTel 的 span 模型与此同构。

## 3. 文件结构

```
interview/29_observability/
├── README.md            # 本篇
├── observability.py     # Tracer + 树渲染 + 统计 + 回放（约 180 行）
└── traces.jsonl         # 运行产物 (gitignore)
```
