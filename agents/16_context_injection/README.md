# 16 · 上下文构建与注入：System Prompt 是组装出来的

> 项目 01-15 的 System Prompt 都是写死的一行字符串——改角色要动 prompt、不知道
> 它有多大、也无法证明模型真的"读到"了它。从本篇进入第四阶段：System Prompt
> 不该手写，而该**组装**。`build_system_prompt()` 把 Identity（角色）、Memory
> （记忆）、Workspace（工作区）、Tools（工具）、Rules（规则）五类上下文来源
> 按固定顺序拼成最终 prompt，逐段计量占比，并用对照实验验证注入生效。

## 1. 为什么需要它

Agent 与普通聊天机器人的分水岭，是它的 System Prompt 里塞了多少"运行时上下文"：
你是谁（Identity）、用户是谁（Memory）、周围有什么（Workspace）、能做什么
（Tools）、什么不能做（Rules）。这些内容都是动态的——工具列表随 Registry 变化、
记忆随对话沉淀、工作区随项目切换。**手写 prompt 无法跟随这些变化**，必须有一个
组装器在运行时构建它。这也是 Claude Code 等 Agent 产品的 System Prompt 构建方式。

## 2. 总览：核心机制一图看懂

![System Prompt 的五段式组装](images/context_assembly.dataflow.svg)

**怎么看这张图**：左侧四类来源（Identity / MEMORY.md / 工作区快照 / 工具与规则）
各自独立维护，汇入中间的 `build_system_prompt()` 按固定顺序拼接；产物一路发给
qwen3.8 做注入验证，另一路输出占比报告（组装即计量）。

心智模型一句话：**System Prompt = 五段上下文的有序拼接，顺序即优先级。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/16_context_injection/images/context_assembly.dataflow.html)（或本地打开 [`images/context_assembly.dataflow.html`](images/context_assembly.dataflow.html)）。

## 3. 快速开始

```bash
cd agents/16_context_injection
python context_injection.py --demo   # 离线：三阶段演进 + 占比报告（无需 Ollama）
python context_injection.py          # 真实：组装后注入 qwen3.8，对照实验验证
```

`--demo` 依次展示三个阶段：只有 Identity（项目 01-15 的状态）→ +Memory+
Workspace → +Tools+Rules 完整形态，每阶段打印占比表。

真实模式做两组验证加一组对照：问"我叫什么名字？喜欢吃什么？"（答案只在注入的
Memory 里）、"打个招呼吧"（称呼约定在 Memory 里）；对照组用裸 Identity 问同样
的问题。**预期输出**：完整 prompt 下模型答出"张三、火锅、不能吃辣"并称呼
"张三同学"；对照组答不出来——差异全部来自注入，这就是"注入生效"的证据。

## 4. 核心概念

### 4.1 五段式结构

| 段 | 来源 | 对应真实 Agent 的什么 | 组装后占比（本实验实测） |
| :--- | :--- | :--- | :--- |
| Identity | IDENTITY 配置 | 角色定义文件 | 8.4% |
| Memory | MEMORY.md | 跨会话记忆（项目 17/19） | 26.4% |
| Workspace | 目录扫描快照 | 工作区上下文 | 28.4% |
| Tools | Registry / MCP | 工具清单（项目 12/14） | 17.7% |
| Rules | 规则文件 | 行为约束与红线 | 19.0% |

**顺序即优先级**：模型对靠前的内容更敏感，所以 Identity 永远第一、Rules 收尾。
调整顺序不需要改任何一段的内容——这正是组装优于手写的地方。

### 4.2 组装即计量

`build_system_prompt()` 在拼接的同时返回逐段统计（字符数 / 估算 token / 占比）。
prompt 的大小必须时时可见：Memory 和 Workspace 通常是大头，它们膨胀的速度就是
你需要上下文压缩（项目 18）的速度。token 估算用教学级启发式（CJK 1 字 1 token、
其余 4 字符 1 token），**生产环境请用 tiktoken 或模型自有 tokenizer**。

### 4.3 注入生效的验证

"注入了"和"注入生效"是两回事。本篇的验证设计是一个对照实验：

- 实验组：完整 prompt + "我叫什么名字？"→ 答对（答案只存在于注入的 Memory）；
- 对照组：裸 Identity + 同样的问题 → 答不出。

两组差异只能来自注入的上下文。**任何"我加了 XXX 到 prompt"的改动，都应该有
这样一个能区分注入前后的探针问题。**

### 4.4 易错点

- Memory 注入≠模型服从：验证 2 里的称呼约定是"弱约束"，模型多数时候遵守但不
  保证；硬约束要走 Rules + 校验（甚至项目 15 的审批层）。
- Workspace 快照直接 `os.listdir` 会把无关文件全塞进 prompt——生产要做过滤
  与截断（项目 13 的大结果卸载思想）。
- 五段的拼接顺序不要按"重要程度"随意插队：模型对开头的注意力显著更强。

## 5. 代码关键部分

```python
def build_system_prompt(identity, memory, workspace, tools, rules):
    sections = [
        ("Identity", f"你是 {identity['name']}，{identity['role']}。语气: {identity['tone']}。"),
        ("Memory",   f"## 关于用户的长期记忆\n{memory}"),
        ("Workspace", f"## 当前工作区\n{workspace}"),
        ("Tools",    f"## 可用工具\n{tools}"),
        ("Rules",    f"## 行为规则\n{rules}"),
    ]
    parts, stats = [], []
    total_chars = sum(len(body) for _, body in sections) or 1
    for name, body in sections:
        parts.append(f"### {name}\n{body}")
        stats.append({"name": name, "chars": len(body),
                      "tokens": estimate_tokens(body),
                      "pct": len(body) / total_chars * 100})
    return "\n\n".join(parts), stats
```

坑清单：

- 组装产物以 `messages[0]`（system 角色）注入，不要把上下文拼进 user 消息；
- `estimate_tokens` 的启发式对混合中英文误差可达 ±20%，只用于趋势观察；
- 改任何一段只需改对应来源常量（或未来改为读文件），组装器与报告自动跟随。

## 6. 文件结构

```
16_context_injection/
├── README.md                            # 本篇教程
├── context_injection.py                 # 主脚本（约 230 行）：五段组装 + 占比报告 + 注入验证
└── images/
    ├── context_assembly.dataflow.json   # 图源：dataflow 类型（来源→组装→产物→验证）
    ├── context_assembly.dataflow.html   # 交互版架构图
    └── context_assembly.dataflow.svg    # 双主题矢量图
```

## 7. 面试要点

- **Q: Agent 的 System Prompt 通常由哪几部分组成？**
  A: Identity（角色）、Memory（记忆）、Workspace（环境/工作区）、Tools（工具
  清单）、Rules（规则）五类，运行时按固定顺序动态组装。
- **Q: 为什么 System Prompt 要动态组装而不是手写？**
  A: 组成部分都是运行时状态（工具列表、记忆、工作区随时间变化），手写无法跟随；
  组装器还便于逐段计量与做上下文预算管理。
- **Q: 如何验证一段上下文注入后真的影响了模型？**
  A: 设计只有注入内容才能答对的探针问题，并跑一个不注入的对照组——两组输出
  差异即注入生效的证据。
- **Q: 五段的排列顺序有什么讲究？**
  A: 模型对 prompt 开头的注意力更强：Identity 最前、Rules 收尾；Memory/Workspace
  居中。顺序即优先级，不要随意调整。
- **Q: token 占比报告有什么工程价值？**
  A: 上下文预算管理的基础——知道每段占多少，才能决定压缩谁（摘要 Memory）、
  截断谁（Workspace 快照），这正是下一篇的主题。

## 8. 总结

System Prompt 从"写死的字符串"变成"五类来源的有序组装"，组装即计量让上下文
大小第一次可见，对照实验让注入效果第一次可证。但 Memory 现在还是写死的常量——
下一篇让 Agent 真正拥有跨会话的记忆：短期滑动窗口 + 长期向量检索。
