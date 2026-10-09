# 06 · Checkpointer：断点恢复与时间旅行

> Checkpointer（检查点保存器）把状态图（LangGraph 里用节点和边描述工作流的那种图）的每个超步（super-step：一批并发节点全部执行完）快照落盘（写进磁盘文件）：进程被 `kill -9`（强制终止进程的信号）后，用同一个 thread（会话标识）重启即可续跑；`get_state_history` 能回看每一步；`update_state` 还能从历史点分叉重放（时间旅行）。
> 本篇纯离线：子进程真的跑到第 4 步被 SIGKILL（强杀，即 kill -9），父进程用同一 thread 续跑，磁盘上的执行账本证明已完成步骤没有重算；随后从第 3 步的检查点分叉出一个新分支。
> 读完你能给任意 LangGraph 图接上持久化，并分清"恢复"与"重放"的边界。

## Background

05 实验的状态图活在内存里：进程一退，状态全丢。对分钟级的小流程无所谓，但长任务（批量处理、等待人工审批数小时）不允许从头再来——崩溃后重跑意味着重复的调用成本，甚至重复的副作用（重复扣款、重复发信）。

最早的土办法是每步执行后手动把进度写进 JSON 文件，重启时读回，像给游戏手动存档。做法可行，但"存什么、什么时候存、并发写怎么办"全要自己维护，节点一改存档格式就崩。

LangGraph 把这件事做进运行时：每个超步（一批并发节点执行完）自动写一次检查点，状态、待执行任务、写入记录一并保存。这份机制叫 durable execution（持久化执行），开发者只选存储后端。

## What

Checkpointer 是"把图的状态按超步自动快照、并能从任意快照恢复"的持久化组件。掌握它只需要认识四个词：

| 概念 | 含义 | 实验中的体现 |
|:--|:--|:--|
| thread | 一条独立的执行会话，配置在 `configurable.thread_id` | `crash-job` / `history-job` |
| checkpoint | 一个超步结束时的完整状态快照 | 8 个快照、长度 6→0 |
| history | 同一 thread 的快照序列，`get_state_history` 取回（新→旧） | `[6, 5, 4, 3, 2, 1, 0, 0]` |
| fork | 从历史快照 `update_state` 改状态再续跑，形成新分支 | "fork" 分支与 original 并存 |

可以把 checkpointer 想象成给白板拍快照的相机：每完成一轮就往相册里存一张，崩了就看最后一张重画。但和相机不同的是：快照是**自动、按超步粒度**拍的，而且支持"从第 3 张照片继续画另一种剧情"——这是时间旅行，不是回放录像。

两种后端的选择：

| 后端 | 存储 | 生存期 | 适用 |
|:--|:--|:--|:--|
| `InMemorySaver` | 进程内存 | 进程退出即失 | 单测、一次性演示 |
| `SqliteSaver` | SQLite 文件 | 跨进程、跨重启 | 本机持久化（本篇用） |

## When to Use

典型场景：

1. 长任务续跑：批处理、爬取、多步生成，崩溃后从最近检查点继续。
2. 人工介入：等待审批时把状态挂起，人到齐后恢复（07 实验的地基）。
3. 调试与对拍：回看每一步的状态、从关键点改参数重放，比较两种决策的走向。

何时不用：秒级完成且无副作用的一次性脚本，加持久化只是负担；只在一个进程内传递状态，普通变量即可。

同类方案对比：

| 方案 | 粒度 | 什么时候选它 |
|:--|:--|:--|
| 手动写 JSON 进度文件 | 自定义 | 非 LangGraph 项目、需求极简 |
| Checkpointer（本篇） | 超步自动 | 任何 LangGraph 图 |
| 外部工作流引擎 | 任务级 | 跨系统编排（LangGraph 之外的话题） |

## Quick Start

以下命令从仓库根目录（clone 后的 `hands-on-agentic-ai/`）执行。纯离线，不需要 Ollama；依赖已装在仓库根 `.venv`（见 [docs/langchain.md](../../docs/langchain.md) 的「环境配置」节）。

```bash
cd langchain/06_checkpointer              # 在仓库根目录执行
source ../../.venv/bin/activate           # 也可直接用 ../../.venv/bin/python
python3 checkpointer.py
```

真实输出（节选：省略分隔线，以空行代替）：

```text
[06] Checkpointer：断点恢复与时间旅行（纯离线）

[A] 崩溃恢复：SIGKILL 后同 thread 续跑
  子进程退出: returncode=-9（-9 = SIGKILL）
  ✅ 工作进程在步骤 4 被 SIGKILL 杀死
  崩溃时 ledger: ['s1', 's2', 's3']
  ✅ 崩溃时只留下已完成步骤 s1-s3
  续跑后 ledger: ['s1', 's2', 's3', 's4', 's5', 's6']
  续跑后 done_steps: ['s1', 's2', 's3', 's4', 's5', 's6']
  ✅ 恢复后完整跑完且每步恰好执行一次

[B] 检查点历史：每个超步一个快照
  快照数: 8（新→旧），各快照已完成步骤数: [6, 5, 4, 3, 2, 1, 0, 0]
  ✅ 快照数量覆盖全部超步且长度单调递减

[C] 时间旅行：从历史检查点分叉重放
  分叉重放结果: ['s1', 's2', 's3', 'fork', 's4', 's5', 's6'] (branch=forked)
  ✅ 分叉分支包含 fork 标记并继续跑完 s4-s6
  旧分支最终快照: ['s1', 's2', 's3', 's4', 's5', 's6'] (branch=original)
  ✅ 旧分支最终快照仍可单独读取

验收: 6/6 通过 ✅
```

诚实预期：`[A]` 段会真的启动一个子进程（`subprocess.run` 拉起脚本的 `--worker` 模式）并 SIGKILL 它（`returncode=-9` 是预期值，不是错误）。

整体耗时约 2 秒（本机实测 1.6 秒左右，其中含 1 秒等待，原因见 How It Works）。退出码：0 全部通过，1 有断言失败。

## How It Works

### 检查点是超步级、后台异步落盘的

每个超步（一批可并发节点全部执行完）结束后写一次检查点。写入由后台线程执行，与下一步节点执行并行——这是它能"几乎零开销"的原因，也带来一个真实边界：**杀进程太快时，最近 1-2 个检查点可能还没落盘**。

实验里 `s4` 开头的 `time.sleep(1.0)` 不是凑数：它模拟"跑了一段再崩"，让 `s3` 的检查点写完，从而演示"从 s4 续跑、s1-s3 不重算"。

如果不等待，恢复会从更早的检查点开始、重算最近几步——这就是"至少一次（每步至少执行一次、可能重复执行）"语义（见踩坑 1）。整个崩溃/恢复过程如下图：

![崩溃恢复：检查点让已完成步骤不重算](images/resume.sequence.svg)

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/langchain/06_checkpointer/images/resume.sequence.html)
> （或本地打开 [`images/resume.sequence.html`](images/resume.sequence.html)）。

### 恢复：同 thread + 输入传 None

续跑语句是 `graph.invoke(None, cfg)`：`None` 表示"不提供新输入，从上个检查点继续"，`cfg` 里的 `thread_id` 指向同一条会话。`[A]` 的 ledger 对比（崩溃时 `s1-s3`，续跑后恰好 `s1-s6` 各一次）证明框架跳过了已完成的超步。

### 历史与时间旅行

`get_state_history(cfg)` 返回快照列表（新→旧），每条都带 `config`（含 `checkpoint_id`）与 `values`。`[B]` 段的长度序列 `[6..0]` 说明每个超步都有据可查。

分叉三步走：挑一个历史快照 → `update_state(快照.config, 新值)` 写入增量并拿到**返回的新 config** → `invoke(None, 新config)` 续跑。

`[C]` 段从 s1-s3 快照插入 "fork" 标记后续跑，得到长度 7 的新分支；同时用分叉前的快照 config 直接 `get_state`，旧分支的最终状态（s1-s6、branch=original）原样可读——两条分支在同一 thread 上互不覆盖。

## Pitfalls & Q&A

### 踩坑清单

1. **它是"至少一次"，不是"恰好一次"**。现象：杀太快时恢复会重算最近几步（副作用重复）。原因：检查点后台异步写，硬崩溃可能丢掉最近的。解法：节点内的外部副作用做成幂等（按 id 去重、先查后写），或把副作用放在节点末尾并配合业务级幂等键。
2. **SqliteSaver 的连接必须允许跨线程**。现象：检查点表始终 0 行，进程退出时才报 `SQLite objects created in a thread can only be used in that same thread`。原因：写检查点发生在后台线程，`sqlite3.connect` 默认 `check_same_thread=True` 拒绝跨线程使用。解法：用 `SqliteSaver.from_conn_string(...)`，或自行 `sqlite3.connect(path, check_same_thread=False)`——实验最初就是因此把检查点全写丢了。
3. **从历史点续跑要用 `update_state` 返回的 config**。现象：分叉后结果与旧分支相同、fork 标记消失。原因：`invoke` 需要新分支的 `checkpoint_id`，而原快照 config 指向旧分支。解法：`fork_cfg = graph.update_state(old_cfg, ...)` 后用 `invoke(None, fork_cfg)`。

### 深入问答

**Q：恢复（resume）和重放（replay）有什么区别？**

恢复是从**最后一个**检查点继续未完的流程，目标是"把任务做完"；重放是从**任意历史**检查点再造一个分支，目标是"看看另一种走法"。前者用 `invoke(None, 当前cfg)`，后者先用 `update_state` 制造分叉点。两者共用同一套快照，但语义完全不同。

**Q：`InMemorySaver` 有什么用，反正重启就没？**

进程内的分支探索、单元测试、笔记本演示都用它——不需要清理文件。真正的分界线是"状态是否需要活过进程退出"：需要，换 `SqliteSaver`（本机）或 Postgres 等后端，图的代码一行不改。

**Q：检查点里存的是什么？会不会很大？**

状态里每个字段（LangGraph 叫通道，channel，即该字段的独立存储单元）的当前值、待执行任务与写入记录，按超步增量保存——没变的通道只记一个版本引用（指向上一版的值），不会每步全量复制。真正会让它变大的通常是消息列表类的状态；控制方式与普通内存版本相同（截断/摘要，见后续实验）。
