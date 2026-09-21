# 04 · ⛓️ 最小 Agent Loop：mini-harness v0.1 首航

> 前三篇回答了"harness 是什么、差在哪、怎么量化"；从这一篇起**正式开工造**。
> `harness/mh/` 包今天诞生，第一个器官是主循环：带工具 schema 请求模型 →
> 执行 tool_calls → 结果回填 → 直到无 tool_calls 收敛。34 行循环体，撑起
> 后面 13 个实验的全部骨架。规则只有三条：**先执行再收尾、assistant 先落
> 历史再回填、无 tool_calls 即收敛**。

## 1. 为什么需要它

`agents/07_agent_loop` 已经写过生产级循环——那是 framework 视角的"能跑"。
本篇是 harness 视角的"可生长"：`mh/loop.py` 刻意保持极简（~60 行），但
**接口按 17 个模块的形状设计**——`chat_fn` 可注入（Mock/重试）、`on_event`
可观测（09 预算/16 评测要挂钩）、`cwd` 强制工作目录（06 沙箱）、工具表
`{name: {desc, schema, fn}}` 是 05 工具契约的原材料。这一步走对了，
后面每篇就是"加一个文件、过一遍验收"。

## 2. 总览：核心机制一图看懂

![agent loop 时序](images/agent_loop.sequence.svg)

**怎么看这张图**：一次任务 = 若干个完整回合。每回合主循环带 tools schema
请求模型；返回 `message.tool_calls` 就逐个执行（**先执行再收尾**），结果以
`role:tool` 回填再进下一回合；返回纯文本即收敛。轮次上限是最后的安全网。

心智模型一句话：**主循环是"模型意图"与"真实副作用"之间的传送带。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/harness/04_min_loop/images/agent_loop.html)
> （或本地打开 [`images/agent_loop.html`](images/agent_loop.html)）。

## 3. 快速开始

```bash
cd harness/04_min_loop
MOCK=1 python3 demo.py          # 离线：mock 走完整 tool_calls 协议
python3 demo.py                 # 真机：全自主完成两步任务（验收口径）
python3 demo.py --trace         # 打印完整消息历史
```

真机实测（2026-09-18，qwen3.8，3 轮 2 次工具调用，零人工干预）：

```text
--- 第 1 轮 ---
  >> run_bash({"command": "cat > hello.py << 'EOF'\nfrom datetime import date ..."})
--- 第 2 轮 ---
  >> run_bash({"command": "python3 hello.py"})
--- 第 3 轮 ---
[验收] hello.py 存在: ✅
[验收] 脚本输出 = 今天(2026-09-18): 2026-09-18 ✅
[验收] 最终回答: 已完成。hello.py 已创建并成功运行，脚本输出为 2026-09-18
```

## 4. 核心概念

### 4.1 循环三定律

1. **先执行再收尾**：模型习惯"命令 + 任务完成"同轮输出（01 实验的致命
   bug），循环必须先执行完所有 tool_calls 再判收敛；
2. **assistant 先落历史**：带 `tool_calls` 的 assistant 消息要先 append，
   tool 结果才能对上号（Ollama 协议要求，`agents/11` 已验证）；
3. **无 tool_calls 即收敛**：不猜模型"想不想继续"，协议说了算。

### 4.2 thinking 字段彩蛋

`--trace` 会看到 qwen3.8 的回复里 `content` 为空、推理在 `"thinking"` 字段：
Ollama 把混合推理模型的思考单独存放。`mh/llm.py` 保留该字段原样透传——
这正是 10 上下文压缩要治理的对象之一（思考比正文更占上下文）。

### 4.3 工具表：一切工具系统的种子

```python
TOOLS = {"run_bash": {"desc": ..., "schema": {...}, "fn": run_bash}}
```

三件套（描述/schema/函数）就是 05 工具契约的输入；`fn(**args)` 的裸调用
在 05 会被 schema 校验包住，在 07 会被权限门拦截，在 08 被 hooks 环绕。
**今天故意让它是裸的——先看见不设防的样子，才知道每层防线加在哪。**

## 5. 代码关键点

```python
run_agent(task, tools, max_turns=8, chat_fn=None, cwd=None, on_event=None)
# → {"final", "turns", "tool_trace", "messages"}
```

- `chat_fn` 注入点：默认 `mh_llm.chat_with_retry`（重试+弹性超时），
  `MOCK=1` 时换剧本；16 评测台会用同一接口切模型；
- `except Exception → f"{type(e).__name__}: {e}"` 直传：v0.1 刻意裸奔，
  05 的第一个对比数据就用它；
- `for…else` 兜底轮次上限，超限不算崩溃，返回已有 trace。

## 6. 文件结构

```
harness/
├── mh/                  # mini-harness 包（本系列载体，逐项目生长）
│   ├── __init__.py      # 模块地图与版本
│   ├── llm.py           # 共用客户端: /api/chat + tools + 重试
│   └── loop.py          # ⛓️ 本篇: 主循环
└── 04_min_loop/
    ├── README.md
    ├── demo.py          # 两步任务验收 + --trace
    └── images/          # 时序图三件套
```

## 7. 深入要点

- **为什么不用 LangChain 的循环？** 本系列要的就是"循环里每一行都是自己的"。
  09 预算、10 压缩都要在循环体里插桩，用别人的循环等于在别人的房子里走线。
- **max_turns=8 够吗？** 两步任务 3 轮收敛，8 是 2.6 倍冗余；16 评测台会
  统计分布后再定生产值。
- **为什么 `cwd` 是 run_agent 的参数而不是工具的？** 工作目录是**任务级**
  约束，模型不该有权选择"在哪执行"——权限模型（07）的第一课。
- **收敛判据为什么信协议不信文本？** 与 01 判分铁证同源：确定性信息
  （tool_calls 有无）优于概率性信息（"任务完成"字样）。

## 8. 总结

`mh/` 包 v0.1 上线：60 行循环，真实模型下 3 轮全自主完成两步任务。
它现在不设防——参数不校验、命令无边界、成本无计量，这些"裸奔"每一项都
会在后续实验变成一个模块。下一篇 [05_tool_contract](../05_tool_contract/README.md)
给工具调用装上 schema 校验与错误回传，顺便回答 03 遗留的问题：
**注入扰动后，契约治理能拉开多少差距？**
