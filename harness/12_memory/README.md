# 12 · 跨会话记忆：A 学到 · B 遵循 · C 遗忘

> 压缩（10）保"本任务不忘记"，session（11）保"崩溃不失忆"，本篇管最后
> 一层：**跨任务的世界观**。`mh/memory.py`：MEMORY.md 人类可读存储、
> 收尾时模型自动沉淀（consolidate）、新会话 system 注入（recall）、
> `forget()` 遗忘是一等操作。真机四会话闭环：A 声明偏好 → B 无提示遵循
> → C 遗忘清空 → D 验证无习惯残留。

## 1. 为什么需要它

每次会话都重新交代"我们用 pytest、路径这样约定、我是谁"——这不是 agent，
是复读机。12 记忆污染（旧事实误导新任务）的解药不是"不记"，而是**记的
东西看得见、可追溯、可删除**：每条带时间戳、文件是 markdown、遗忘和记住
同样是 API。Databricks 的组件清单里"文件系统与持久存储"和"记忆与上下文
管理"并列，本篇把它们接通。

## 2. 总览：核心机制一图看懂

![跨会话记忆](images/memory.workflow.svg)

**怎么看这张图**：会话 A 收尾时 consolidate 让模型从对话提取 ≤3 条值得
长期记住的事实（用户声明的偏好命中），带时间戳写入 MEMORY.md；会话 B
启动时 recall() 把记忆块拼进 system——模型在**从未见过任务描述**的情况
下自觉遵守。C 会话 `forget("mh-demo")` 删除条目，recall 清空。

心智模型一句话：**记忆的可靠性不靠模型记性好，靠"看得见、可追溯、可删除"。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/harness/12_memory/images/memory.html)
> （或本地打开 [`images/memory.html`](images/memory.html)）。

## 3. 快速开始

```bash
cd harness/12_memory
MOCK=1 python3 demo.py    # 离线管道自检
python3 demo.py           # 真机四会话（A/B/C 验收 + D 观察项）
```

真机实测（2026-09-20，qwen3.8）：

```text
[A 学偏好] 声明"所有 Python 文件头部必须加 # PROJECT: mh-demo"
  沉淀: 1 条 → MEMORY.md
[B 遵循] 全新会话仅下发"创建 calc.py" → 头部带标记 ✅（无提示）
[C 遗忘] forget("mh-demo") → 移除 1 条, recall 清空 ✅
[D 遗忘后] 模型自发不写标记 ✅（无习惯残留——对照很有说服力）
```

## 4. 核心概念

### 4.1 三层记忆的分工（至此集齐）

| 层 | 模块 | 粒度 | 载体 |
|:--|:--|:--|:--|
| 工作记忆 | 10 compaction | 本任务内 | 上下文窗口 |
| 任务记忆 | 11 session | 本任务进度 | checkpoint.json |
| 长期记忆 | 本篇 | 跨任务世界观 | MEMORY.md |

### 4.2 沉淀是模型的判断，删除是用户的权力

`consolidate()` 让模型自己判断"什么值得记"——它可能记错、记多、记偏；
所以每条带时间戳、每条可被 `forget(关键词)` 单独删除、整个文件人类可读
可手改。**记忆系统的健壮性不来自记得准，来自错了能改。**（Claude Code
的 auto-memory 同哲学：markdown + 人工可编辑。）

### 4.3 偏好选型：要"异常可核查"

演示偏好故意选了异常事实（文件头注释标记）而不是"用 pytest"——后者
模型可能凭训练习惯直接押中，B 会话通过也不能证明记忆生效。**测记忆要
用模型不会自发做的事**，与 03"顺任务测不出 harness"同一条方法论。

## 5. 代码关键点

```python
Memory(path)                     # MEMORY.md 读写, 条目即行
consolidate(chat_fn, transcript, memory)  # 收尾提取 ≤3 条
system_with_memory(base, memory) # 新会话 system 拼接(空记忆原样)
memory.forget(keyword)           # 删含关键词条目, 返回条数
```

注入方式走的是 11 加的 `messages=` 参数——把带记忆的 system 拼好后
传入 loop，**主循环依旧零改动**。

## 6. 文件结构

```
harness/
├── mh/
│   └── memory.py        # ⛓️ 本篇: Memory / consolidate / system_with_memory
└── 12_memory/
    ├── README.md
    ├── demo.py          # 四会话验收
    └── images/          # 工作流图三件套
```

## 7. 深入要点

- **为什么不向量库？** 几十条偏好用不上检索；MEMORY.md 全量注入成本可忽略。
  向量检索是"记忆条目上万"之后的优化，不是前提——先让记忆可见可删，
  再谈规模（alphaXiv 的教训：支架复杂度不等于能力）。
- **consolidate 会不会把闲聊也存进去？** 会。防线有三：prompt 限定
  "偏好/事实"、条数上限、时间戳可删。12 记忆污染在真机上的表现就是
  过期事实误导新任务——遗忘入口是解药不是补丁。
- **注入放 system 还是首条 user？** 本篇放 system 尾部（07 的教训是
  "中途 system 不可靠"，会话开头的 system 可靠）；若记忆很长，应转为
  按需检索注入（RAG 化），见 15。
- **D 会话为什么单独做观察项？** 遗忘后模型自发行为不可控（可能凭习惯
  写标记），硬断言会把模型的巧合当系统的功劳——观察并如实报告即可。

## 8. 总结

第四阶段收官，三层记忆集齐：跑得久（压缩）、摔不死（恢复）、记得住
（本篇）。mh/ 包 11 个模块。下一篇进入第五阶段扩展机制：
[13_subagent](../13_subagent/README.md) 子代理调度——上下文隔离的任务
分派，主代理只收摘要（验证手段是 trace diff）。
