# 17 · 对话记忆与长期记忆：滑动窗口 + 向量检索 + MEMORY.md

> 项目 16 的 Memory 是写死的常量——Agent"认识你"全靠剧本。本篇给它装上真正的
> 两层记忆：**短期记忆**用滑动窗口在上下文预算内保留最近对话；**长期记忆**把值得
> 记的事实 embedding 入库，新对话按相似度检索 top-k 注入。真实模式跑两段会话：
> 第二段用全新的 ShortTermMemory，答对"我叫什么"全靠跨会话记忆召回。

## 1. 为什么需要它

上下文窗口是稀缺资源：对话越长、成本越高、注意力越稀释。理想的记忆系统应该
"近事详记、远事摘要、要事 permanent"——这正是人类记忆的分层结构。本篇用约
300 行纯 Python 实现最小完整版：不加 chromadb、不加 LangChain Memory，向量库
自己写（JSON 落盘 + 余弦相似度），embedding 用本地 nomic-embed-text（768 维，
零 API Key）。理解了这套最小实现，任何记忆框架对你都不再是魔法。

## 2. 总览：核心机制一图看懂

![两层记忆的工作流](images/two_layer_memory.workflow.svg)

**怎么看这张图**：对话层是主干——用户输入经滑动窗口放行、与检索到的相关记忆
一起进入 `build_context`，组装后交给 qwen3.8；记忆层负责检索——用户输入先被
nomic-embed-text 变成 768 维向量，在 memory_store.json 里做余弦相似度检索；
沉淀层在对话结束后工作——LLM 判定值得记的事实，向量入库并写入 MEMORY.md。

心智模型一句话：**短期逐字保真但会淘汰，长期压缩成事实但跨会话。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/17_memory/images/two_layer_memory.workflow.html)（或本地打开 [`images/two_layer_memory.workflow.html`](images/two_layer_memory.workflow.html)）。

## 3. 快速开始

```bash
cd agents/17_memory
python memory.py --demo   # 离线：伪向量演示两层机制（无需 Ollama）
python memory.py          # 真实：两段会话验证跨会话记忆召回
```

`--demo` 演示写入/检索/窗口淘汰三件事（用确定性伪向量，仅验证管线）。

真实模式跑两段会话：会话 1 告诉 Agent"我叫张三、喜欢吃火锅不能吃辣、正在学
记忆系统"；会话 2 用**全新的 ShortTermMemory**（模拟重启）问"我叫什么？学到
哪了？"。**预期输出**：会话 2 检索到记忆（相似度 0.67/0.57）并正确回答——
没有任何短期历史，答对只能靠长期记忆。每轮结束 LLM 提取值得记的事实入库。

## 4. 核心概念

### 4.1 两层记忆的分工

| | 短期（滑动窗口） | 长期（向量库 + MEMORY.md） |
| :--- | :--- | :--- |
| 形态 | 逐字 messages | 压缩成一句话事实 |
| 生命周期 | 预算外自动淘汰 | 永久沉淀 |
| 入库条件 | 不需要判断 | LLM 判定"值得记" |
| 生效时机 | 本回合 | 下次对话检索注入 |
| 本篇预算 | 300 token | top-2、相似度阈值 0.5 |

### 4.2 滑动窗口：预算内放行最近对话

`build_window()` 从最新消息向前收集，预算（300 token）用尽即停，system 消息
永远保留。与全量重发（项目 05）相比：token 成本有上界，代价是早期对话被淘汰
——被淘汰的内容若有长期价值，就该在对话时沉淀进长期记忆（两层配合的逻辑）。

### 4.3 向量检索：语义而非关键词

"我喜欢吃什么？"与"用户喜欢吃火锅"没有共同关键词，但 embedding 空间里余弦
相似度 0.67——**语义检索让记忆按意思被找到，而不是按字面**。检索带相似度
阈值（0.5）过滤不相关记忆：宁可少注入，不注入噪音。

### 4.4 沉淀：LLM 判定"值得记"

每轮对话结束后，用 LLM 从对话中提取值得长期记住的事实（一句话），embedding
入库并追加 MEMORY.md。MEMORY.md 是人可读的沉淀层——你可以直接打开看 Agent
记了什么、手动删掉不该记的。**易错点（本篇真实发生）**：同一事实会被反复提取
入库（"喜欢吃火锅"沉淀了两次），去重与融合是项目 19 的主题。

## 5. 代码关键部分

```python
def build_messages(user_msg, hits):
    """短期窗口 + 长期检索结果 -> 完整请求"""
    stm = ShortTermMemory(SYSTEM_PROMPT)
    stm.add("user", user_msg)
    if hits:
        lines = "\n".join(f"- {t} (相似度 {s:.2f})" for s, t in hits)
        stm.system_prompt += f"\n\n【相关记忆】\n{lines}"
    window, dropped = stm.build_window()
    return window, dropped

def recall(user_msg, store):
    return store.search(embed(user_msg), top_k=TOP_K, threshold=SIM_THRESHOLD)
```

坑清单：

- `memory_store.json` 与 `MEMORY.md` 是运行时产物，重复跑会累积记忆（想从零
  开始就删掉它们）；
- 相似度阈值过高会"失忆"，过低会注入噪音——按库的规模调；
- embedding 模型换了，旧向量全部作废（维度与空间都不同），必须重建索引。

## 6. 文件结构

```
17_memory/
├── README.md                            # 本篇教程
├── memory.py                            # 主脚本（约 260 行）：窗口 + 向量库 + 沉淀
├── MEMORY.md                            # 运行时产物：人可读的长期记忆（gitignore）
├── memory_store.json                    # 运行时产物：向量库（gitignore）
└── images/
    ├── two_layer_memory.workflow.json   # 图源：workflow 类型（对话/记忆/沉淀三层）
    ├── two_layer_memory.workflow.html   # 交互版架构图
    └── two_layer_memory.workflow.svg    # 双主题矢量图
```

## 7. 面试要点

- **Q: Agent 的记忆为什么要分短期和长期两层？**
  A: 短期保真（逐字）但受上下文预算限制、会淘汰；长期压缩成事实、可跨会话
  检索。两层互补：淘汰前沉淀，需要时召回。
- **Q: 滑动窗口的预算怎么定？淘汰时要注意什么？**
  A: 按模型上下文与成本预算定；system 消息永不淘汰，尽量成对淘汰，
  被淘汰内容若值得保留应先沉淀长期记忆。
- **Q: 向量检索相比关键词匹配的优势？**
  A: 语义级匹配——"我喜欢吃什么"能召回"用户喜欢吃火锅"，无共同关键词；
  代价是需要 embedding 计算与向量存储。
- **Q: 什么事实值得写入长期记忆？谁来判定？**
  A: 偏好、身份、约定等稳定事实；由 LLM 判定（本篇），更精细的重要性分级、
  去重融合与遗忘策略见项目 19。
- **Q: 相似度阈值的作用是什么？**
  A: 过滤不相关召回——宁可少注入不注入噪音；阈值随库规模与业务调优。

## 8. 总结

短期滑动窗口管"现在"，长期向量库管"永远"，LLM 充当两者之间的守门人。本篇
的库里有真记忆、也有重复沉淀的噪音——怎么让 Agent 自主决定记什么、怎么更新
和遗忘，正是下一篇「记忆更新策略」的主题。
