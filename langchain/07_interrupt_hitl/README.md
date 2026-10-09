# 07 · interrupt 与 Human-in-the-loop

> interrupt（中断）让正在跑的图（LangGraph 的工作流图：节点＝一个执行步骤，边＝步骤之间怎么跳转）在指定位置暂停、把决策交给人类；`Command(resume=...)` 把决定送回去、从暂停点继续——这就是 Human-in-the-loop（HITL，人在回路：关键动作由人拍板）。
> 本篇做两级实验：离线段自建"审批闸门"节点，回放 approve / edit / reject 三种决策；真机段用 `HumanInTheLoopMiddleware` 拦住危险工具，验证编辑参数真实生效、拒绝后工具不执行。
> 读完你能把"人工确认"做成流程里的标准停顿，而不是把危险动作藏在提示词里。

## Background

自动化流程迟早会遇到"不该让机器单独决定"的动作：删文件、扣款、对外发信。此前的做法只有两个极端——把这类动作从自动化里剔除，人工全程代劳；或者写进提示词叮嘱模型"别乱来"——但提示词是建议，不是闸门。

中间路线需要一种机制：流程跑到关键点**停下来等人**，人不在时可以退出程序、明天再来，决定之后流程从停顿点继续。难点在于"停下"之后状态还在不在——如果状态只在内存里，进程一退就得从头再来。

LangGraph 把这件事做成内建机制：`interrupt` 让节点（图里执行一个步骤的函数）抛出暂停信号，状态由 checkpointer（检查点保存器：把图每一步的状态快照存进内存或磁盘的组件）持久化；恢复时用 `Command(resume=...)` 把决定送回暂停点。人不在场的等待，进程可以完全退出。

## What

interrupt 是一种"声明在节点内、由调用方补齐"的暂停原语：调用 `interrupt(payload)` 的节点立即暂停，`payload` 成为调用方收到的 `__interrupt__`。

调用方稍后用 `Command(resume=value)` 恢复，`value` 成为 `interrupt()` 的返回值，节点继续执行。

可以把这想象成审批窗口的叫号机：办事员（节点）把材料递进窗口就停手，号单（payload）交给柜台；人到齐后凭号单把答复（resume value）送回同一个窗口，办事员接着办。但和叫号机不同的是：**流程可以整体退出**——等待不占用任何进程资源，号单（状态）存在磁盘里。

两种粒度，用途不同：

| 粒度 | 挂什么位置 | 实验中的形态 |
|:--|:--|:--|
| 节点级 | 自定义节点里调 `interrupt()` | `[A]` 段的自建审批闸门 |
| 工具级 | `HumanInTheLoopMiddleware` 钩住危险工具 | `[B]` 段的删除审批 |

三种决策的语义：**approve**（按原参数执行）、**edit**（用修改后的参数执行）、**reject**（不执行，把理由回给模型）。

## When to Use

典型场景：

1. 不可逆动作审批：删除、付款、发布、对外通信，执行前等人放行。
2. 流程中缺人才能提供的信息：让操作员二选一、补充参数后再继续。
3. 合规留痕：每次放行/修改/拒绝都有状态记录（配合 06 实验的检查点历史：checkpointer 存下的历次状态快照）。

何时不用：可逆的小动作尽量别拦——人人都被弹窗问一遍的审批会迅速疲劳，最后无脑点通过；拦关键动作、一次授权批量执行，是更可持续的策略。

同类方案对比：

| 方案 | 暂停在哪 | 什么时候选它 |
|:--|:--|:--|
| 提示词约束 | 无真正暂停 | 低风险场景的习惯性防线 |
| 工具内确认输入 | 工具函数里 `input()` | 单机脚本、单工具 |
| interrupt / HITL（本篇） | 图运行时，状态持久化 | 流程级审批，可跨进程等待 |

## Quick Start

以下命令从仓库根目录（clone 后的 `hands-on-agentic-ai/`）执行。

依赖已装在仓库根 `.venv`（见 [docs/langchain.md](../../docs/langchain.md) 的「环境配置」节）；真机段需要本机 Ollama（在本地运行大语言模型的服务）已启动且已拉取 `qwen3.8:latest`。

```bash
cd langchain/07_interrupt_hitl            # 在仓库根目录执行
source ../../.venv/bin/activate           # 也可直接用 ../../.venv/bin/python
python3 interrupt_hitl.py                 # 真机：A 离线 + B 调模型（3 次审批流程）
python3 interrupt_hitl.py --demo          # 离线：只跑 A 段
```

真实输出（节选：省略分隔线，以空行代替）：

```text
[07] interrupt 与 Human-in-the-loop
模式: 真机（qwen3.8:latest）

[A] 节点级中断：interrupt 暂停 + Command(resume) 三种决策（离线）
  暂停时的问题: 是否执行 delete_file? args={'path': 'old.txt'}
  ✅ 审批闸门在动作执行前暂停
  approve -> executed=['delete_file(old.txt)']
  ✅ approve：原参数执行
  edit    -> executed=['delete_file(old-v2.txt)']
  ✅ edit：用修改后的参数执行
  reject  -> executed=[] notes=['rejected: 先不删了']
  ✅ reject：不执行且记录理由

[B] 工具级中断：中间件在危险工具前暂停（真机）
  approve 场景暂停: True
  ✅ 危险工具执行前中断
  approve -> 审计列表: ['old.txt']
  ✅ approve：工具按原参数执行
  edit    -> 审计列表: ['archive/old.txt']
  ✅ edit：工具收到修改后的参数
  reject  -> 审计列表: []，拒绝消息 1 条
  ✅ reject：工具未执行且模型收到拒绝理由

验收: 8/8 通过 ✅
```

诚实预期：`[B]` 段跑三个独立的审批流程（三种决策各一次），依赖真机模型的工具调用行为，连跑多次均 8/8；整轮真机约 10 秒上下（本机实测模型已驻留约 6 秒；冷加载或较慢机器会更久）。Ollama 未启动时真机部分跳过（退出码 2），`--demo` 只跑 A 段（4/4）。

## How It Works

### 节点级：暂停、回放、恢复

`review` 节点调用 `interrupt(payload)` 后立即停住；`invoke` 返回的 `__interrupt__` 里带着审批问题。

恢复时 `Command(resume={"type": "approve"})` 的值成为 `interrupt()` 的返回值——节点**重新执行但不会再次暂停**，直到下一个 interrupt。

`[A]` 段的三个独立 thread（会话标识：每个 thread_id 对应一份独立状态，不是操作系统线程）各演示一种决策：approve 执行原参数、edit 用 `{"path": "old-v2.txt"}` 执行、reject 不执行并把理由记进 `notes`。三种结果的分流结构如下图：

![审批闸门：interrupt 暂停后，三种决策分流](images/hitl.architecture.svg)

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/langchain/07_interrupt_hitl/images/hitl.architecture.html)
> （或本地打开 [`images/hitl.architecture.html`](images/hitl.architecture.html)）。

### 工具级：中间件把 ID 和载荷都替你管好

`HumanInTheLoopMiddleware(interrupt_on={"delete_file": {"allowed_decisions": [...]}})` 在危险工具执行前暂停，`__interrupt__` 里是结构化请求（工具有名有参、还带 `allowed_decisions`）。

恢复载荷是 `{"decisions": [决策]}`：approve 直接执行；edit 必须带 `"edited_action": {"name": ..., "args": ...}`，框架用改名后的工具和参数重建调用。

reject 可带 `"message"` 理由，框架把它包装成一条状态为 error 的 `ToolMessage`（工具消息：对话中代表"工具执行结果"的消息类型，这里装的是拒绝理由）交给模型。

`[B]` 段的审计列表直接证明三种决策落到工具上的差异：`['old.txt']`、`['archive/old.txt']`、`[]`。

### 恢复载荷的格式差异

两级实验的 resume 载荷并不一样：节点级是**你自定义的任意值**（`{"type": "approve"}`），由你的节点自己解释。

工具级是**框架约定的结构**（`decisions` 数组 + `edited_action`/`message` 字段）。混用会在恢复时报错或行为不符——记住"谁的 interrupt，谁的格式"。

## Pitfalls & Q&A

### 踩坑清单

1. **没有 checkpointer 就无法恢复**。现象：`RuntimeError: Cannot use Command(resume=...) without checkpointer`。原因：暂停点的状态必须有地方存，否则进程内没留、进程外没有。解法：编译图时挂 `InMemorySaver`（进程内）或 `SqliteSaver`（跨进程，等待期间可退出程序）。
2. **工具级 edit 的载荷容易少一层**。现象：恢复时报字段错误。原因：期望的是 `{"type": "edit", "edited_action": {"name": ..., "args": {...}}}`，只传 `args` 不行。解法：按框架的类型定义构造决策；改工具名也走 `edited_action.name`。
3. **interrupt 的节点会整体重跑**。现象：节点里 interrupt 之前的副作用（写文件、打日志）执行了两次。原因：恢复时节点从函数开头重新执行，`interrupt()` 这次直接返回恢复值。解法：把副作用放在 interrupt 之后，或保证幂等（同一操作重复执行与只执行一次效果相同——按路径删除天然幂等，追加一行不幂等）。

### 深入问答

**Q：流程"暂停"的时候，进程一直在等我吗？**

不等。interrupt 只是让图的一次 `invoke` 返回（带着 `__interrupt__`），进程可以照常退出；等待的是"下一步的调用"而不是进程。跨天等待就用 `SqliteSaver`，第二天新进程用同一 thread 恢复。

**Q：节点级和中间件级怎么选？**

要拦的具体工具已经存在（删文件、发邮件）→ 用中间件，声明式配置最少、载荷由框架管理；要暂停的位置不是"某个工具"而是流程步骤（比如"等参数补充后再决定调哪个工具"）→ 自建节点 + `interrupt()`。两者可以混用：中间件拦工具，节点拦流程。

**Q：怎么避免审批疲劳？**

三个手段：只拦真正危险的少数工具；相同动作提供"本次会话内一直允许"的选项（由你的审批界面实现，决策值可自定义）；把审批和 06 的检查点历史结合，事后审计谁放行了什么，而不是事前拦截一切。
