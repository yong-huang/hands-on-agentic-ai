# 18 · 收尾对照：换模型 vs 换 Harness，2×2 给出答案

> 整个系列的主线问题在这里收口：**Harness AI 和 Agentic AI 的区别，
> 到底值多少分？** 复用 16 评测台的任务集与判分器，跑一张 2×2 表：
> 两个模型（qwen3.8 27B / qwen3:4b 4B）× 两套 harness（裸 loop / 全装）。
> 40 次真机跑批，结论是量化过的，不是引用来的。

## 1. 为什么需要它

03 的受控对照只比了两个 harness 配置；本篇把第二个轴（模型）加上，
构成完整 2×2。这是论文方法的完整复现，也是系列学习的"毕业答辩"：
如果你能预测每个格的结果并解释为什么，这门课就通过了。

## 2. 总览：核心机制一图看懂

![2×2 对照实验](images/model_vs_harness.workflow.svg)

**怎么看这张图**：任务集与判分器全程不动（左），只动两个变量——模型
（行）与 harness（列），40 次跑批汇成一张表（右）。

心智模型一句话：**Agent = Model × Harness，是乘法——两个因子各有下限，
harness 的边际价值随模型变弱而放大。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/harness/18_model_vs_harness/images/model_vs_harness.html)
> （或本地打开 [`images/model_vs_harness.html`](images/model_vs_harness.html)）。

## 3. 快速开始

```bash
cd harness/18_model_vs_harness
python3 run_2x2.py --quick    # 快速版: 每格 4 任务
python3 run_2x2.py            # 全量: 4 格 × 10 任务(约 1 小时, 断点续跑)
```

真机数据（2026-09-20，详见 [REPORT.md](REPORT.md)）：

| 格 | 解决率 | 平均轮次 | est token/任务 |
|:--|:--:|:--:|:--:|
| qwen3.8 + 裸 loop | 10/10 | 2.0 | 67 |
| qwen3.8 + full harness | 10/10 | 2.1 | 69 |
| qwen3:4b + 裸 loop | **1/10** | 1.1 | 752 |
| qwen3:4b + full harness | **5/10** | 1.5 | 764 |

## 4. 核心结论（验收项）

1. **harness 的收益与模型强度成反比**：强模型域 +0pp，弱模型域 +40pp
   （×5）——05/09 观察到的"harness 价值 ∝ 故障密度"的最终定理形式：
   **弱模型就是持续的故障源**。
2. **harness 救不了太弱的模型**：4b+full（5/10）仍远逊 3.8+bare（10/10）。
   乘法关系的另一面。
3. **无效推理有成本证据**：4b 每任务烧 11 倍 token 换 1/10 解决率——
   09 预算止损对弱模型是刚需，不是优化。

## 5. 代码关键点

```python
run_one(model_key, harness, task_i, ...)   # 单格单任务, 断点续跑(rows.json)
report(rows)                               # 2×2 表生成
```

两个工程细节：`importlib.reload(mh.llm)` 让 `LLM_MODEL` 环境变量在切换
单元格时生效；`rows.json` 断点续跑——40 次跑批随时可中断续作。

## 6. 文件结构

```
18_model_vs_harness/
├── README.md
├── run_2x2.py             # 2×2 编排（断点续跑）
├── REPORT.md              # 数据表 + 三条量化结论
├── rows.json              # 原始跑批记录（git 忽略）
└── images/                # 工作流图三件套
```

## 7. 深入要点

- **为什么 4b 在 bare 下只有 1/10？** 多步任务对小模型是"连续不走神"
  的考验，一步偏差全盘皆输——这正是 harness 各模块（校验/止损/恢复）
  存在的理由：把"不走神"从模型职责挪到工程职责。
- **full 对 4b 的提升来自哪个模块？** 主要三类：schema 错误回传（自纠）、
  沙箱拒绝的明确反馈（不瞎猜）、预算 HANDOFF（不无限烧）。逐模块归因
  是 16 评测台的后续工作。
- **这个实验能推广吗？** 单任务集、单领域，样本 10/格——方向性结论可靠，
  数字不可外推。要发论文需要多任务域 × 多模型。

## 8. 总结（全系列收官）

40 次跑批给系列主线一个自己的答案：**模型决定上限，harness 决定下限，
harness 的边际价值随模型变弱而放大（本机实测：弱模型域 ×5）。**
从 01 的失败实录到这张 2×2 表，"Harness AI 与 Agentic AI 的区别"完成了
从概念到数据的闭环。`mh/` 的 12 个模块和评测台会留在这里——下次换模型、
加模块、调策略，先跑一遍 `bash run.sh`。
