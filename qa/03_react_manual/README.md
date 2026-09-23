# 03 · 手写 ReAct 循环

> 纯手写不用框架的 ReAct（Thought-Action-Observation）：calculator + mock
> 天气两工具，JSON 解析失败重试、工具异常转 Observation 喂回。5 个多步
> 任务全部正确，含一条"失败→自愈"轨迹。

## What

ReAct = Thought → Action → Observation 循环，直到模型输出 Answer 终止。
本篇不用任何框架，约 160 行手写完整循环。

心智模型一句话：**每个结论都必须有工具 Observation 支撑——不凭空生成。**

## Why

手写一遍的价值是循环里每一行都可见可控：解析失败怎么重试、工具异常怎么
回喂、何时终止，全是自己的逻辑，行为完全可复现。

## How

```bash
cd qa/03_react_manual
MOCK=1 python3 react_manual.py   # 离线走完整循环含解析失败重试
python3 react_manual.py          # 真机: 5 个多步任务
```

5 个多步任务全部正确，含一条"失败→自愈"轨迹（计算器故意传非法表达式，
Agent 读取错误后自行调整）。

## Deep Dive

**失败→自愈是 ReAct 可靠性的核心**：Action 失败不崩溃、不静默——错误
作为 Observation 回喂，模型读取后自行调整下一步。JSON 解析失败同理：
两级回退提取，仍失败则把解析错误喂回让模型自纠。max_steps 兜底防死循环。

## Q&A

**Q1: ReAct 怎么解决幻觉？**

每个结论都有工具 Observation 支撑——模型只能基于真实工具输出作答，而非
凭空生成。
