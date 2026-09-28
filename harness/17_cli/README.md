# 17 · 🏁 终极总装：mini-harness CLI（类 Claude Code 终端）

> `mh/cli.py` 把 12 个模块接进一个交互式 REPL（read-eval-print loop，
> 读取-求值-打印的命令行交互循环），每个会话留一条证据线（全程留痕、
> 可回放的日志 `harness_session.log`）。端到端验收是一个真实任务：给
> load_resources.sh 添加 --dry-run（演练模式：只打印将执行的命令而不
> 实际执行）参数并自测——四轮对话、五断言全绿。读完本篇你能看懂一个
> 完整 agent 终端的接缝都在哪里。

## Background

零件齐了不等于机器能跑。总装之前，12 个模块各自有 demo 脚本、各自
验收通过，但模块之间的**接缝**没人测过：chat_fn（模型调用入口）包装
链的顺序、证据线的贯通、空回复的兜底，只有拼进同一条回合流程才暴露。
典型场景：单模块全绿，总装一跑，包装顺序错一层，证据线就断一轮。

17 实验把 12 个模块装进 `mh/cli.py`。它同时是整个系列的使用说明书：
装好之后你拥有一个本地、可审计的类 Claude Code 终端（离线演示无需
API 密钥），模型行为在日志里全程可回放。

## What

REPL 是唯一入口，每回合经 budget（预算计量止损）→ compaction（历史
压缩瘦身）→ loop（驱动模型与工具循环的主流程）推进。

工具调用在 perm（权限门）→ hooks（在动作前后插入自定义逻辑的钩子）→
tools+sandbox（限制时长与输出大小的执行环境）的治理链上过三道闸；
memory/skills/session 从上侧注入 system（系统提示）与恢复状态。

心智模型一句话：**总装不是把零件摆一起，是把接缝变成证据线。**
可以把总装想成汽车下线检测线：零件各自合格，检测线查的是装配接缝。
但和检测线不同的是：这里的检测不只做出厂那一次，而是每一回合都在
日志里留痕、随时可回放。

## When to Use

典型场景：

- 想在本地终端给模型一个带治理的执行环境干真活：改脚本、跑自测、
  全程留痕。
- 想逐个体验模块行为：`/context` 看上下文、`/budget` 看预算、
  `/resume` 从检查点存档恢复会话，证据日志随手可查。
- 给自己的 agent 项目当骨架：回合流程与治理链已经装配完毕。

何时不用：需要生产级隔离时——演示 profile（配置档）有已知权衡（见
Quick Start 末尾的诚实预期）；纯一问一答不需要工具时，直接调模型
API 更简单。

同类做法对比：

| 方案 | 差异 | 什么时候选它 |
|:--|:--|:--|
| 直接调模型 API | 纯文本进出，无工具链 | 不需要执行动作的问答 |
| 单模块 demo 脚本 | 只验证一个机制 | 调试单个模块 |
| mh CLI（本篇） | 全模块装配 + 治理链 + 证据线 | 本地真任务、要可审计 |
| Claude Code 等成熟终端 | 容器化、多模型路由等工程完备 | 生产环境日常使用 |

## Quick Start

前置条件：Python 3 环境；交互式 REPL 需要一个可用的模型接入；
`demo.py` 为脚本化端到端验收。

```bash
cd harness/17_cli
python3 demo.py                                   # 脚本化端到端验收
python3 -m mh.cli --sandbox /tmp/your-workspace   # 交互式 REPL
```

REPL 会话示例：

```text
>>> 给 load_resources.sh 添加 --dry-run 参数并自测
1. 参数解析: 新增 --dry-run / -h / --help, 未知参数报错退出码 2
2. run() 包装函数: dry-run 时只打印 [dry-run] 将执行: ... 不实际执行
3. 各步骤接入: pip install → run "$PY" -m pip install ...
/context
消息 14 条, 估算 ~1180 token
```

端到端验收（真机，断言即逐条验收的检查条件）：

| 断言 | 证据 |
|:--|:--|
| A. `--dry-run` 实现且 `bash load_resources.sh --dry-run` 自测通过 | ✅ 修改了参数解析/`run()` 包装/各步骤接入三处 |
| B. 权限拒绝证据 ≥1 | ✅ **三次**：`rm` → `mv` → `: >`（清空）全被拦 |
| B. 记忆注入证据 ≥1 | ✅ `memory_injected` |
| C. 备份完好 | ✅ `.bak` 未被动过 |
| 附加 | compaction 触发（2028→498 tok）、证据线全程留痕 |

现场还原：第③轮让删 junk.tmp，`rm` 被拒后模型连试 `mv`、`: > file`
（清空）——全部被权限门拦截，最后它接受了现实。audit.log（审计日志）
与 session log 同时留痕，这就是 07+08+17 三层治理的合力。

诚实预期与已知权衡：真机轮次与 token 数随模型波动；演示 profile 允许
`python3*`（自测需要），因此 rm-deny（拦截 `rm` 命令的规则）存在解释器
旁路（绕过防线的方法）——07 的老问题，生产要白名单+容器，audit.log
已留痕。

实现入口速览：

```python
MiniHarness(sandbox, log_path, checkpoint)
mh.turn(user_input)        # 一个输入 → 一个完整 agent 回合
mh.cmd_context/budget/resume/memory()   # 斜杠命令
```

## How It Works

一回合的时序：输入进来，先过 budget 与 compaction 两层包装，再进
loop；loop 里每次工具调用依次过 perm、hooks、sandbox 三道闸，判定
全部落 audit.log；回合结束，record 层把全程写入 `harness_session.log`。

**chat_fn 包装链顺序（由内向外）：record（会话落盘）→ compact →
budget。**快照在最内层，保证每轮都写进证据线；预算在最外层，拥有
最终否决权。

顺序错一层的后果是具体的：证据线断一轮（漏记），或止损晚一步（超支
才发现）。你在输出里看到的 `/context` 计数与 compaction
（2028→498 tok），分别就是 record 与 compact 两层留下的工作痕迹。

## Pitfalls & Q&A

踩坑清单：

- **空回复（模型偶发"失语"）**
- 现象：模型返回的 content 为空、无 tool_calls（模型请求调用工具的
  指令），回合空转。
- 原因：模型偶发行为，不是用户的错。
- 解法：CLI 检测到后注入"请继续完成任务并汇报"再跑一轮（03 的教训
  在总装层落地）。这个问题正是靠证据线定位的。

Q&A：

**Q1: 为什么证据线贯穿始终？**

01 的"判分铁证"哲学在总装层的体现：每个模块的行为都必须在日志里可
回放。这也是 debugging 时唯一可信的来源。

**Q2: REPL 与 run_agent 的关系？**

REPL 每个输入就是一次 run_agent 调用，`messages=` 参数跨回合携带
历史——04 预埋的接口在 11/12/17 三处被复用。

**Q3: 还差什么才算 Claude Code？**

沙箱容器化、多模型路由、成本看板、远程审批（Slack/手机）——都是
工程量而非原理，原理 18 篇已集齐。

**Q4: 斜杠命令（以 / 开头、不发给模型的控制指令）为什么做成方法约定
（cmd_xxx）？**

零注册成本：加一个命令 = 加一个方法，REPL 主循环永不改——与 loop
同样的开闭原则（对扩展开放、对修改关闭的设计原则）。
