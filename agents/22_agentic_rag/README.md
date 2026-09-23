# 22 · Agentic RAG：检索成为 Agent 的工具

> 检索不再是无脑执行的固定管线，而变成 Agent 手里的**工具**——模型先看
> 问题，自主决定"要不要查、查什么"，查完基于结果作答；知识库没有的内容
> 明确拒答，绝不编造。真机实测：库内问题自主生成高质量检索词并给出结构化
> 答案，库外问题诚实回答"知识库中没有"。

## What

决策循环：用户问题进入循环，LLM 每轮输出一个 JSON 决策——`search`（带上
改写后的检索词）就走检索工具、结果回喂给模型；`answer` 则输出最终回答
结束循环。检索工具背后是项目 21 的向量索引。max_rounds=3 兜底防死循环：

```json
{"action": "search", "query": "文档切分 chunking 策略"}
{"action": "answer", "answer": "最终回答"}
```

心智模型一句话：**把 search 做成工具，"查不查、查什么"由模型自主决策。**

## Why

固定管线 RAG 有两个浪费：闲聊寒暄也要过一遍检索（浪费），问题需要的检索
词与原句不同时检索质量差（失效）。Agentic RAG 让 LLM 充当"检索决策者"
——它会把"切分文档有什么讲究"改写成更好的检索词，会在信息足够时跳过
检索直接回答，会在知识库覆盖不到时明确拒答。**把能力做成工具、把决策
交还给模型**，这正是 Agent 区别于管线的地方。

## How

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

**检索词改写：Agent 的隐性增值**——用户问"切分文档有什么讲究"，模型检索
用的是"文档切分 chunking 策略 讲究 注意事项"——**检索词比原句更适合
向量空间**。这是 Agentic RAG 相对固定管线最实在的收益：把"提问"和"查询"
两个任务解耦给最擅长的角色。

**拒答：RAG 的诚实底线**——系统提示词明确要求"知识库中没有的信息必须
拒答"。**RAG 的信任来自"知之为知之"**——一次编造毁掉的可信度，十次正确
回答也换不回来。

决策循环的实现：

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

## Deep Dive

**三条终止路径都要如实报告而不是硬答**：模型显式输出 answer、达到
max_rounds、决策解析失败。

踩坑清单：

- 决策 JSON 解析失败要有兜底（提示重试或直接报告失败），不能让循环崩掉；
- 检索结果注入时带上 `[文件#块号]` 出处标注，答案才可溯源；
- 知识库主题要在 system prompt 里声明，模型才能判断"什么该拒答"；
- 单工具循环是最小形态：生产中 search/read_more/compare 可并存，决策空间
  变大后建议升级 Function Calling（项目 11 的协议）；
- 检索质量的上游仍是切分（20）与索引（21）——Agent 救不了垃圾索引。

## Q&A

**Q1: 如何避免 RAG 编造（幻觉）？**

系统提示词强制"知识库外必须拒答" + 检索无果时不给答案 + 让答案引用
chunk 出处（元数据），三道防线缺一不可。

**Q2: 决策用 JSON 还是 Function Calling？**

单工具 JSON 足够且好调试；多工具/参数复杂时用 Function Calling（协议级
保证），本质都是"让模型输出可执行的决策"。
