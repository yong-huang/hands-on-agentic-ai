# 02 · 流式输出：SSE 打字机效果的完整拆解

> 把 `stream` 打开，用 `requests` 的流式读取逐个接住 token，实现 ChatGPT
> 风格的逐字打字机效果——并搞清楚 SSE 数据到底长什么样。

## What

从生成到终端是一条数据管线：模型逐 token 生成 → HTTP chunked 传输 →
`iter_lines()` 按行切 → 每行剥掉 `data: ` 前缀后 `json.loads` → 增量文本
同时送往终端打印（`flush=True`）和 `full_content` 累积。

流式三要素，缺一条就退化回非流式：

| 要素 | 代码 | 缺了会怎样 |
| :--- | :--- | :--- |
| 请求声明流式 | payload 里 `"stream": true` | 服务端仍返回一个大 JSON |
| 客户端流式读取 | `requests.post(..., stream=True)` + `iter_lines()` | `requests` 会把字节流整个读完才返回 |
| 立即刷新 | `print(chunk, end="", flush=True)` | 终端攒够缓冲区才显示，没有打字机效果 |

心智模型一句话：**流式不是新技术，就是把"一个大 JSON"换成"一行一个
JSON"逐行喂给你。**

## Why

首字延迟（TTFT）是聊天体验的生命线：非流式要等 5-30 秒才看到第一个字，
流式把"等待"变成"渐进而出"。对 Agent 来说流式还有工程价值——可以
**边读边解析**，在回复流里提前发现工具调用意图，而不必等全部生成完。

SSE（Server-Sent Events）是 LLM API 事实上的流式标准，OpenAI/Ollama
兼容。亲手拆过一次字节流，以后用任何 SDK 的 `stream=True` 你都知道底下
发生了什么。

## How

```bash
cd agents/02_call_llm_stream
python call_llm_stream.py
# 🧑 请输入提示词: （直接回车则用默认提示词）
```

脚本依次做四件事：

1. `input()` 读提示词（空输入回退默认："用一句话解释什么是人工智能"）；
2. 以 `stream=True` 发 POST，拿到的是**字节流**而非 JSON；
3. `process_stream()` 逐行解析、逐 token 打印（打字机效果）；
4. 返回拼接好的完整文本。

预期输出：`🤖 助手: ` 后文字逐字蹦出，速度受本地推理速度限制。

SSE 行的格式——每行一个 `data:` 前缀 + JSON：

```
data: {"message":{"content":"人"},"done":false}
data: {"message":{"content":"工"},"done":false}
...
data: [DONE]
```

Ollama 用 `done: true` 标记结束并附统计字段；OpenAI 用哨兵值 `[DONE]`。
本脚本两种都兼容（先剥前缀，再判 `[DONE]`）。**易错点**：某行可能不是
合法 JSON（心跳注释行、空行），解析必须 try/except 后 `continue`，不能
让整个流崩掉。

每个 chunk 只含几个字的增量，完整回复需要客户端自己拼接（`full_content`）。
流式结束后的 `full_content` 与非流式结果的 `message.content` 等价——可以
在项目 01/02 之间互相验证。实测流式 overhead 约 2%-5%（逐块传输的协议
开销），换来的是体验上质变：**聊天/Agent 场景无脑开流式**；只有批量
离线任务才值得用非流式换吞吐。

## Deep Dive

**逐行解析函数**：

```python
def process_stream(response):
    full_content = ""
    for line in response.iter_lines():            # 按行迭代字节流
        if not line:
            continue
        line = line.decode("utf-8")
        if line.startswith("data: "):
            line = line[6:]                        # 剥掉 "data: " 前缀
        if line.strip() == "[DONE]":
            break
        try:
            data = json.loads(line)
            chunk = data.get("message", {}).get("content", "")
            if chunk:
                print(chunk, end="", flush=True)   # 打字机的关键：flush
                full_content += chunk
            if data.get("done", False):
                break                              # Ollama 的结束标记
        except json.JSONDecodeError:
            continue                               # 心跳/非 JSON 行直接跳过
    return full_content
```

踩坑清单：

- `iter_lines()` 自带按行缓冲，但它依赖 `chunk_size` 参数——默认值即可，
  自己手写 `iter_content` 循环反而容易把一行 JSON 切成两半；
- Windows 终端的 `flush=True` 效果受终端模拟器影响，VS Code 集成终端
  表现最好；
- 流中断（网络断开）会抛 `ChunkedEncodingError`，生产代码要捕获并提示
  重试。

## Q&A

**Q1: SSE 是什么？和 WebSocket 的区别？**

SSE 是单向服务器推送（基于 HTTP，文本行协议），WebSocket 是全双工。
LLM 流式回复只需要服务器→客户端方向，SSE 更简单。

**Q2: 为什么 `print` 里必须 `flush=True`？**

Python 标准输出是行缓冲/块缓冲，遇到 `\n` 或缓冲区满才真正写出；
`end=""` 的逐字打印永远凑不齐换行，必须手动刷新。

**Q3: 流式响应怎么统计 token 用量？**

Ollama 在最后一个 `done: true` 的 chunk 里附 `eval_count` 等字段；
OpenAI 可在请求里带 `stream_options: {"include_usage": true}`。
