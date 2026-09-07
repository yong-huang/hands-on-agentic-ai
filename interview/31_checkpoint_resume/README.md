# 31 · 长任务断点续跑（Checkpoint/Resume）

> 覆盖面试题：长任务中途挂了怎么恢复？检查点应该存什么？如何保证步骤幂等？
> 一条 10 步的 LLM 长任务管线，每步完成后原子写检查点；`--crash-at N` 模拟
> 进程在任意步崩溃，重启后从断点恢复：已完成步骤复用结果、未完成步骤重做。

## 1. 面试答题主线

- **检查点存什么**：已完成步骤 id + 每步输出 + 共享上下文——重启后任务可以
  一次性恢复到崩溃前的完整状态；
- **原子写**：先写 `.tmp` 再 `os.replace`，任何时刻崩溃都不会留下半截检查点；
- **幂等语义**：at-least-once 执行 + 结果按步骤 id 去重 = 业务上 exactly-once
  （未完成的步骤重做是安全的，因为该步没有检查点记录）；
- **LLM 上下文恢复**：重启后把已完成步骤的摘要喂回模型，不"失忆重做"。

## 2. 快速开始

```bash
cd interview/31_checkpoint_resume
# 三步演示（真实 LLM）:
python checkpoint_resume.py --crash-at 4 --fresh   # 步骤 1-3 完成后崩溃 (exit 137)
python checkpoint_resume.py                        # 恢复: 复用 1-3, 续跑 4-10
python checkpoint_resume.py                        # 全部复用, 零 LLM 调用
# 离线: 加 --demo（canned 产出，机制相同）
```

**实测**：run1 崩溃后检查点保留步骤 1-3；run2 跳过 1-3、执行 4-10（7 步），
复用 3 步；run3 全部复用零重算（重放语义正确）。恢复只花 70% 的成本跑完剩余
70% 的任务——任务越长，断点续跑的收益越大。

## 3. 面试追问预案

- 检查点写入频率？→ 每步落盘（本篇）；更细可按 token 预算/时间窗口；
- 步骤有副作用（写外部系统）怎么办？→ 步骤设计为幂等或引入业务事务 id；
- 与"从头重跑"的成本差？→ 本脚本每次打印 `实际执行/复用` 计数；
- 生产对应物：LangGraph checkpointer、Temporal/Celery 的工作流持久化。

## 4. 文件结构

```
interview/31_checkpoint_resume/
├── README.md               # 本篇
└── checkpoint_resume.py    # 主脚本（约 170 行）：检查点 + 崩溃模拟 + 恢复
```

（`checkpoint.json` 为运行时产物，已 gitignore。）
