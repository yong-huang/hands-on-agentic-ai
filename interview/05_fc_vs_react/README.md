# 05 · Function Calling 版 Agent 与 ReAct 对比

> 覆盖面试题：ReAct 和 Function Calling 的关系？可以结合使用吗？
> 把项目 3 的 5 个任务用原生 `tools/tool_calls` 重写，与提示词版 ReAct 同题同工具对跑，
> 输出解析稳定性 / token 成本 / 可观测性 / 模型依赖度四维对比（token 取 API 真实 usage）。

## 1. 同题对跑实测

```bash
MOCK=1 python fc_vs_react.py    # 离线：预置响应
python fc_vs_react.py           # 真实：qwen3.8 (Ollama 原生 tools)
```

实测（2026-09-09，qwen3.8@Ollama，temperature=0）：

| 指标 | ReAct（提示词 JSON） | FC（原生 tool_calls） |
|:--|:--|:--|
| 正确率 | **5/5** | **5/5** |
| LLM 调用次数 | 15 | **13**（task2/4 一轮并行两个工具） |
| token 总量 | **3632** | 6378（schema 每轮重发，+75%） |
| 解析失败 | 0 次 | 0 次 |

怎么看：正确率打平；FC 赢在**一轮多工具并行**（`message.tool_calls` 是数组）与
结构化传输；但 schema 常驻 prompt 使其 token 反而更多——**任务越短，schema 开销
占比越高**。解析稳定性在本组实验打平（qwen3.8 抠 JSON 也全对），小模型/长决策
场景下 FC 的结构化优势才会显现。

## 2. 四维对比（程序输出）

| 维度 | ReAct（提示词模式） | FC（原生能力） |
|:--|:--|:--|
| 解析稳定性 | 从文本抠 JSON，靠正则+重试 | `arguments` 结构化返回 |
| token 成本 | 决策 JSON 全文重发 | 含 schema 常驻开销（实测更高） |
| 可观测性 | 解析文本 trace | `message.tool_calls` 天然结构化 |
| 模型依赖度 | 任何指令模型可跑 | 要求模型支持 tools |

## 3. 可叠加：FC 是传输层，ReAct 是提示词模式

叠加演示（真实输出）：system prompt 要求"调用前先在 content 写一句思考"，
qwen3.8 在**同一条消息**里返回了两者——

```text
content(Thought)   = '我先查询广州的实时天气，获取当前温度。'
tool_calls(Action) = [('get_weather', '{"city":"广州"}')]
```

ReAct 的 Thought→Action→Observation 语义原样成立，只是 Action 从"文本里的 JSON"
换成"API 结构化字段"。生产系统通常两者叠加：ReAct 语义 + FC 传输 + max_steps 兜底。

## 4. 深入要点

- **一句话关系**：FC 解决"Action 怎么传"（传输层），ReAct 解决"Agent 怎么想"
  （提示词循环）——不互斥，可叠加，答案是"结合使用"。
- **选型不是二选一**：看模型是否支持 tools（依赖度）、是否要并行调用、
  可观测性要求、token 预算（schema 常驻是实打实的成本）。
- **实测数据背书**：别背"FC 更省 token"的旧结论——本机实测 FC 反而 +75%
  （schema 重发），好处在结构化与并行；能报出自己跑的数字就是加分项。

## 5. 文件结构

```
interview/05_fc_vs_react/
├── README.md            # 本篇
└── fc_vs_react.py       # FC/ReAct 双实现 + 同题对跑 + 叠加演示（约 290 行）
```
