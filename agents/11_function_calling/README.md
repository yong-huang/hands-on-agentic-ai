# 11 · Function Calling：协议级的工具调用

> 换用 API 原生的 Function Calling：把工具的 JSON Schema 放进请求的
> `tools` 参数，模型直接返回结构化的 `message.tool_calls`——没有正则、
> 没有格式猜谜，参数类型由 schema 保证。

## What

一条完整的消息流：用户提问 → Agent 把 `messages + tools schema` 发给模型
→ 模型返回 `message.tool_calls`（结构化 JSON）→ Agent 本地 `fn(**arguments)`
执行 → 结果以 `role:"tool"` 回传 → 模型返回纯文本 → 转达用户。

请求侧的 tools 参数——`description` 和参数描述直接决定模型选工具、填参数
的质量（**schema 是给模型看的文档**）：

```json
{"type": "function", "function": {
  "name": "get_weather",
  "description": "查询指定城市的天气",
  "parameters": {"type": "object",
                 "properties": {"city": {"type": "string", "description": "城市名"}},
                 "required": ["city"]}}}
```

响应侧的 tool_calls——注意 `arguments` 是 **JSON 字符串**，要 `json.loads`
后再 `fn(**args)`；一次响应可含多个 tool_calls（并行调用）：

```json
{"role": "assistant", "tool_calls": [
  {"id": "call_1", "type": "function",
   "function": {"name": "get_weather", "arguments": "{\"city\": \"beijing\"}"}}]}
```

与文本 ReAct 的对比：

| 维度 | 文本 ReAct | Function Calling |
| :--- | :--- | :--- |
| 解析 | 正则 + 变体兼容 + 重试 | 零解析，直接读 JSON |
| 参数类型 | 字符串，自己转 | Schema 声明，类型安全 |
| 并行调用 | 每轮一个 | 单响应多 tool_calls |
| 模型要求 | 会按格式写文本即可 | 模型需支持 tools 参数（qwen3.8 支持） |

心智模型一句话：**Function Calling = 把"工具菜单"给模型，模型"点菜"，
你"炒菜"，再把菜端回去。**

## Why

文本 ReAct 的所有痛点都源于"用自然语言传结构化信息"。Function Calling
把这件事挪进协议。这是 OpenAI/Anthropic/Ollama 通用的现代标准，也是 MCP
（项目 14）、LangChain 工具（项目 09）共同的地基。**理解了这 4 条消息的
流转，所有 Agent 框架的工具循环对你都不再神秘。**

## How

```bash
cd agents/11_function_calling
python function_calling.py --demo                # 离线：完整协议流程演示
python function_calling.py "北京天气怎么样？"      # 真实调用本地 Ollama
```

`--demo` 分四部分：①打印发给 API 的两个工具 JSON Schema；②单工具调用
（北京天气 → `Sunny, 28C`）；③并行 tool_calls（上海/东京各查天气+人口，
一次响应 4 个调用）；④打印完整 message flow（user → assistant(tool_calls)
→ tool → assistant）。真实模式预期输出：`Round 1` 模型发起
`get_weather(beijing)`，回传结果后 `Round 2` 给出最终中文回答。

执行器与主循环：

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

工具结果必须以 `{"role": "tool", ...}` 消息追加后**再请求一轮**，模型才能
基于结果作答。终止判定也变得极简：**响应里没有 tool_calls 就是最终答案**。

## Deep Dive

**模型并不"执行"函数**：它只输出"想调用的函数名与参数 JSON"，执行永远
发生在你的运行时，结果再喂回去。

踩坑清单：

- `role:"tool"` 消息的 `tool_name`/`tool_call_id` 要与调用对应，多工具
  并行时对不上号模型会困惑；
- 未知工具、参数校验失败都应返回错误字符串（模型会重试），不要抛异常
  中断循环——模型可能幻觉出不存在的工具名或越界参数；
- 本地小模型的 schema 遵循度弱于云端旗舰，复杂参数要加 enum 约束。

## Q&A

**Q1: Function Calling 的完整消息流是什么？**

user 提问 → assistant 携带 tool_calls → tool 消息回传结果 → assistant
给出最终文本；循环至响应不含 tool_calls。

**Q2: arguments 为什么是字符串？**

协议设计使 JSON 以字符串传输以适配 token 化生成；客户端必须 `json.loads`
并做异常处理。

**Q3: 模型返回不存在的工具怎么办？**

返回 "Unknown tool: ..." 的 tool 消息，模型通常下一轮会修正；执行器永远
不因模型输出而崩溃。
