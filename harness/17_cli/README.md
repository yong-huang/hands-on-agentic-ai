# 17 · 🏁 终极总装：mini-harness CLI（类 Claude Code 终端）

> 十六个实验的零件在这一篇拧成一台机器：`mh/cli.py` 把 12 个模块接进一个
> 交互式 REPL（`/help` `/context` `/budget` `/resume` `/memory` `/quit`），
> 每个会话留一条证据线（`harness_session.log`）。端到端验收是一个真实
> 任务：**给 load_resources.sh 添加 --dry-run 参数并自测**——四轮对话、
> 五断言全绿、日志里权限拒绝与压缩事件全部留痕。

## 1. 为什么需要它

零件齐了不等于机器能跑：模块间的**接缝**（chat_fn 包装链的顺序、证据线
的贯通、空回复的兜底）只有总装才暴露。本篇还是整个系列的"使用说明书"：
装好之后你拥有一个本地、免 Key、可审计的类 Claude Code 终端。

## 2. 总览：核心机制一图看懂

![mini-harness CLI 总装接线](images/cli.architecture.svg)

**怎么看这张图**：REPL 是唯一入口，每回合经 budget（计量止损）→
compaction（历史瘦身）→ loop（三定律）推进；工具调用在 perm→hooks→
tools+sandbox 的治理链上过三道闸；memory/skills/session 从上侧注入
system 与恢复状态。虚线都是信息流，实线是执行流。

心智模型一句话：**总装不是把零件摆一起，是把接缝变成证据线。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/harness/17_cli/images/cli.html)
> （或本地打开 [`images/cli.html`](images/cli.html)）。

## 3. 快速开始

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

## 4. 端到端验收（真机，2026-09-20）

| 断言 | 证据 |
|:--|:--|
| A. `--dry-run` 实现且 `bash load_resources.sh --dry-run` 自测通过 | ✅ 修改了参数解析/`run()` 包装/各步骤接入三处 |
| B. 权限拒绝证据 ≥1 | ✅ **三次**：`rm` → `mv` → `: >`（清空）全被拦 |
| B. 记忆注入证据 ≥1 | ✅ `memory_injected` |
| C. 备份完好 | ✅ `.bak` 未被动过 |
| 附加 | compaction 触发（2028→498 tok）、证据线全程留痕 |

**最精彩的现场**：第③轮让删 junk.tmp，`rm` 被拒后模型连试 `mv`、
`: > file`（清空）——**全部被权限门拦截**，最后它接受了现实。audit.log
与 session log 同时留痕，这就是 07+08+17 三层治理的合力。

## 5. 代码关键点

```python
MiniHarness(sandbox, log_path, checkpoint)
mh.turn(user_input)        # 一个输入 → 一个完整 agent 回合
mh.cmd_context/budget/resume/memory()   # 斜杠命令
```

- **chat_fn 包装链顺序**（由内向外）：record(session) → compact → budget
  ——快照在最内层保证每轮落盘，预算在最外层拥有最终否决权；
- **空回复兜底**：模型偶发"失语"（content 空、无 tool_calls），CLI 检测后
  注入"请继续完成任务并汇报"再跑一轮——**空回复是 harness 要处理的现象，
  不是用户的错**（03 的教训在总装层落地）；
- **已知治理权衡**：演示 profile 允许 `python3*`（自测需要），因此 rm-deny
  存在解释器旁路——07 的老问题，生产要白名单+容器，audit.log 已留痕。

## 6. 文件结构

```
harness/
├── mh/
│   └── cli.py           # 🏁 本篇: MiniHarness REPL(接线 12 模块)
└── 17_cli/
    ├── README.md
    ├── demo.py          # 脚本化端到端验收
    └── images/          # 总装接线图三件套
```

## 7. 深入要点

- **为什么证据线贯穿始终？** 01 的"判分铁证"哲学在总装层的体现：每个
  模块的行为都必须在日志里可回放。这也是 debugging 时唯一可信的来源
  （本次空回复问题正是靠证据线定位的）。
- **REPL 与 run_agent 的关系？** REPL 每个输入就是一次 run_agent 调用，
  `messages=` 参数跨回合携带历史——04 预埋的接口在 11/12/17 三处被复用。
- **还差什么才算 Claude Code？** 沙箱容器化、多模型路由、成本看板、
  远程审批（Slack/手机）——都是工程量而非原理，原理 18 篇已集齐。
- **斜杠命令为什么做成方法约定（cmd_xxx）？** 零注册成本：加一个命令
  = 加一个方法，REPL 主循环永不改——与 loop 同样的开闭原则。

## 8. 总结

🏁 十八个实验的终点：一个本地、免 Key、全模块可观测、治理链完整的
mini-harness。它不比 Claude Code 强，但**每一行你都知道为什么存在**。
下一篇 [18_model_vs_harness](../18_model_vs_harness/README.md) 用 2×2
对照实验给整个系列收口：换模型和换 harness，到底哪个影响大？
