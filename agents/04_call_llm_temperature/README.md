# 04 · Temperature 参数实验：亲手量化"随机性"

> Prompt 一字不改，模型为什么每次回答不一样？答案藏在 `temperature` 这个采样
> 参数里。本篇做一次严格的对照实验：固定 Prompt 与 system 消息，只改 temperature
> （0.0 / 0.5 / 1.0），横向对比输出的长度、词汇多样性和关键词命中率，并用
> softmax 把它背后的数学一次讲透。

## 1. 为什么需要它

Agent 开发里 temperature 不是玄学而是工程参数：工具调用解析错一个字就崩，
所以工具场景要低温；创意生成要发散，所以要高温。**你不亲手对比一次，就永远
在"听说 0.7 比较好"的水平。** 本篇还埋了一个真实世界的坑：qwen3.8 这类
推理模型可能把答案写进 `thinking` 字段——实验脚本里就带了这个兜底。

## 2. 总览：核心机制一图看懂

![Temperature 对照实验](images/temperature_fanout.dataflow.svg)

**怎么看这张图**：同一个 Prompt（左侧）扇出到三条采样路径（中列三档温度），
各自产出不同"性格"的输出（右列），最终汇入对比分析（长度/多样性/关键词命中）。

心智模型一句话：**temperature 是 softmax 的除数——T→0 退化成 argmax（永远选
最高分词），T 越大长尾词越容易被抽中。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/04_call_llm_temperature/images/temperature_fanout.dataflow.html)（或本地打开 [`images/temperature_fanout.dataflow.html`](images/temperature_fanout.dataflow.html)）。

## 3. 快速开始

```bash
cd agents/04_call_llm_temperature
python call_llm_temperature.py
```

脚本依次做三件事：

1. 打印实验设计（固定 Prompt + 三档温度）；
2. 依次以 0.0 / 0.5 / 1.0 调用（每轮间隔 0.5s），打印各档输出；
3. `analyze_results()` 对比长度、词数、关键词命中、词汇多样性并给出结论。

预期输出：`0.0` 档措辞工整命中关键词；`1.0` 档可能更"放飞"甚至偏离约束
（这正是教学点——多发散的模型越可能牺牲指令遵循）。

## 4. 核心概念

### 4.1 数学本质：一个除数

采样概率 `p(x) = softmax(logits / T)`：

| T | 效果 | 适用场景 |
| :--- | :--- | :--- |
| T→0 | 分布退化为 argmax，输出可复现 | 工具调用、分类、抽取 |
| 0.5 | 分布略收窄，稳定中有变化 | 日常对话、摘要 |
| 1.0 | 原始分布，长尾词有机会 | 头脑风暴、创意写作 |
| T>1 | 人为压平分布，明显发散 | 少用；容易牺牲指令遵循 |

### 4.2 实验设计：控制变量

固定不变的：Prompt（含"必须包含'数据'和'模式'"的硬约束）、system 消息、
`num_predict=150`。唯一的自变量：`options.temperature`。观测量：输出长度、
词汇多样性（去重词数）、关键词命中率。**任何结论都必须在这样的控制变量下
得出**——这也是评估 Agent 的基本功（项目 30 会复用这套思路建评估集）。

### 4.3 实验观察

多次运行你会发现：T=0.0 的多次输出几乎一致；T=1.0 的输出每次都不同且
长度方差更大。**T=0 并不 100% 确定**（GPU 浮点并行导致少量非确定性），
但工程上足够当作"可复现"使用。

### 4.4 真实的坑：thinking 字段

qwen3.8 是推理模型，响应里可能同时有 `message.thinking` 和 `message.content`，
且答案有时只出现在 thinking 里。`extract_content()` 做了三级兜底：
`content` → `thinking` 的最后有效行 → `response` 字段。**失败时打印响应的
字段名列表**，是调试陌生模型响应结构的通用技巧。

## 5. 代码关键部分

```python
def extract_content(response_data):
    message = response_data.get("message", {})
    content = message.get("content", "").strip()
    if not content and message.get("thinking"):      # 推理模型兜底
        for line in reversed(message["thinking"].splitlines()):
            line = line.strip()
            if line and not line.startswith("Thinking"):
                return line                           # thinking 里最后一条有效行
    return content or response_data.get("response")   # generate 接口风格兜底
```

坑清单：

- 温度实验每次调用之间加 `sleep(0.5)`，避免本地推理排队互相污染计时；
- 对照实验**不要**同时改 max_tokens，否则长度对比失去意义；
- 别用"看起来更智能"评价高温输出——用可量化指标（命中/多样性）说话。

## 6. 文件结构

```
04_call_llm_temperature/
├── README.md                          # 本篇教程
├── call_llm_temperature.py            # 主脚本（约 210 行）：实验 + 解析兜底 + 对比分析
└── images/
    ├── temperature_fanout.dataflow.json  # 图源：dataflow 类型（扇出对照）
    ├── temperature_fanout.dataflow.html  # 交互版架构图
    └── temperature_fanout.dataflow.svg   # 双主题矢量图
```

## 7. 面试要点

- **Q: temperature 的数学作用是什么？**
  A: 对 logits 除以 T 再 softmax。T<1 放大差异使分布更尖，T>1 压平分布使
  采样更均匀，T→0 等价 argmax。
- **Q: Agent 的工具调用为什么建议低温？**
  A: 工具名和参数 JSON 必须精确匹配注册表，发散采样会增加幻觉工具名、
  格式错误的概率；低温提升可解析率。
- **Q: temperature=0 能保证完全确定性吗？**
  A: 不能完全保证。浮点并行归约顺序不定会引入微量非确定性；要严格复现需
  固定 seed + 确定性推理配置。
- **Q: top_p 和 temperature 什么关系？**
  A: 都是控制采样分布的手段：top_p 是"截断"（只从累计概率前 p 的词里采），
  temperature 是"调形"。实践里二选一调，同时大幅调整容易互相抵消。
- **Q: 怎么科学地对比两个参数档位的效果？**
  A: 控制变量 + 量化指标（命中率/多样性/长度）+ 多次重复，参考本篇实验设计。

## 8. 总结

temperature 是采样分布的"形状旋钮"，工具链路用低温、创作链路用高温，且
一切结论要靠控制变量实验说话。至此"发什么给模型"（Prompt）和"怎么采样"
（参数）都清楚了；下一篇回到 messages 数组本身——让它**越聊越长**，实现
真正的多轮对话。
