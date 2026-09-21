# 01 · 无 Harness 基线：裸 LLM 的多步任务失败实录

> 在造 harness 之前，先回答一个问题：**没有 harness 会怎样？**
> 本篇给一个裸 LLM（无执行层、无重试控制、无状态管理）布置一个多步文件任务，
> 再给一个只多 15 行「真执行」逻辑的对照组。跑完你会发现：Agentic AI 的全部痛点
> ——工具幻觉、虚假成功、上下文漂移——都不来自模型不够聪明，而来自缺少一层
> 确定性的工程设施。这层设施，就是后面 17 个实验要亲手造的 harness。

## 1. 为什么需要它

`agents/` 线教你"怎么一步步把 agent 能力组合出来"（framework 视角），
本线补另一半：**运行时怎么管控它**（harness 视角）。行业公式是
**Agent = Model + Harness**——模型是大脑，harness 是身体：执行工具、管理记忆、
强制权限。2026 年的实证很一致：同一模型换 harness 得分能差一倍
（42% vs 78%），而固定模型只升级 harness 版本，解决率几乎不动。

但"相信结论"和"见过现场"是两回事。本实验把现场录下来：让裸 LLM 和一个
最小 harness 解同一道题，用**文件系统**当唯一裁判——模型说什么不算数，
磁盘上有什么才算什么。

## 2. 总览：核心机制一图看懂

![无 Harness 基线实验流程](images/no_harness_baseline.workflow.svg)

**怎么看这张图**：上下两条泳道是 A/B 两组，提示词完全相同。A 组模型的命令
只是被 runner "看到"，从未执行，于是它会在磁盘空空如也时宣称"任务完成"
（虚假成功）；B 组多了一步真执行 + 输出回喂，模型据实修正，最终文件落盘。
两路最后都汇到同一个判分器：逐文件核对行数。

心智模型一句话：**harness 的最小定义 = 替模型执行 + 把现实喂回去。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/harness/01_no_harness_baseline/images/no_harness_baseline.workflow.html)
> （或本地打开 [`images/no_harness_baseline.workflow.html`](images/no_harness_baseline.workflow.html)）。

## 3. 快速开始

```bash
cd harness/01_no_harness_baseline
MOCK=1 python3 no_harness_baseline.py --selftest   # 离线自检（不需要 Ollama）
python3 no_harness_baseline.py --trials 10         # 真机跑 A/B 各 10 次（验收口径）
python3 no_harness_baseline.py --groups B          # 只跑对照组
```

默认模型是 Ollama 的 `qwen3.8:latest`（免 Key）。想提速可换
`LLM_MODEL=qwen3:4b`，但注意 qwen3 小模型是混合推理架构，思考会吃掉
token 配额导致空回复（见 §5 坑清单）。

每次试验落一份 `results/trial_<组><n>.json`（完整对话 + 判分 + 失败标签），
最后汇总生成 `results/FAILURES.md`。真机结果见下方实测数据。

<!-- 真机跑批 2026-09-17/18, qwen3.8:latest, Ollama 本地 -->

```text
[A0] 4 轮 4 条命令 → ❌ 虚假成功: 宣称任务完成, 但文件系统零变化
[A1] 4 轮 4 条命令 → ❌ 虚假成功 …（含死循环证据）
……（A2-A9 同）
[B0] 2 轮 1 条命令 → ✅
[B1] 2 轮 1 条命令 → ✅
……（B2-B9 同）
A 组(裸 LLM)成功 0, B 组(最小 harness)成功 10
```

| 组 | 成功率 | 平均轮次 | 结论 |
|:--|:--:|:--:|:--|
| A 裸 LLM | **0/10** | 4.0 | 每轮都输出"正确"命令，但磁盘零变化，直到上限轮仍宣称完成 |
| B 最小 harness | **10/10** | 2.0 | 第 1 轮执行、第 2 轮据实收尾，全程无人工干预 |

两个值得咀嚼的细节：

1. **A 组的"死循环"证据**：模型每轮原样重复同一段完美命令——它没有任何
   反馈告诉它"命令没生效"，只能假装推进。`FAILURES.md` 里 10 份证据一字
   不差（temperature=0），失败因此**完全可复现**——这恰是评测台需要的性质。
2. **B 组只要 1 条命令**：拿到真实执行反馈后，模型第一轮就把任务做完了。
   执行反馈不只是纠错，更大幅缩短了收敛路径——harness 既是安全网也是油门。

完整证据见 `results/FAILURES.md` 与 20 份 `results/trial_*.json`
（git 忽略，重跑 `--trials 10` 即可再生）。

## 4. 核心概念

### 4.1 实验设计：差一层执行，其余全同

| | A 组（裸 LLM） | B 组（最小 harness） |
|:--|:--|:--|
| 提示词 | 完全相同 | 完全相同 |
| 模型输出 bash 代码块 | 提取、记录 | 提取、**执行** |
| 执行结果 | 不存在 | 回喂为下一轮 user 消息 |
| 判分 | 文件系统（相同） | 文件系统（相同） |

B 组的执行逻辑只有约 15 行：`subprocess.run` + `cwd` 锁沙箱 + 3 秒超时 +
输出截断。**这 15 行就是 harness 的种子**——后面 17 个实验给它的每个器官。

### 4.2 判分铁证：不看嘴，看磁盘

`grade()` 只认一件事：三个文件都存在，且行数精确等于 3/2/1。A 组会输得
很稳定——它根本没法创建文件。这不是嘲讽 A 组，而是把"没有执行层的 Agentic
AI 长什么样"变成可复现的实验事实：模型每轮都自信地输出正确命令，
**正确命令 + 没有执行 = 零进度**。

### 4.3 失败模式归类

`classify()` 从对话记录里自动抓三种经典死法：

- **虚假成功**：末轮含"任务完成"但执行层缺失（A 组必中）；
- **死循环**：同一命令重复输出 ≥3 次仍不收敛；
- **上下文漂移**：8 轮里始终没出现任务第 3 步（gamma.txt）。

分类是纯函数，证据摘录自动写进 `FAILURES.md`——这就是后面项目 3 与
项目 16 评测台的雏形：先能记录失败，才谈得上量化改进。

### 4.4 从本实验到 harness 之路

本实验暴露的每个缺口，对应后续一个实验：执行无人监督 → 06 沙箱；
失败不自纠 → 05 工具契约；命令无边界 → 07 权限门；轮数无上限 → 09 预算；
状态不落地 → 11 会话持久化。清单见 [../../docs/harness.md](../../docs/harness.md)。

## 5. 代码关键点（与三个真实的坑）

主脚本 ~200 行，四个关键函数：

```python
run_bash(cmd, cwd, timeout=3)   # B 组唯一的 harness 能力：真执行
grade(sandbox)                  # 铁证判分：行数精确匹配
classify(turns, executed_ok)    # 失败模式归类（纯函数）
run_trial(group, n, llm, keep)  # 单次试验：对话循环 + 落盘
```

调试过程中踩到的三个坑，比代码本身更值钱：

1. **同轮漏执行**：模型习惯在同一轮里既给命令又说"任务完成"。最初的循环
   见到"完成"就 break，B 组最后一批命令根本没执行。修复：**先执行再收尾**——
   harness 的动作顺序必须先于模型的结论，这是运行时视角和对话视角的典型差异。
2. **thinking 吃掉配额**：`qwen3:4b` 是混合推理模型，1200 个 token 全花在
   思考上，`content` 为空、`finish_reason=length`。本脚本用 `/no_think`
   软开关兜底；真正的问题是**配额管理本来就是 harness 的职责**（项目 9）。
3. **本地请求被代理劫持**：系统代理把 `localhost:11434` 的请求转发到
   `127.0.0.1:7890`，跑批静默卡死。脚本顶部 `NO_PROXY=localhost,127.0.0.1`
   豁免——网络出口管理同样是 harness 工程的一部分。

## 6. 文件结构

```
01_no_harness_baseline/
├── README.md                    # 本篇：实验教材
├── no_harness_baseline.py       # 主脚本：A/B 两组 runner + 判分 + 失败归类
├── results/                     # 跑批产物（trial_*.json + FAILURES.md，git 忽略）
├── batch.log                    # 最近一次真机跑批的 stdout
└── images/
    ├── no_harness_baseline.workflow.json   # 图源（archify Typed IR）
    ├── no_harness_baseline.workflow.html   # 交互版架构图
    └── no_harness_baseline.workflow.svg    # 双主题矢量图（README 内嵌）
```

## 7. 深入要点

- **为什么判分不信任模型的自我汇报？** Agentic 系统里模型的自我评估是概率性的，
  harness 的判分必须是确定性的。生产里对应"测试通过才算完成"，而不是
  "模型说改完了"。这也是 Databricks 讲的"harness 提供反馈循环与自我验证"。
- **A 组是不是太不公平？** 公平，且必须公平：A 组模拟的是"只接了个 API、
  没有任何工程设施"的真实 teams。它的失败模式（工具幻觉、上下文漂移）与
  生产事故类型一一对应。
- **对照组为什么才算"最小 harness"，agent loop 呢？** 提取→执行→回喂的
  while 循环已经藏在 `run_trial()` 里了，它就是项目 04 的雏形。本实验刻意
  不把它抽象出来——先看见血，再谈解剖。
- **换更强模型能救 A 组吗？** 不能。执行层不存在时，模型再聪明也只能"说出"
  命令。这正是"Harness 与 Agentic AI 的区别"的实验版：**范式决定上限，
  harness 决定下限。**

## 8. 总结

裸 LLM + 多步任务 = 稳定失败，哪怕它每一步都"想对了"；只加 15 行真执行 +
输出回喂，成功率从 0 到满。harness 不是模型的装饰，而是模型智能变成可靠
工作的**必要条件**。

下一篇 [02_harness_anatomy](../02_harness_anatomy/README.md) 把镜头拉远：
拆解工业级 harness（Claude Code）的分层结构，画出 framework / harness /
platform 的四层地图，给后面 16 个实验一张总蓝图。
