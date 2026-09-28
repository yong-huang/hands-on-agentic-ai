# 01 · Raw HTTP 调用 LLM API：一切 Agent 的最小骨架

> 本篇不借助任何封装库，直接用 Python 的 `requests` 库发送一个 HTTP 请求，
> 完成「组装请求 → 调用大模型 → 解析回复」的最小完整链路。读完你能独立
> 调用一次 LLM（大语言模型）API，并具备排查封装层之下问题的能力。

## Background

在直接发 HTTP 请求成为学习路径之前，绝大多数开发者通过官方 SDK
（Software Development Kit，厂商提供的封装库）或 Agent 框架调用大模型：
装一个库，一行 `client.chat(...)` 就能拿到回复，请求组装、发送、解析全部
由库内部完成。

这层封装在出错时会变成障碍：是网络超时、请求字段写错，还是响应结构和文档
不一致？此时你手里往往只有一条框架抛出的报错栈，看不到实际发出了什么、
收到了什么。另一个现实约束是云端 API 需要 API Key（调用云端服务的密钥）、
按量计费，且请求数据要出本机。

而所有 LLM 服务最底层的形态就是 HTTP API。绕过封装直接发请求，等于把一次
调用还原成看得见的三个动作，问题定位也退化成一句 `print(response.json())`。

这也是理解 Agent（在循环中自主调用模型并执行动作的程序）的起点——Agent
的本质是程序在循环里反复调用 LLM，循环里的每一次调用，都是本篇这样一个
HTTP 请求。

## What

直接 HTTP 调用，指不经过 SDK，用 HTTP 客户端直接请求 LLM（Large Language
Model，大语言模型）服务的聊天接口。

一次调用分三段：组装 payload（发给 API 的请求体，一个 JSON 对象——键值对
格式的数据交换文本）、`POST`（HTTP 中提交数据的请求方法）到 `/api/chat`
等待推理完成、从完整 JSON 响应里取出 `message.content`。

心智模型一句话：**可以把聊天 API 想象成一个普通函数——输入一组消息，输出
一条回复。** 但和本地函数不同的是：它运行在远端服务器上，有网络延迟和超时
风险；并且同一个输入可能得到不同输出，因为回复由带随机性的采样过程生成
（见 How It Works 的 options 部分）。

## When to Use

判断标准很简单：想看清调用细节时用它，想省事时用封装。

典型场景：

- **排查封装层问题**：用 LangChain（流行的 Agent 开发框架）等框架开发时
  调用突然失败，直接发一个原始请求，能把「框架的错」和「服务端的错」分开；
- **数据不出本机**：把模型跑在本地（本系列统一用 Ollama——在本机运行
  大模型的工具，模型名 `qwen3.8:latest`），不需要 API Key、不花钱、
  数据不出机器；
- **学习 Agent 原理**：想看清「程序在循环里反复调用模型」中每一次调用的
  完整形态。

何时不用：业务生产代码优先用官方 SDK——它内置重试、错误分类和类型定义；
需要频繁切换多家模型服务时，选统一网关类工具（如 LiteLLM、OpenRouter），
不必自己维护每家的字段差异。

| 方案 | 差异 | 什么时候选它 |
| :--- | :--- | :--- |
| 原始 HTTP（本篇） | 每个字段显式可见，零封装 | 排查问题、学习原理、最小依赖 |
| 官方 SDK | 封装请求与解析，内置重试、类型 | 日常业务开发 |
| Agent 框架 | 在调用之上编排循环、工具、记忆 | 需要多步任务与工具调用时 |

## Quick Start

前置条件：本机已安装并启动 Ollama，已执行 `ollama pull qwen3.8:latest`
把模型下载到本地；Python 环境装有 `requests` 库（`pip install requests`）。

```bash
cd agents/01_call_llm
python call_llm.py          # 一条命令跑完全流程
```

脚本依次做四件事：

1. 打印连接地址与模型名（确认在跟谁说话）；
2. `call_llm()` 发送 `stream=False` 的 POST 请求（等待完整回复）；
3. `extract_content()` 从响应里取出 `message.content`；
4. `print_usage()` 打印元数据（`model`、`created_at`）。

预期输出：`🤖 助手: 人工智能是指……`（一句话解释 AI）。若连接被拒绝，先
确认 Ollama 在跑：`curl http://localhost:11434/api/tags`。回复的具体措辞
每次运行可能不同，属于正常现象。

## How It Works

本节按一次请求的流向展开：请求怎么组装、参数放在哪里、响应怎么解析。

### 核心调用函数

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

Quick Start 里那行 `🤖 助手: ……` 就来自这段代码：`payload` 组装请求，
`requests.post` 发送并等待完整 JSON 返回，`raise_for_status()` 保证
4xx/5xx（客户端/服务端错误状态码）不会溜进解析阶段。

### messages 数组：角色即协议

```python
"messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user",   "content": prompt}
]
```

- `system`：定义角色与规则，模型最"听话"的位置；
- `user`：本轮输入；
- `assistant`：模型的历史回复（多轮对话时由你手动带回去，见 05 实验）。

顺序即语境：同样的 user 消息，前面挂什么 system，回答风格完全不同。

### options：采样参数与字段名差异

`options` 里是 Ollama 的采样参数（采样——模型逐个挑选下一个输出词的过程，
参数决定挑选时的随机程度）：`temperature` 控制随机性（见 04 实验），
`num_predict` 限制生成的 token（模型处理文本的最小单位，一个汉字或半个
英文单词大致对应一个 token）数。

**同一概念在不同 API 里的字段名不同**，这是封装框架掩盖不了的差异。下表中
端点指 API 的 URL 地址，认证指向服务证明调用者身份，流式指服务器边生成边
发送回复（而非等全部生成完再返回）：

| 维度 | Ollama | OpenAI |
| :--- | :--- | :--- |
| 端点 | `POST /api/chat` | `POST /v1/chat/completions` |
| 认证 | 无需 Key | `Authorization: Bearer sk-xxx` |
| 消息格式 | `messages[{role, content}]` | 相同 |
| 流式 | `stream: true` → SSE | 相同 |
| 最大 token | `options.num_predict` | `max_tokens` |

SSE（Server-Sent Events，服务器向客户端单向持续推送数据流的协议）。

### 响应结构与解析

非流式响应是一个完整 JSON，回复文本固定在 `["message"]["content"]`。
`extract_content()` 对 `KeyError`（访问字典中不存在的键时抛出的 Python
异常）做了防御：结构变了就打印原始 JSON 帮你调试。

一个已知例外：`qwen3.8` 这类推理模型（会把思考过程单独输出的模型）可能
把正文写进 `message.thinking` 而 `content` 为空，现象与解法见文末踩坑
清单。

## Pitfalls & Q&A

踩坑清单（每条 = 现象 + 原因 + 解法）：

- **解析阶段 `response.json()` 抛异常**：报错发生在取 JSON 的一步。原因：
  忘记写 `stream: False` 时，部分版本默认流式，返回的不是单个 JSON。解法：
  在 payload 里显式声明 `"stream": False`。
- **请求超时中断**：脚本运行几十秒后被超时打断。原因：本地模型首次加载
  （冷启动）可能要几十秒。解法：`timeout` 必须给且给足，脚本里是 60 秒。
- **解析出的回复为空字符串**：`content` 取出来是空的。原因：`qwen3.8`
  这类推理模型把正文写进了 `message.thinking`。解法：解析时对 `thinking`
  字段做兜底读取（本系列后续实验都带这个兜底）。

工程化解析还要看两个字段：`finish_reason`（回复是否被长度截断）与
`usage`（token 用量，计费与计量的依据）。

**Q1: 不用 SDK 直接调 LLM API，最小需要哪些字段？**

`model` + `messages`，其余（`options`/`stream`）都有默认值。

**Q2: `raise_for_status()` 在这里为什么重要？**

让 4xx/5xx 在解析前就抛异常，避免拿错误页的 HTML 去 `json()` 产生更难懂
的报错。

**Q3: 多轮对话的"记忆"是怎么实现的？**

把历史的 assistant 消息放回 messages 数组再发——API 本身无状态，记忆
完全由调用方维护（见 05 实验）。
