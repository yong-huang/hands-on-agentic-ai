# 16 · 上下文构建与注入：System Prompt 是组装出来的

> `build_system_prompt()` 把 Identity（角色）、Memory（记忆）、Workspace
> （工作区）、Tools（工具）、Rules（规则）五类上下文来源按固定顺序拼成
> 最终 prompt，逐段计量占比，并用对照实验验证注入生效。

## Background

早期 Agent 的 System Prompt（系统提示词，发给模型的最高优先级指令文本）
是手写的：一个写死在代码里的字符串，改一个字都要动代码。

手写字符串在动态环境里撑不住：工具列表随 Registry（工具注册表，12 实验
的主题）增减、记忆随对话沉淀、工作区随项目切换。prompt 写死意味着每次
环境变化都要人工同步，漏改一次模型就在用过期信息干活。

运行时组装器因此出现：每次会话开始时扫描各上下文来源，现场拼出
System Prompt。Claude Code 等 Agent 产品的 System Prompt 就是这种构建
方式——不是一段固定的文案，而是每次运行都重新组装的产物。

## What

System Prompt 是模型的"运行说明书"，上下文注入（context injection）
指在运行时把动态信息拼进这份说明书。本实验的核心结论：**System Prompt
是组装出来的**。

五段式结构——Agent 与普通聊天机器人的分水岭，是它的 System Prompt 里
塞了多少"运行时上下文"。五个组成段如下：

| 段 | 来源 | 对应真实 Agent 的什么 | 组装后占比（本实验实测） |
| :--- | :--- | :--- | :--- |
| Identity | IDENTITY 配置 | 角色定义文件 | 8.4% |
| Memory | MEMORY.md | 跨会话记忆（17/19 实验） | 26.4% |
| Workspace | 目录扫描快照 | 工作区上下文 | 28.4% |
| Tools | Registry / MCP | 工具清单（12/14 实验） | 17.7% |
| Rules | 规则文件 | 行为约束与红线 | 19.0% |

表中 MCP 是 14 实验的工具接入协议。

组装器在拼接的同时返回逐段统计（字符数 / 估算 token / 占比）——**组装即
计量**。token（模型计费与计长的最小文本单位）估算用教学级启发式
（近似规则：CJK 即中日韩字符按 1 字 1 token、其余 4 字符 1 token）。

生产环境请用 tiktoken（OpenAI 的精确计数库）或模型自有 tokenizer。

心智模型一句话：**System Prompt = 五段上下文的有序拼接，顺序即优先级。**

## When to Use

判断标准：是否有会随时间或环境变化的上下文需要喂给模型。

典型场景：

- Agent 同时挂多类动态上下文时（记忆、工作区、工具清单）：每次会话都
  需要最新状态，手写跟不上；
- 需要管理上下文预算时：逐段占比计量是决定"压缩谁、截断谁"的依据；
- 角色与规则需要配置化时：改 IDENTITY/Rules 文件即可，不动代码。

何时不用：

- 单轮固定任务的简单应用：一段写死的 system 字符串完全够用；
- 上下文来源唯一且不变：组装器的拆分与计量是额外复杂度，没有收益。

同类方案对比：

| 方案 | 差异 | 什么时候选它 |
| :--- | :--- | :--- |
| 手写固定 System Prompt | 内容静态，改一次动一次代码 | 单轮固定任务 |
| 模板引擎渲染（如 Jinja2） | 能填变量，但无逐段计量、无来源管理 | 变量少且固定的半动态场景 |
| 运行时组装器（本实验） | 五段来源动态拼接 + 逐段计量 | 多来源动态上下文的 Agent |

## Quick Start

前置条件：`--demo` 完全离线，不需要 Ollama（本地大模型运行环境）；真实
模式需要 Ollama 与 qwen3.8 模型在线。

```bash
cd agents/16_context_injection
python context_injection.py --demo   # 离线：三阶段演进 + 占比报告（无需 Ollama）
python context_injection.py          # 真实：组装后注入 qwen3.8，对照实验验证
```

`--demo` 依次展示三个阶段：只有 Identity（01–15 实验积累的状态）→
+Memory+Workspace → +Tools+Rules 完整形态，每阶段打印占比表。

真实模式做两组验证加一组对照：问"我叫什么名字？喜欢吃什么？"（答案
只在注入的 Memory 里）、"打个招呼吧"（称呼约定在 Memory 里）；对照组
用裸 Identity 问同样的问题。

**预期输出**：完整 prompt 下模型答出"张三、
火锅、不能吃辣"并称呼"张三同学"；对照组答不出来——差异全部来自注入，
这就是"注入生效"的证据。

## How It Works

组装函数——五个 `(段名, 内容)` 元组按序拼接，同时累出逐段统计：

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

`--demo` 每阶段打印的占比表，就是循环里 `stats.append(...)` 那三行算出
的 `chars`/`tokens`/`pct`——你在输出里看到的 26.4%、28.4% 都来自这里。

**顺序即优先级**：模型对靠前的内容更敏感，所以 Identity 永远第一、
Rules 收尾、Memory/Workspace 居中。调整顺序不需要改任何一段的内容——
这正是组装优于手写的地方；但也因此不要按"重要程度"随意插队。

**注入生效的验证设计**：实验组（完整 prompt）答对只存在于 Memory 里的
答案，对照组（裸 Identity）答不出——两组差异只能来自注入。**任何"我
加了 XXX 到 prompt"的改动，都应该有一个能区分注入前后的探针问题。**

## Pitfalls & Q&A

踩坑清单（现象 + 原因 + 解法）：

- **注入了记忆但模型不照做**。现象：称呼约定有时被无视。原因：Memory
  注入 ≠ 模型服从，记忆是"弱约束"。解法：硬约束走 Rules + 校验
  （甚至 15 实验的审批层）。
- **Workspace 快照撑大 prompt**。现象：目录文件一多，这一段占比暴涨。
  原因：直接 `os.listdir` 把无关文件全塞进来。解法：生产要做过滤与
  截断（13 实验的大结果卸载思想）。
- **上下文拼进了 user 消息**。现象：模型把背景信息当成用户说的话来
  回应。原因：注入位置错了。解法：组装产物以 `messages[0]`（system
  角色）注入，不拼进 user 消息。
- **token 占比与真实计费对不上**。现象：估算偏差明显。原因：启发式对
  混合中英文误差可达 ±20%。解法：生产用 tiktoken 或模型自有 tokenizer，
  启发式只用于趋势观察。

**Q1: 如何验证一段上下文注入后真的影响了模型？**

设计只有注入内容才能答对的探针问题，并跑一个不注入的对照组——两组
输出差异即注入生效的证据（完整设计见 How It Works）。

**Q2: token 占比报告有什么工程价值？**

上下文预算管理的基础——知道每段占多少，才能决定压缩谁（摘要 Memory）、
截断谁（Workspace 快照），见 18 实验（上下文压缩主题）。
