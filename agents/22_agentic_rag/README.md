# 22 · Agentic RAG：检索成为 Agent 的工具

> 项目 21 的检索是固定管线：每个问题都无脑查一遍。Agentic RAG 把检索变成
> Agent 手里的**工具**——模型先看问题，自主决定"要不要查、查什么"，查完
> 基于结果作答；知识库没有的内容明确拒答，绝不编造。真机实测：库内问题
> 自主生成高质量检索词并给出结构化答案，库外问题诚实回答"知识库中没有"。

## 1. 为什么需要它

固定管线 RAG 有两个浪费：闲聊寒暄也要过一遍检索（浪费），问题需要的检索词
与原句不同时检索质量差（失效）。Agentic RAG 让 LLM 充当"检索决策者"——它
会把"切分文档有什么讲究"改写成更好的检索词（"文档切分 chunking 策略"），
会在信息足够时跳过检索直接回答，会在知识库覆盖不到时明确拒答。**把能力做成
工具、把决策交还给模型**，这正是 Agent 区别于管线的地方。

## 2. 总览：核心机制一图看懂

![Agentic RAG 决策循环](images/agentic_rag.workflow.svg)

**怎么看这张图**：用户问题进入决策循环，LLM 每轮输出一个 JSON 决策——
`search`（带上改写后的检索词）就走检索工具、结果回喂给模型；`answer` 则
输出最终回答结束循环。检索工具背后是项目 21 的向量索引。

心智模型一句话：**把 search 做成工具，"查不查、查什么"由模型自主决策。**

🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/22_agentic_rag/images/agentic_rag.workflow.html)（或本地打开 [`images/agentic_rag.workflow.html`](images/agentic_rag.workflow.html)）。

## 3. 快速开始

```bash
cd agents/22_agentic_rag
python agentic_rag.py --demo   # 离线：预置决策脚本走完整循环
python agentic_rag.py          # 真实：qwen3.8 自主决策 + 项目 21 的向量索引
```

真实模式测两个问题。**实测输出**：

- "切分文档有什么讲究？"→ round 1 自主检索（查询被改写成"文档切分
  chunking 策略 讲究 注意事项"），round 2 基于检索给出 4 点结构化回答
  （切分大小 / 递归策略 / overlap / 元数据）；
- "量子力学的波函数坍缩？"（知识库外）→ 检索无果后明确回答"知识库中没有
  相关信息"，零编造。

## 4. 核心概念

### 4.1 决策协议：JSON Action

```json
{"action": "search", "query": "文档切分 chunking 策略"}
{"action": "answer", "answer": "最终回答"}
```

每轮 LLM 只输出一个决策 JSON（两级回退提取，复用项目 08）。`search` 的结果
以 user 消息回喂后进入下一轮；`answer` 终止循环。max_rounds=3 兜底防死循环。

### 4.2 检索词改写：Agent 的隐性增值

用户问"切分文档有什么讲究"，模型检索用的是"文档切分 chunking 策略 讲究
注意事项"——**检索词比原句更适合向量空间**。这是 Agentic RAG 相对固定管线
最实在的收益：把"提问"和"查询"两个任务解耦给最擅长的角色。

### 4.3 拒答：RAG 的诚实底线

系统提示词明确要求"知识库中没有的信息必须拒答"。实测库外问题（量子力学）
在检索无果后正确拒答。**RAG 的信任来自"知之为知之"**——一次编造毁掉的可信
度，十次正确回答也换不回来。

### 4.4 已知边界

- max_rounds 内没收敛就如实报告失败，不硬答；
- 单工具循环是最小形态：生产中 search/read_more/compare 可并存，
  决策空间变大后建议升级 Function Calling（项目 11 的协议）；
- 检索质量的上游仍是切分（20）与索引（21）——Agent 救不了垃圾索引。

## 5. 代码关键部分

```python
def agentic_answer(collection, question, llm, max_rounds=3):
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question}]
    for round_no in range(1, max_rounds + 1):
        decision = extract_json(llm(messages))
        if decision["action"] == "answer":
            return decision["answer"]
        print(f"  [round {round_no}] search: {decision['query']}")
        messages.append({"role": "assistant",
                         "content": json.dumps(decision, ensure_ascii=False)})
        messages.append({"role": "user",
                         "content": f"[search 结果]\n{search_tool(decision['query'])}"})
    return "（达到最大轮数仍未给出答案）"
```

坑清单：

- 决策 JSON 解析失败要有兜底（提示重试或直接报告失败），不能让循环崩掉；
- 检索结果注入时带上 `[文件#块号]` 出处标注，答案才可溯源；
- 知识库主题要在 system prompt 里声明，模型才能判断"什么该拒答"。

## 6. 文件结构

```
22_agentic_rag/
├── README.md                            # 本篇教程
├── agentic_rag.py                       # 主脚本（约 160 行）：决策循环 + 检索工具
└── images/
    ├── agentic_rag.workflow.json        # 图源：workflow 类型（决策循环）
    ├── agentic_rag.workflow.html        # 交互版架构图
    └── agentic_rag.workflow.svg         # 双主题矢量图
```

## 7. 面试要点

- **Q: Agentic RAG 与普通 RAG 管线的区别？**
  A: 检索从固定步骤变成模型可自主调用的工具——是否检索、检索词怎么写、
  检索几轮都由模型按问题动态决定。
- **Q: 为什么检索词改写很重要？谁来做？**
  A: 用户问句与知识库表述常有语义落差；LLM 决策时顺便把问句改写成更适合
  检索的查询，是 Agentic RAG 最直接的收益。
- **Q: 如何避免 RAG 编造（幻觉）？**
  A: 系统提示词强制"知识库外必须拒答" + 检索无果时不给答案 + 让答案引用
  chunk 出处（元数据），三道防线缺一不可。
- **Q: 循环的终止条件有哪些？**
  A: 模型显式输出 answer、达到 max_rounds、决策解析失败——三条路径都要
  如实报告而不是硬答。
- **Q: 决策用 JSON 还是 Function Calling？**
  A: 单工具 JSON 足够且好调试；多工具/参数复杂时用 Function Calling
  （协议级保证），本质都是"让模型输出可执行的决策"。

## 8. 总结

把检索做成工具、把决策交还模型：Agentic RAG 会改写检索词、会按需多轮检索、
会在知识库外诚实拒答。RAG 管线的"生成"与"检索"从此由一个会思考的循环连接。
下一篇给检索本身做体检——重排序与优化，让"查回来的东西"更准。
