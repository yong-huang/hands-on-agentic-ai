# 02 · 拆解工业 Harness：Claude Code 分层地图与四层对照

> 不先看工业实现就动手造，容易把 harness 造成"带工具的 chat 循环"。
> 本篇解剖工业级 harness（Claude Code）的分层结构，产出两张自己画的地图：
> **九模块职责表**和 **Model/Harness/Framework/Platform 四层对照**。

## What

工业 harness 是把"模型可能的智能"翻译成"被允许的可靠工作"的确定性工程层。Claude Code 据源码拆解转述内部有五层结构、约 51 万行工程代码——模型只占其中几乎为零的推理调用。九个模块按职能分三条线记：

- **主干道**：启动链路 → Prompt 装配 → 主循环；
- **执行面**：工具契约 → 权限门 → 沙箱；
- **续航面**：上下文管理 → 会话/记忆，扩展机制挂载一切。

心智模型一句话：**模型在区域外，harness 在区域内——边界画在哪，权力就在哪。**

四层对照（一句话测试）：

| 层 | 回答的问题 | 换掉它要重写什么 | 代表 |
|:--|:--|:--|:--|
| Model | 会不会 | 不用改任何东西 | qwen3.8 |
| Harness | 做不做得到、被允许做什么 | 不用改模型 | Claude Code、本系列 mh/ |
| Framework | 多 agent 怎么组合 | 改 harness 交互 | LangGraph、CrewAI |
| Platform | 组织怎么治理一群 harness | 改组织接入 | Databricks Agent Bricks |

**"Frameworks compose agents. Harnesses run them."**（Winder.AI）

## Why

知道每一层"为什么存在、失效了会怎样"，动手造的每个实验才有靶子——不先看工业实现就动手，最容易漏掉的恰恰是权限、预算这些"不出事看不见"的层。

四层对照同时回答核心问题：**Harness AI 和 Agentic AI 到底差在哪**——范式 vs 工程层；what/why vs how/where；概率性推理 vs 确定性规则。六个字版：**范式定上限，harness 定下限。**完整论述见 [REPORT.md §4](REPORT.md)。两条支撑论断：同一模型换 scaffold 得分 42% vs 78%，harness 质量直接决定下限；生产故障大多来自 harness 而非模型——学它的工程性价比极高。

## How

```bash
cd harness/02_harness_anatomy
open REPORT.md        # 主产出：模块职责表 + 四层对照论述（含全部来源）
```

本实验无真机跑批，验收方式是**能讲**：3 分钟讲完 harness 与 Agentic AI 的
区别，能指出任意模块"失效时对应 01 实验的哪种死法"。完整九模块职责表在
[REPORT.md §2](REPORT.md)。

## Deep Dive

**一次工具调用的旅程**：主循环向模型要决策 → 工具调用先过权限门 → 放行后
在沙箱执行 → 结果经上下文治理回喂主循环；记忆与扩展机制分别从下方/上方
挂载。九个模块全部是确定性工程代码，区域外只有两个东西：终端用户和 LLM。

**权限门为什么在工具系统和沙箱之间，而不是模型和工具之间？**模型输出的
只是"意图"，拦截点必须在意图与副作用之间——"The model decides what to
do. The harness decides what's allowed."，第三代设计哲学：不定义行为，只
定义约束边界（07 权限门实验实现的就是这个位置）。

易错点：

- **别把 UI 当 harness**：终端界面只是启动链路的外壳（suedbroecker 列的
  三个"≠"之一）；同理执行环境（沙箱）也不必然是 harness 的一部分——
  但治理它的策略代码是。
- **别拿功能清单比 harness**：2026 年各家功能已趋同（三家支持 ACP 互相
  驱动），要比就比**假设**：模型锁不锁定、部署在哪、谁能改行为。

## Q&A

**Q1: Claude Code 五层和九模块是什么关系？**

五层是源码包结构，九模块是职能切分；一一对应关系见
[REPORT.md §2](REPORT.md) 表格备注。

**Q2: 为什么说护城河在 harness 不在模型？**

模型商品化后可随换；沙箱、权限、预算、审计编码的是组织政策与机构知识，
模型升级不会废除它们（Winder.AI）。

**Q3: Agent QA 是什么？**

alphaXiv 论文实证：支架演进不必然提升解决率，却让 token 翻倍——所以
harness 需要回归评测（固定模型、固定任务集），见 16 评测台。
