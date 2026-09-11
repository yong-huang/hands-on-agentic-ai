# 03 · 手写 ReAct 循环（面试主线①）

> 覆盖面试题：手写 ReAct（Thought-Action-Observation）；Action 失败怎么办？
> ReAct 怎么解决幻觉？纯手写不用框架，calculator + mock 天气两工具，
> JSON 解析失败重试、工具异常转 Observation 喂回。

## 1. 真机实测

5 个多步任务全部正确，含一条"失败→自愈"轨迹（计算器故意传非法表达式，
Agent 读取错误后自行调整）。`MOCK=1` 离线走完整循环含解析失败重试。

## 2. 深入要点

- ReAct 的本质：Thought/Action/Observation 循环 + Answer 终止条件
- Action 失败处理：错误作为 Observation 回喂，不崩溃、不静默
- JSON 解析失败：错误回喂让模型自纠（两级回退提取）
- 幻觉解决：每个结论都有工具 Observation 支撑，非凭空生成
- max_steps 兜底防死循环

## 3. 文件结构

```
interview/03_react_manual/
├── README.md            # 本篇
└── react_manual.py      # 手写 ReAct（约 160 行）
```
