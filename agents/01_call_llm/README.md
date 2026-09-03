# 01 · Raw HTTP 调用 LLM API：一切 Agent 的最小骨架

> 在写任何 Agent 之前，先回答一个问题：你调用的到底是什么？
> 本篇不用任何 SDK，直接用 `requests` 发一个 HTTP 请求，把「调用 LLM」这件事
> 还原到它最朴素的样子。理解了这个最小骨架，后面所有的流式输出、ReAct、
> Function Calling 都只是它的增量扩展。

## 1. 为什么需要它

LangChain、OpenAI SDK 这些框架把调用细节封装得越好，出问题时你越不知道该去哪查。
是网络超时？是 payload 字段写错？还是响应结构和文档不一样？**亲手发过原始
HTTP 请求的人，排查这些问题只要一个 `print(response.json())`。**

其次是模型本地化的需求：用 Ollama 跑本地模型（本系列统一用 `qwen3.8:latest`），
不需要 API Key、不花钱、数据不出机器。掌握原始调用后，切换到 OpenAI/DeepSeek
只是换 URL 和认证头的事。

最后，Agent 的本质是「程序在循环里反复调用 LLM」。循环里的每一次调用，都是
本篇这一个请求。

## 2. 总览：核心机制一图看懂

![Raw HTTP 调用时序](images/llm_api.sequence.svg)

**怎么看这张图**：左侧是 `call_llm.py`（调用者），中间是 Ollama Server，
右侧是加载的模型。一次调用分三段：组装 payload（`model + messages + options`）、
`POST /api/chat` 等待推理完成、从完整 JSON 里取出 `message.content`。

心智模型一句话：**聊天 API 就是一个函数——输入一组消息，输出一条回复。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/01_call_llm/images/llm_api.sequence.html)（或本地打开 [`images/llm_api.sequence.html`](images/llm_api.sequence.html)）。

## 3. 快速开始

```bash
cd agents/01_call_llm
python call_llm.py          # 一条命令跑完全流程
```

脚本依次做四件事：

1. 打印连接地址与模型名（确认在跟谁说话）；
2. `call_llm()` 发送 `stream=False` 的 POST 请求（等待完整回复）；
3. `extract_content()` 从响应里取出 `message.content`；
4. `print_usage()` 打印元数据（`model`、`created_at`）。

预期输出：`🤖 助手: 人工智能是指……`（一句话解释 AI）。若连接被拒绝，先确认
Ollama 在跑：`curl http://localhost:11434/api/tags`。

## 4. 核心概念

### 4.1 messages 数组：角色即协议

```python
"messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user",   "content": prompt}
]
```

- `system`：定义角色与规则，模型最"听话"的位置；
- `user`：本轮输入；
- `assistant`：模型的历史回复（多轮对话时由你手动带回去，见项目 05）。
- 顺序即语境：同样的 user 消息，前面挂什么 system，回答风格完全不同。

### 4.2 options：Ollama 的采样参数

`temperature` 控制随机性（项目 04 会专门做对照实验），`num_predict` 限制
生成 token 数。注意 OpenAI 里叫 `max_tokens`——**同一概念在不同 API 里的
字段名不同**，这是封装框架掩盖不了的差异。

### 4.3 响应结构与解析

非流式响应是一个完整 JSON，回复文本固定在 `["message"]["content"]`。
`extract_content()` 对 `KeyError` 做了防御：结构变了就打印原始 JSON 帮你调试。

**易错点**：`qwen3.8` 这类推理模型可能把正文写进 `message.thinking` 而
`content` 为空（后续项目都会做兜底），这是本系列反复出现的真实坑。

### 4.4 Ollama vs OpenAI 速查

| 维度 | Ollama | OpenAI |
| :--- | :--- | :--- |
| 端点 | `POST /api/chat` | `POST /v1/chat/completions` |
| 认证 | 无需 Key | `Authorization: Bearer sk-xxx` |
| 消息格式 | `messages[{role, content}]` | 相同 |
| 流式 | `stream: true` → SSE | 相同 |
| 最大 token | `options.num_predict` | `max_tokens` |

## 5. 代码关键部分

```python
def call_llm(prompt, temperature=0.7, max_tokens=2048):
    payload = {
        "model": MODEL,                # qwen3.8:latest，本地已 pull 的模型
        "messages": [...],             # 角色化的上下文
        "options": {"temperature": temperature,
                    "num_predict": max_tokens},   # Ollama 的采样参数都在 options 里
        "stream": False,               # False: 一次性等完整 JSON
    }
    response = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=60)
    response.raise_for_status()        # 4xx/5xx 直接抛异常，不让坏响应溜进解析
    return response.json()
```

坑清单：

- 忘记 `stream: False` 时部分版本默认流式，`response.json()` 会炸；
- `timeout` 必须给：本地模型首次加载（冷启动）可能要几十秒；
- 工程化解析还要看 `finish_reason`（是否被截断）与 `usage`（计费/计量）。

## 6. 文件结构

```
01_call_llm/
├── README.md                  # 本篇教程
├── call_llm.py                # 主脚本（约 100 行），最小调用骨架
└── images/
    ├── llm_api.sequence.json  # 图源（Typed JSON，可 diff、可复现）
    ├── llm_api.sequence.html  # 交互版架构图（自包含单文件）
    └── llm_api.sequence.svg   # 双主题矢量图（README 内嵌，跟随系统深浅色）
```

## 7. 面试要点

- **Q: 不用 SDK 直接调 LLM API，最小需要哪些字段？**
  A: `model` + `messages`，其余（`options`/`stream`）都有默认值。
- **Q: system / user / assistant 三种角色各是什么语义？**
  A: system 定角色规则、user 是输入、assistant 是历史回复；多轮对话靠把
  assistant 消息放回 messages 实现"记忆"。
- **Q: Ollama 和 OpenAI 接口的三个关键差异？**
  A: 端点路径、认证方式（无 Key vs Bearer）、参数名（`num_predict` vs `max_tokens`）。
- **Q: `raise_for_status()` 在这里为什么重要？**
  A: 让 4xx/5xx 在解析前就抛异常，避免拿错误页的 HTML 去 `json()` 产生更难懂的报错。
- **Q: 推理模型（如 qwen3.8）的响应有什么特殊之处？**
  A: 可能带 `message.thinking` 字段且 `content` 为空，解析要做兜底。

## 8. 总结

一次 LLM 调用 = 组装 messages + POST + 取 `message.content`，这个最小骨架是
整个系列的"系统调用"。下一篇给它加上 `stream: true`，让回复像 ChatGPT 一样
一个字一个字蹦出来。
