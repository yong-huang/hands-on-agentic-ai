# 09 · 预算与止损：给 07 的 7 轮空转装上硬天花板

> 控制面最后一块：`mh/budget.py`。07 权限门演示过模型被拒后可以连续改道
> 7 轮；本篇给它硬性天花板——`warn`（预算将尽注入"请尽快收敛"提醒）→
> `force`（撤走工具表 + 强制输出 HANDOFF 三行摘要）。超限**不抛异常**：
> 止损和自然收敛从同一扇门出去，这就是优雅降级。

## 1. 为什么需要它

Databricks 的失败模式清单里"延迟""上下文腐化""无限循环"全都指向同一件事：
agent 不知道自己该停。alphaXiv 论文的数据更狠——失败任务的 token 消耗是
成功任务的 **2.7 倍**，支架常让模型陷入无效推理循环。预算不是性能优化，
是**故障止损**：把钱和轮次的上限从"祈祷模型自觉"变成"harness 说了算"。

## 2. 总览：核心机制一图看懂

![预算止损时序](images/budget.sequence.svg)

**怎么看这张图**：主循环每轮先过预算闸。warn 档只在消息尾部附加提醒
（工具还在，模型可收尾可继续）；force 档则**撤走整个工具表**再要最终
回答——物理禁止而非口头禁止，这是本篇最重要的设计决策。

心智模型一句话：**止损不是打断 agent，而是换一种它无法拒绝的方式让它收尾。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/harness/09_budget/images/budget.html)
> （或本地打开 [`images/budget.html`](images/budget.html)）。

## 3. 快速开始

```bash
cd harness/09_budget
MOCK=1 python3 demo.py    # 离线三组对照
python3 demo.py           # 真机: 无预算对照 / 步数预算 / token 预算
```

真机实测（2026-09-19，qwen3.8）：

```text
① 对照组: 自然 3 轮完成 5/5（模型两条批量 bash 干完全部活）
② 步数预算 max_turns=2: 预算事件 [(warn,1),(force,2)] → HANDOFF 三行摘要 ✅
③ token 预算 ~100: 事件 [(force,3)] → HANDOFF ✅
   已完成: 创建 d1~d5 五个目录并统计确认均为 1 行
   未完成: 无
   关键文件: d1/f.txt … d5/f.txt
```

## 4. 核心概念

### 4.1 优雅降级三原则

1. **不抛异常**：预算超限走正常返回路径，`result["final"]` 就是 HANDOFF；
2. **force 轮撤走 tools**：`tools=None` 后模型协议上无法再调用工具——
   口头禁止（"别再调工具了"）在 07 已被证明会被绕过；
3. **HANDOFF 固定三行**：已完成/未完成/关键文件——止损输出必须可交接，
   人或下一个 agent 能拿着它继续。

### 4.2 真机发现：强模型批量执行让预算很难自然触发

qwen3.8 把"5 目录 × 建目录+写文件+统计"合并成两条 bash，3 轮干完——
预算两次都没触发。最终演示口径改为**预算低于自然轮次**（max_turns=2），
才逼出止损路径。这条设计约束直接写进后续实验：**16 评测台的任务集必须
有"不可批量"的串行依赖，预算指标才有区分度**。

### 4.3 中途 system 消息会被无视

第一版 force 用 `role: "system"` 注入收尾指令，qwen3.8 完全无视、照常
输出任务汇报。改成**对话尾部的 user 消息**后立刻遵守。教训：会话中途的
system 消息在本地模型上权重不可靠，关键指令要用 user 角色 + 固定格式要求。

## 5. 代码关键点

```python
Budget(max_turns=…, max_tokens=…)      # 双维度, warn 在 80%/max-1 触发
budget_chat_fn(chat_fn, budget)        # 包一层 chat_fn, loop 零改动
# force 轮: chat_fn(finalize, tools=None) —— 撤走工具表
```

token 计量用字符估算（~3 字符/token，中英混合），够预算判断用；精确
计量（Ollama 响应里的 `eval_count`）归 16 评测台。

## 6. 文件结构

```
harness/
├── mh/
│   └── budget.py        # ⛓️ 本篇: Budget / budget_chat_fn
└── 09_budget/
    ├── README.md
    ├── demo.py          # 三组对照验收
    └── images/          # 时序图三件套
```

## 7. 深入要点

- **为什么 warn 不直接撤工具？** 给模型留"体面收尾"的机会——多数任务在
  warn 档就能自然收敛，节省一轮 force。人被 deadline 逼一逼也会先收尾。
- **HANDOFF 为什么不自动存盘？** 它是模型输出，可信度未经验证；11 会话
  持久化会把**工具副作用**（权威事实）落盘，HANDOFF 只是给人看的摘要。
- **轮次和 token 两个维度都要吗？** 要。轮次限"死循环"，token 限"单轮
  爆炸"（超长命令/超长输出）——07 的 7 轮空转是前者，yes 刷屏是后者。
- **止损后任务算成功还是失败？** 都不是——HANDOFF 引入第三种终态：
  "预算内未竟，可交接"。16 评测台会给它单独计分。

## 8. 总结

控制面三件套集齐：权限门（做不做）+ Hook（对不对）+ 预算（多久停），
loop 从头到尾零改动——接口预埋（04）的回报开始兑现。下一篇进入第四阶段
上下文工程：[10_compaction](../10_compaction/README.md) 上下文压缩，
让 agent 跑得久。
