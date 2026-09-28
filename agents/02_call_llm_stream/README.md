# 02 · 流式输出：SSE 打字机效果的完整拆解

> 打开 `stream` 开关，用 `requests` 的流式读取逐个接住 token（模型处理
> 文本的最小单位），实现聊天应用常见的逐字打字机效果，并看清 SSE 数据流
> 的原始样貌。读完你能独立解析一条流式响应，并说出打字机效果的三个必要
> 条件。

## Background

在流式输出普及之前，调用聊天模型只有一种交付方式：发请求，等模型把整段
回复全部生成完，服务器再一次性返回一个大 JSON（键值对格式的数据交换
文本）。生成是逐 token 进行的，交付却是全有或全无。

撞墙的场景在聊天产品里最明显：模型生成一段长回复需要 5-30 秒，用户盯着
一片空白屏幕干等；程序侧同样受限——想在生成中途就拿部分内容做处理，
接口不支持。

流式传输因此成为聊天类 API 的标配：服务器边生成边推送，客户端边接收边
显示。承载它的协议逐渐收敛为 SSE（Server-Sent Events，基于 HTTP 的
服务器单向推送协议），OpenAI 与 Ollama（在本机运行大模型的工具）等主流
接口均兼容。

亲手拆一次 SSE 字节流，以后用任何 SDK（厂商提供的封装库）的
`stream=True`，都知道底下发生了什么。

## What

流式输出（streaming），指服务器把回复拆成小段、边生成边推送、客户端边
接收边显示的传输方式；SSE 是承载它的协议，每行一个 `data: ` 前缀加一段
JSON。

心智模型一句话：**流式不是新技术，就是把"一个大 JSON"换成"一行一个
JSON"逐行喂给你。** 可以把两种模式想象成上菜的差别：非流式是整桌菜做完
才一起上，流式是每做好一道就端一道。但和上菜不同的是：流式的每一"道"
只是几个字的增量片段，完整回复要客户端自己按顺序拼接。

流式三要素（payload 指发给 API 的请求体），缺一条就退化回非流式：

| 要素 | 代码 | 缺了会怎样 |
| :--- | :--- | :--- |
| 请求声明流式 | payload 里 `"stream": true` | 服务端仍返回一个大 JSON |
| 客户端流式读取 | `requests.post(..., stream=True)` + `iter_lines()` | `requests` 会把字节流整个读完才返回 |
| 立即刷新 | `print(chunk, end="", flush=True)` | 终端攒够缓冲区才显示，没有打字机效果 |

## When to Use

核心判断：回复是给人实时看的，开流式；给程序批量消费的，用非流式。

典型场景：

- **做聊天界面**：用户提交问题后盯着屏幕，打字机效果把 5-30 秒的等待
  变成"渐进而出"——首字延迟（TTFT，Time To First Token，从发出请求到
  看到第一个字的时间）是聊天体验的生命线；
- **Agent 边读边解析**：在回复流里提前发现工具调用意图，而不必等全部
  生成完；
- **长回复预览**：内容很长时让用户先看到开头，随时可以中断。

何时不用：批量离线任务（如批量摘要、数据清洗）要的是吞吐而不是实时性，
值得用非流式换吞吐。

| 方案 | 差异 | 什么时候选它 |
| :--- | :--- | :--- |
| 非流式（一次一个大 JSON） | 实现最简单，首字等待等于全部生成时间 | 批量离线任务 |
| SSE 流式（本篇） | 逐 token 推送，首字快，客户端负责拼接 | 聊天界面、Agent 实时解析 |
| WebSocket | 全双工长连接，双向都能主动发 | 客户端也要持续向服务端推数据的场景 |

## Quick Start

前置条件与 01 实验相同：本机已启动 Ollama，已执行 `ollama pull
qwen3.8:latest`，Python 环境装有 `requests` 库。

```bash
cd agents/02_call_llm_stream
python call_llm_stream.py
# 🧑 请输入提示词: （直接回车则用默认提示词）
```

脚本依次做四件事：

1. `input()` 读提示词（空输入回退默认："用一句话解释什么是人工智能"）；
2. 以 `stream=True` 发 POST（HTTP 中提交数据的请求方法），拿到的是
   **字节流**（bytes 序列）而非 JSON；
3. `process_stream()` 逐行解析、逐 token 打印（打字机效果）；
4. 返回拼接好的完整文本。

预期输出：`🤖 助手: ` 后文字逐字蹦出，速度受本地推理速度限制。

流式响应在网络上长这样——每行一个 `data: ` 前缀 + 一段 JSON：

```
data: {"message":{"content":"人"},"done":false}
data: {"message":{"content":"工"},"done":false}
...
data: [DONE]
```

## How It Works

本节沿数据流向展开：一段文字从模型到你的终端，中间经过哪几站。

### 数据管线

从生成到终端是一条数据管线：模型逐 token 生成 → HTTP chunked 传输
（chunked transfer，把响应拆成小块逐块发送的传输编码）→ `iter_lines()`
按行切 → 每行剥掉 `data: ` 前缀后 `json.loads`。

增量文本同时送往两处：终端打印（`flush=True`，flush 即刷新输出缓冲区，
让内容立即显示）和 `full_content` 累积。

你在 Quick Start 看到的"逐字蹦出"，就来自管线最后一站：每个增量片段先
`print` 到终端，再累加进 `full_content`。

### 逐行解析函数

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

每个 chunk（一次推送的数据片段）只含几个字的增量，完整回复靠
`full_content += chunk` 拼出来。流式结束后的 `full_content` 与非流式
结果的 `message.content` 等价——可以在 01/02 实验之间互相验证。

三种行要区别对待：`data: ` 开头的 JSON 行是正文；`[DONE]` 是 OpenAI 的
结束哨兵（约定的特殊标记值）；解析失败的行（心跳注释行、空行——保持
连接活跃的周期性消息）必须 `try/except` 后 `continue`，不能让整个流
崩掉。

### 两种结束标记

Ollama 用 `done: true` 标记结束并附统计字段；OpenAI 用哨兵值 `[DONE]`。
本脚本两种都兼容：先剥前缀，再判 `[DONE]`，最后看 `done` 字段。实测
流式 overhead（逐块传输带来的协议开销）约 2%-5%，代价很小。

## Pitfalls & Q&A

踩坑清单（每条 = 现象 + 原因 + 解法）：

- **手写 `iter_content` 循环后 JSON 解析随机失败**：现象是某些行解析
  报错。原因：`iter_lines()` 自带按行缓冲，自己手写按字节切的循环容易
  把一行 JSON 切成两半。解法：用默认参数的 `iter_lines()`。
- **打字机效果时有时无**：现象是同样的代码在不同终端下逐字效果不同。
  原因：Windows 终端的 `flush=True` 效果受终端模拟器影响。解法：换
  VS Code 集成终端，表现最好。
- **网络断开时脚本直接崩溃**：现象是流中途抛 `ChunkedEncodingError`。
  原因：chunked 传输中途断连，迭代器抛异常。解法：生产代码捕获该异常
  并提示重试。

**Q1: SSE 是什么？和 WebSocket 的区别？**

SSE 是单向服务器推送（基于 HTTP，文本行协议），WebSocket 是全双工。
大模型的流式回复只需要服务器→客户端方向，SSE 更简单。

**Q2: 为什么 `print` 里必须 `flush=True`？**

Python 标准输出是行缓冲/块缓冲，遇到 `\n` 或缓冲区满才真正写出；
`end=""` 的逐字打印永远凑不齐换行，必须手动刷新。

**Q3: 流式响应怎么统计 token 用量？**

Ollama 在最后一个 `done: true` 的 chunk 里附 `eval_count` 等字段；
OpenAI 可在请求里带 `stream_options: {"include_usage": true}`。
