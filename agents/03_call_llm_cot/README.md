# 03 · Prompt 结构设计：CoT + Few-shot 引导结构化输出

> 项目 01/02 里模型自由发挥，你想拿到能被程序消费的 JSON，它却回你一大段散文。
> 本篇用一套精心设计的 System Prompt——角色设定 + CoT 思维链 + Few-shot 示例
> + 输出标签约定——让模型"先想后说"，并稳定吐出可解析的 JSON。同时定义三种
> 不同角色，实测同一问题在不同人格下的回答差异。

## 1. 为什么需要它

Agent 的每个决策都来自模型的输出，而程序的每个动作都要求输出**可解析**。
"让模型输出结构化数据"是 Agent 工程的第一道坎：模型不是不配合，而是你没
告诉它"想的过程"和"结果的格式"。本篇的 Prompt 模板是后续 ReAct（项目 06）
的直系祖先——ReAct 的 `Thought/Action/Answer` 格式就是同一套思路。

## 2. 总览：核心机制一图看懂

![CoT + Few-shot 工作流](images/cot_prompt.workflow.svg)

**怎么看这张图**：上面两条泳道是 Prompt 的组装流水线（角色 → Few-shot 注入），
第三条是模型推理，最下面是解析与兜底——两级回退正则先抓 `<output>` 标签、
失败再全文找第一个 `{...}`。

心智模型一句话：**Prompt 是编程，示例是类型声明，双标签是返回值的信封。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/03_call_llm_cot/images/cot_prompt.workflow.html)（或本地打开 [`images/cot_prompt.workflow.html`](images/cot_prompt.workflow.html)）。

## 3. 快速开始

```bash
cd agents/03_call_llm_cot
python call_llm_cot.py
# 🧑 请输入需要分析的文本: （回车用默认："这个产品很好用，质量也很棒！"）
```

脚本依次做四件事：

1. 读入待分析文本；
2. 以 `temperature=0.3`（结构化任务要低温）调用 API；
3. 打印模型完整响应——你能亲眼看到 `<thinking>` 里的推理过程；
4. `extract_json()` 提取并解析，美观打印五字段结果。

预期输出：`📊 结构化输出结果`，含 `category / sentiment / confidence /
keywords / summary`。

## 4. 核心概念

### 4.1 System Prompt 的四层结构

| 层 | 作用 | 本项目的实现 |
| :--- | :--- | :--- |
| 角色（Identity） | 限定语气与专业域 | "你是一个专业的数据分析助手" |
| 任务 + 格式约定 | 说明做什么、输出长什么样 | 情感分析 + `<thinking>`/`<output>` 双标签 |
| CoT 指令 | 要求先推理再下结论 | "先在 `<thinking>` 中逐步分析" |
| Few-shot 示例 | 用 3 个样例钉死格式 | 正面/负面/中性各一条 |

### 4.2 CoT（Chain-of-Thought）：先想后说

强迫模型把推理写出来，会显著提升复杂任务的准确率——推理过程占用的 token
给了模型"草稿纸"。本项目用 `<thinking>` 标签圈住推理、`<output>` 圈住结论，
**推理过程可读、结论可解析**，两者兼得。

CoT 家族速览（文件头注释里有 10 种形态的完整表格）：Zero-Shot（只说"一步步想"）、
Few-Shot（带推理示例）、Self-Consistency（多次采样投票）、ReAct（推理+行动
交替，项目 06 的主题）。

### 4.3 Few-shot：示例即契约

模型对"照着例子输出"的服从度远高于"按 JSON Schema 输出"。三个示例覆盖
正/负/中性三类，等于告诉模型：**输出就长这样，字段一个都不能少**。

### 4.4 解析的两级回退

```python
pattern_tag  = r"<output>\s*(\{.*?\})\s*</output>"   # 第一级: 标签内提取
pattern_json = r"\{[^{}]*\}"                          # 第二级: 全文第一个 {...}
```

第一级精准，第二级兜底——模型偶尔忘写标签时仍能救回。**易错点**：正则必须
带 `re.S`（DOTALL），否则跨行 JSON 匹配失败；第二级只匹配无嵌套的扁平 JSON，
字段设计时要避免嵌套对象。

工程上更稳的方案是 Function Calling（项目 11）——服务端强制 JSON Schema，
连解析都省了。本篇教的是"没有 Function Calling 时的完整自救链"。

### 4.5 角色定义实验

把 System Prompt 换成"工程师/产品经理/安全审计"三种角色问同一个问题，
回答的侧重点立刻分化：工程师谈实现、产品谈用户价值、安全审计谈风险。
**角色不是玄学，是对采样分布的条件约束。**

## 5. 代码关键部分

```python
SYSTEM_PROMPT = """你是一个专业的数据分析助手...
## 输出格式要求
1. 先在 <thinking> 标签中逐步分析（CoT）
2. 再在 <output> 标签中给出纯 JSON，字段:
   category, sentiment, confidence, keywords, summary
## 示例
输入: 这家店服务太差了...     ← Few-shot 第 1/3 条
<output>{"sentiment": "负面", ...}</output>
"""
```

坑清单：

- `temperature` 高了 JSON 字段会"发挥"（多字段、换行带注释），结构化任务用 0-0.3；
- `confidence` 是模型自估的，**不是真实概率**，只可做相对比较；
- 中文场景下 `keywords` 可能带标点，下游要做清洗。

## 6. 文件结构

```
03_call_llm_cot/
├── README.md                     # 本篇教程
├── call_llm_cot.py               # 主脚本（约 240 行）：Prompt 模板 + 调用 + 两级解析
└── images/
    ├── cot_prompt.workflow.json  # 图源：workflow 类型（含异常兜底泳道）
    ├── cot_prompt.workflow.html  # 交互版架构图
    └── cot_prompt.workflow.svg   # 双主题矢量图
```

## 7. 面试要点

- **Q: CoT 为什么能提升准确率？**
  A: 把中间推理显式化，相当于给模型草稿纸——后续 token 可以"参考"前面的
  推理，降低一步到位的出错率；代价是输出变长、延迟变高。
- **Q: Few-shot 示例数量越多越好吗？**
  A: 不是。示例占上下文窗口且边际收益递减，2-5 个覆盖典型 case 通常最优；
  示例的**格式一致性**远比数量重要。
- **Q: 模型输出的 JSON 解析失败有哪些自救手段？**
  A: ①正则提取标签/花括号；②重试并在消息里附上解析错误；③温度调 0；
  ④终极方案 Function Calling / JSON mode 由服务端保证格式。
- **Q: `<thinking>` 内容应该留给下游吗？**
  A: 不应该。它是推理草稿，可能包含自我矛盾的内容；只把 `<output>` 的
  JSON 交给程序。
- **Q: temperature=0.3 而不是 0，为什么？**
  A: 留一点随机性避免措辞僵化，同时足够低保证格式稳定；纯分类任务可以到 0。

## 8. 总结

角色 + CoT + Few-shot + 双标签 = 让模型"想得清楚、说得规矩"。这一套 Prompt
工程模板在下一篇会被拆开重装——下一篇做对照实验：只改 `temperature` 这一个
参数，看输出会发生什么。
