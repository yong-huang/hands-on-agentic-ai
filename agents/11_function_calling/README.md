# 11 · Function Calling：协议级的工具调用

> 换用 API 原生的 Function Calling（函数调用协议）：把工具的 JSON Schema
> （机器可读的工具说明书）放进请求的 `tools` 参数，模型直接返回结构化的
> `message.tool_calls`——没有正则、没有格式猜谜。读完本篇，你能写出不
> 依赖文本解析的工具循环，并看懂所有 Agent 框架工具循环的底层消息流。

## Background

在协议级方案出现之前，工具调用靠"约定文本格式"：开发者要求模型按固定格式输出，比如 `Action: get_weather[beijing]`，再用正则表达式从文本里抠出工具名和参数。06/07 实验的循环就是这么做的。

痛点场景：正则表达式（regular expression，用模式串匹配并提取文本的工具）解析在三处撞墙：

- **格式跑偏即解析失败**：模型偶尔在格式外加一句"好的，我来查询"，或者给参数包上引号、换个括号，程序只能重试或兼容各种变体；
- **参数类型靠猜**：文本里传出来的都是字符串，"28"是数字还是文本要自己猜着转；
- **每轮只能一个调用**：一轮只能发起一个工具调用，想同时查两个城市就得跑两轮。

根源在于**用自然语言传结构化信息**。Function Calling 把这件事挪进了协议层：请求里带上工具清单，模型直接返回结构化的工具调用对象。

它已是 OpenAI / Anthropic / Ollama 通用的现代标准，也是 MCP（Model Context Protocol，连接外部工具的开放协议，见 14 实验）与 LangChain 工具体系（见 09 实验）共同的地基。

## What

Function Calling（函数调用）是**大模型 API 原生的工具调用协议**：调用方把每个工具的 schema（机器可读的工具说明书：叫什么名字、收什么参数、各是什么类型）随请求发送，模型以结构化 JSON 返回"要调用哪个工具、参数是什么"，由调用方执行后把结果回传。

一个必须先建立的认知：**模型并不"执行"函数。** 它只输出"想调用的函数名与参数 JSON"，执行永远发生在你的运行时（你写的 Python 程序）里，结果再喂回去。

可以把这想象成餐厅：Function Calling 把"工具菜单"递给模型，模型"点菜"，你"炒菜"，再把菜端回去。但和餐厅点菜不同的是，模型点完菜不会等着上菜——它必须收到你端回的结果消息，才会进行下一轮。

一条完整的消息流（四步）：

1. 用户提问（user 消息）；
2. Agent 把 `messages + tools schema` 发给模型，模型返回
   `message.tool_calls`（结构化 JSON，一次可含多个调用，即并行调用）；
3. Agent 本地以 `fn(**arguments)` 执行工具，结果以 `role:"tool"` 消息回传；
4. 模型基于结果返回纯文本，转达用户。

心智模型一句话：**Function Calling = 把"工具菜单"给模型，模型"点菜"，你"炒菜"，再把菜端回去。**

点菜的两端各有一份关键数据结构。**请求侧**：工具以 JSON Schema（用 JSON 描述结构与类型的标准）形式放进请求的 `tools` 参数。`description` 和参数描述直接决定模型选工具、填参数的质量——**schema 是给模型看的文档**，不是给人看的注释。

你在 `--demo` 第①部分看到的两个工具 Schema，就是按这个结构生成的：

```json
{"type": "function", "function": {
  "name": "get_weather",
  "description": "查询指定城市的天气",
  "parameters": {"type": "object",
                 "properties": {"city": {"type": "string", "description": "城市名"}},
                 "required": ["city"]}}}
```

**响应侧**：模型返回的 `tool_calls` 里，`arguments` 是 **JSON 字符串**而不是对象——注意下面 `"{\"city\": \"beijing\"}"` 的外层引号，执行前必须先 `json.loads`（把 JSON 字符串解析回 Python 对象）：

```json
{"role": "assistant", "tool_calls": [
  {"id": "call_1", "type": "function",
   "function": {"name": "get_weather", "arguments": "{\"city\": \"beijing\"}"}}]}
```

`tool_calls` 是个数组，单次响应可同时携带多个调用（即并行调用）；每个调用带 `id`，供结果回传时一一对应——`--demo` 第③部分"一次响应 4 个调用"对应的就是这个设计。

## When to Use

这节回答：什么条件下值得把工具循环搬到协议级，什么条件下只能退回文本协议。

典型场景：

- **所用模型支持 `tools` 参数时**（qwen3.8 支持，主流云端模型均支持）：
  工具循环应默认采用 Function Calling，省掉全部解析代码；
- **参数结构复杂时**：类型由 schema 声明并校验，不再靠字符串猜测转换；
- **需要一次并行调用多个工具时**：单响应可携带多个 tool_calls，一轮
  完成多路查询。

何时不用：所用模型或本地运行环境不支持 `tools` 参数时，只能退回文本
ReAct 协议；本地小模型对协议的遵循度不稳定，效果不佳时也需考虑。

与文本 ReAct 的对比：

| 维度 | 文本 ReAct | Function Calling |
| :--- | :--- | :--- |
| 解析 | 正则 + 变体兼容 + 重试 | 零解析，直接读 JSON |
| 参数类型 | 字符串，自己转 | Schema 声明，类型安全 |
| 并行调用 | 每轮一个 | 单响应多 tool_calls |
| 模型要求 | 会按格式写文本即可 | 模型需支持 tools 参数（qwen3.8 支持） |

## Quick Start

前置条件：本地装有 Python 3；`--demo` 为离线演示，不调用外部接口；真实模式需要本地 Ollama（在本地运行开源大模型的工具）已启动，且所用模型支持 tools 参数。

```bash
cd agents/11_function_calling
python function_calling.py --demo                # 离线：完整协议流程演示
python function_calling.py "北京天气怎么样？"      # 真实调用本地 Ollama
```

`--demo` 分四部分：①打印发给 API 的两个工具 JSON Schema；②单工具调用
（北京天气 → `Sunny, 28C`）；③并行 tool_calls（上海/东京各查天气+人口，
一次响应 4 个调用）。

④打印完整 message flow（user → assistant(tool_calls)
→ tool → assistant）。

真实模式的诚实预期：`Round 1` 模型发起 `get_weather(beijing)`，程序执行
后回传结果，`Round 2` 模型给出最终中文回答。首次运行若模型没有发起工具
调用，通常所用模型不支持 tools 参数——换支持的模型再试。

## How It Works

这节讲循环本身的机制：执行器怎么"炒菜"，主循环怎么流转消息、怎么判定
终止。What 节的两侧数据结构在这里被消费。

### 执行器与主循环

执行器负责"炒菜"，主循环负责消息流转。终止判定极简：**响应里没有
tool_calls，就是最终答案。**

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

工具结果必须以 `{"role": "tool", ...}` 消息追加到 `messages` 后**再请求
一轮**，模型才能基于结果作答——这正是 `--demo` 第④部分打印的完整消息
流，也是真实模式里 `Round 1` 与 `Round 2` 之间发生的事。

## Pitfalls & Q&A

踩坑清单，每条按"现象 → 原因 → 解法"：

- **现象：多工具并行后模型答非所问。** 原因：`role:"tool"` 消息的
  `tool_name`/`tool_call_id` 与调用对不上号，模型分不清哪个结果对应哪次
  调用。解法：每条 tool 消息严格携带对应调用的标识字段。
- **现象：模型请求了一个不存在的工具，程序崩溃。** 原因：模型可能幻觉
  （编造不存在的内容）出不存在的工具名或越界参数，而执行器抛了异常。
  解法：未知工具、参数校验失败都返回错误字符串（如 `"Unknown tool: ..."`
  的 tool 消息）回传给模型，模型通常下一轮自行修正——执行器永远不因
  模型输出而崩溃。
- **现象：本地小模型填错参数类型或漏填必填参数。** 原因：本地小模型的
  schema 遵循度弱于云端旗舰模型。解法：复杂参数加 enum 约束（把取值
  限制在列出的几个选项内）。

**Q: `arguments` 为什么是字符串而不是 JSON 对象？**

协议设计使然：模型按 token（模型生成文本的最小单位）逐个生成，JSON 以
字符串传输才能适配这种生成方式。客户端必须 `json.loads` 并对解析失败做
异常处理。
