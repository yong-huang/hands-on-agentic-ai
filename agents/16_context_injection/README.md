# 16 · 上下文构建与注入：System Prompt 是组装出来的

> `build_system_prompt()` 把 Identity（角色）、Memory（记忆）、Workspace
> （工作区）、Tools（工具）、Rules（规则）五类上下文来源按固定顺序拼成
> 最终 prompt，逐段计量占比，并用对照实验验证注入生效。

## What

五段式结构——Agent 与普通聊天机器人的分水岭，是它的 System Prompt 里
塞了多少"运行时上下文"：

| 段 | 来源 | 对应真实 Agent 的什么 | 组装后占比（本实验实测） |
| :--- | :--- | :--- | :--- |
| Identity | IDENTITY 配置 | 角色定义文件 | 8.4% |
| Memory | MEMORY.md | 跨会话记忆（项目 17/19） | 26.4% |
| Workspace | 目录扫描快照 | 工作区上下文 | 28.4% |
| Tools | Registry / MCP | 工具清单（项目 12/14） | 17.7% |
| Rules | 规则文件 | 行为约束与红线 | 19.0% |

组装器在拼接的同时返回逐段统计（字符数 / 估算 token / 占比）——**组装即
计量**。token 估算用教学级启发式（CJK 1 字 1 token、其余 4 字符 1 token），
生产环境请用 tiktoken 或模型自有 tokenizer。

心智模型一句话：**System Prompt = 五段上下文的有序拼接，顺序即优先级。**

## Why

五类上下文都是动态的——工具列表随 Registry 变化、记忆随对话沉淀、工作区
随项目切换。**手写 prompt 无法跟随这些变化**，必须有一个组装器在运行时
构建它。这也是 Claude Code 等 Agent 产品的 System Prompt 构建方式。

## How

```bash
cd agents/16_context_injection
python context_injection.py --demo   # 离线：三阶段演进 + 占比报告（无需 Ollama）
python context_injection.py          # 真实：组装后注入 qwen3.8，对照实验验证
```

`--demo` 依次展示三个阶段：只有 Identity（项目 01-15 的状态）→ +Memory+
Workspace → +Tools+Rules 完整形态，每阶段打印占比表。

真实模式做两组验证加一组对照：问"我叫什么名字？喜欢吃什么？"（答案只在
注入的 Memory 里）、"打个招呼吧"（称呼约定在 Memory 里）；对照组用裸
Identity 问同样的问题。**预期输出**：完整 prompt 下模型答出"张三、火锅、
不能吃辣"并称呼"张三同学"；对照组答不出来——差异全部来自注入，这就是
"注入生效"的证据。

**注入生效的验证设计**：实验组（完整 prompt）答对只存在于 Memory 里的
答案，对照组（裸 Identity）答不出——两组差异只能来自注入。**任何"我加了
XXX 到 prompt"的改动，都应该有一个能区分注入前后的探针问题。**

组装函数：

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

## Deep Dive

**顺序即优先级**：模型对靠前的内容更敏感，所以 Identity 永远第一、Rules
收尾、Memory/Workspace 居中。调整顺序不需要改任何一段的内容——这正是
组装优于手写的地方；但也因此不要按"重要程度"随意插队。

踩坑清单：

- Memory 注入≠模型服从：称呼约定是"弱约束"，模型多数时候遵守但不保证；
  硬约束要走 Rules + 校验（甚至项目 15 的审批层）；
- Workspace 快照直接 `os.listdir` 会把无关文件全塞进 prompt——生产要做
  过滤与截断（项目 13 的大结果卸载思想）；
- 组装产物以 `messages[0]`（system 角色）注入，不要把上下文拼进 user
  消息；
- `estimate_tokens` 的启发式对混合中英文误差可达 ±20%，只用于趋势观察。

## Q&A

**Q1: 如何验证一段上下文注入后真的影响了模型？**

设计只有注入内容才能答对的探针问题，并跑一个不注入的对照组——两组输出
差异即注入生效的证据。

**Q2: token 占比报告有什么工程价值？**

上下文预算管理的基础——知道每段占多少，才能决定压缩谁（摘要 Memory）、
截断谁（Workspace 快照），见项目 18。
