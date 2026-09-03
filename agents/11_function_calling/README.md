# 11 · Function Calling：协议级的工具调用

> 项目 06 里模型用 `Action: Calculator(2126+1768)` 这样的**文本**表达工具
> 调用，解析器写了几百行还到处打补丁。本篇换用 API 原生的 Function Calling：
> 把工具的 JSON Schema 放进请求的 `tools` 参数，模型直接返回结构化的
> `message.tool_calls`——没有正则、没有格式猜谜，参数类型由 schema 保证。

## 1. 为什么需要它

文本 ReAct 的所有痛点都源于"用自然语言传结构化信息"。Function Calling 把
这件事挪进协议：请求时声明工具（JSON Schema），响应时模型返回带类型的
`tool_calls` 数组，你本地执行后以 `role: "tool"` 消息回传。这是 OpenAI/
Anthropic/Ollama 通用的现代标准，也是 MCP（项目 14）、LangChain 工具（项目
09）共同的地基。**理解了这 4 条消息的流转，所有 Agent 框架的工具循环对你就
不再神秘。**

## 2. 总览：核心机制一图看懂

![Function Calling 协议时序](images/tool_call_sequence.sequence.svg)

**怎么看这张图**：一条完整的消息流——用户提问 → Agent 把 `messages + tools
schema` 发给模型 → 模型返回 `message.tool_calls`（结构化 JSON）→ Agent 本地
`fn(**arguments)` 执行 → 结果以 `role:"tool"` 回传 → 模型这次不再要求工具，
返回纯文本 → 转达用户。

心智模型一句话：**Function Calling = 把"工具菜单"给模型，模型"点菜"，
你"炒菜"，再把菜端回去。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/11_function_calling/images/tool_call_sequence.sequence.html)（或本地打开 [`images/tool_call_sequence.sequence.html`](images/tool_call_sequence.sequence.html)）。

## 3. 快速开始

```bash
cd agents/11_function_calling
python function_calling.py --demo                # 离线：完整协议流程演示
python function_calling.py "北京天气怎么样？"      # 真实调用本地 Ollama
```

`--demo` 分四部分：①打印发给 API 的两个工具 JSON Schema；②单工具调用
（北京天气 → `Sunny, 28C`）；③并行 tool_calls（上海/东京各查天气+人口，
一次响应 4 个调用）；④打印完整 message flow（user → assistant(tool_calls)
→ tool → assistant）。

真实模式预期输出：`Round 1` 模型发起 `get_weather(beijing)`，回传结果后
`Round 2` 给出最终中文回答。

## 4. 核心概念

### 4.1 请求侧：tools 参数

```json
{"type": "function", "function": {
  "name": "get_weather",
  "description": "查询指定城市的天气",
  "parameters": {"type": "object",
                 "properties": {"city": {"type": "string", "description": "城市名"}},
                 "required": ["city"]}}}
```

`description` 和参数描述直接决定模型选工具、填参数的质量——**schema 是给
模型看的文档**。

### 4.2 响应侧：tool_calls 结构

```json
{"role": "assistant", "tool_calls": [
  {"id": "call_1", "type": "function",
   "function": {"name": "get_weather", "arguments": "{\"city\": \"beijing\"}"}}]}
```

注意 `arguments` 是 **JSON 字符串**，要 `json.loads` 后再 `fn(**args)`。
一次响应可含多个 tool_calls（并行调用），这是文本 ReAct 做不到的。

### 4.3 回传：role="tool"

工具结果必须以 `{"role": "tool", "tool_name": ..., "content": ...}` 消息
追加后**再请求一轮**，模型才能基于结果作答。终止判定也变得极简：
**响应里没有 tool_calls 就是最终答案**。

### 4.4 对比文本 ReAct（项目 06）

| 维度 | 文本 ReAct | Function Calling |
| :--- | :--- | :--- |
| 解析 | 正则 + 变体兼容 + 重试 | 零解析，直接读 JSON |
| 参数类型 | 字符串，自己转 | Schema 声明，类型安全 |
| 并行调用 | 每轮一个 | 单响应多 tool_calls |
| 模型要求 | 会按格式写文本即可 | 模型需支持 tools 参数（qwen3.8 支持） |

**易错点**：模型可能幻觉出不存在的工具名或越界参数——执行器要像项目 12
那样把错误作为字符串回传，让模型自我修正，而不是直接崩。

## 5. 代码关键部分

```python
def execute_tool_call(tc):
    name = tc["function"]["name"]
    args = json.loads(tc["function"]["arguments"])     # arguments 是字符串！
    fn = TOOLS[name]["fn"]
    try:
        return fn(**args)
    except Exception as e:
        return f"Error: {e}"                           # 错误回传给模型而非崩溃

def run_agent(question, max_rounds=5):
    messages = [{"role": "user", "content": question}]
    for _ in range(max_rounds):
        resp = call_ollama(messages, tools_schema=get_tools_schema())
        msg = resp["message"]
        if not msg.get("tool_calls"):                  # 没有点菜 = 最终答案
            return msg["content"]
        messages.append(msg)                           # assistant(tool_calls) 入史
        for tc in msg["tool_calls"]:
            result = execute_tool_call(tc)
            messages.append({"role": "tool", "tool_name": tc["function"]["name"],
                             "content": str(result)})
```

坑清单：

- `role:"tool"` 消息的 `tool_name`/`tool_call_id` 要与调用对应，多工具并行时
  对不上号模型会困惑；
- 未知工具、参数校验失败都应返回错误字符串（模型会重试），不要抛异常中断循环；
- 本地小模型的 schema 遵循度弱于云端旗舰，复杂参数要加 enum 约束。

## 6. 文件结构

```
11_function_calling/
├── README.md                              # 本篇教程
├── function_calling.py                    # 主脚本（约 350 行）：schema 注册 + 执行器 + 循环
└── images/
    ├── tool_call_sequence.sequence.json   # 图源：sequence 类型（4 参与方消息流）
    ├── tool_call_sequence.sequence.html   # 交互版架构图
    └── tool_call_sequence.sequence.svg    # 双主题矢量图
```

## 7. 面试要点

- **Q: Function Calling 的完整消息流是什么？**
  A: user 提问 → assistant 携带 tool_calls → tool 消息回传结果 → assistant
  给出最终文本；循环至响应不含 tool_calls。
- **Q: 模型真的"执行"了函数吗？**
  A: 没有。模型只输出"想调用的函数名与参数 JSON"，执行永远发生在你的
  运行时，结果再喂回去。
- **Q: 和文本 ReAct 相比最大收益是什么？**
  A: 结构化保证：免解析、参数类型安全、可并行；代价是要求模型支持该协议。
- **Q: arguments 为什么是字符串？**
  A: 协议设计使 JSON 以字符串传输以适配 token 化生成；客户端必须
  `json.loads` 并做异常处理。
- **Q: 模型返回不存在的工具怎么办？**
  A: 返回 "Unknown tool: ..." 的 tool 消息，模型通常下一轮会修正；执行器
  永远不因模型输出而崩溃。

## 8. 总结

Function Calling 把工具调用从"文本约定"升级为"协议保证"，Agent 循环随之
简化到 20 行。但工具注册还是手写字典——下一篇用 Registry 模式解决"新增一个
工具要改三处"的重复劳动。
