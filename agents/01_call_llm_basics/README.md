# 01 · 调用 LLM 基础：裸 HTTP、流式输出与温度对照

> 本篇不借助任何封装库，用 Python 的 `requests` 把调用大模型（LLM）的
> 三件基础事一次讲透：非流式的最小调用骨架、SSE 流式的打字机效果、
> temperature（采样温度）的对照实验。读完你能独立完成一次调用、解析一条
> 流式响应，并为不同任务选对温度档位。

## Background

绝大多数开发者通过官方 SDK（厂商提供的封装库）或 Agent 框架调用大模型：
一行 `client.chat(...)` 就能拿到回复。这层封装在三种时刻会变成障碍——

- **出错时**：网络超时、字段写错还是响应结构变了？你手里只有框架抛出的
  报错栈，看不到实际发出了什么、收到了什么；
- **等回复时**：模型生成一段长回复要 5-30 秒，非流式交付全有或全无，
  用户只能盯着白屏，程序也无法在中途拿部分内容做处理；
- **复现时**：同一提示词今天回答工整、明天回答跑偏，照抄教程的 0.7
  说不清到底改变了什么。

而所有 LLM 服务最底层的形态就是 HTTP API。绕过封装直接发请求，这三个
问题的答案就还原成三件看得见的事：一次 POST 请求、SSE（Server-Sent
Events，服务器向客户端单向持续推送的协议）字节流、softmax 前的一个除数。

这也是理解 Agent（在循环中自主调用模型并执行动作的程序）的起点——循环里
的每一次调用，都是本篇这样一个 HTTP 请求。

## What

直接 HTTP 调用，指不经过 SDK，用 HTTP 客户端请求 LLM（Large Language
Model，大语言模型）服务的聊天接口。三件事共用同一个端点：

| 子主题 | 心智模型一句话 | 关键代码 |
| :--- | :--- | :--- |
| 非流式调用 | 聊天 API 就是个函数：输入一组消息，输出一条回复——只是它跑在远端，有延迟与超时 | `requests.post` + `raise_for_status()` |
| 流式输出 | 把"一个大 JSON"换成"一行一个 JSON"逐行喂给你，像每做好一道菜就端一道 | `stream: true` 双侧声明 + `iter_lines()` |
| 温度对照 | temperature 是采样分布的形状旋钮：`p(x) = softmax(logits / T)` | 固定一切只改 T，量化输出差异 |

一次非流式调用分三段：组装 payload（发给 API 的请求体，一个 JSON 对象）、
`POST`（HTTP 中提交数据的请求方法）到 `/api/chat`、从完整 JSON 响应里取
`message.content`。流式与温度都是在这个骨架上的增量改动。

## When to Use

判断标准：想看清调用细节时用裸 HTTP，想省事时用封装；回复给人实时看就开
流式，给程序批量消费就用非流式；按任务对"稳定 vs 发散"的需求选温度。

典型场景：

- **排查封装层问题**：框架调用突然失败时发一个原始请求，把「框架的错」
  和「服务端的错」分开；
- **数据不出本机**：模型跑在本地（本系列统一用 Ollama——在本机运行大模型
  的工具），不需要 API Key、不花钱；
- **做聊天界面**：打字机效果把 5-30 秒等待变成"渐进而出"，首字延迟
  （TTFT，Time To First Token）是聊天体验的生命线；
- **工具调用、分类、抽取**：输出要被程序解析，选低温（T→0）保证可复现；
  头脑风暴、创意写作选高温（1.0 附近）让长尾词有机会。

何时不用：业务生产代码优先用官方 SDK（内置重试与类型）；批量离线任务要
吞吐不要实时，用非流式；输出质量不稳时先检查 Prompt 是否说清了要求——
temperature 只改变分布形状，弥补不了指令模糊。

| 方案 | 差异 | 什么时候选它 |
| :--- | :--- | :--- |
| 原始 HTTP（本篇） | 每个字段显式可见，零封装 | 排查问题、学习原理、最小依赖 |
| 官方 SDK | 封装请求与解析，内置重试、类型 | 日常业务开发 |
| Agent 框架 | 在调用之上编排循环、工具、记忆 | 需要多步任务与工具调用时 |

## Quick Start

前置条件：Ollama 已启动且已 `ollama pull qwen3.8:latest`；Python 装有
`requests`（`pip install requests`）。

```bash
cd agents/01_call_llm_basics
python call_llm_basics.py          # 依次跑三段（默认 all）
python call_llm_basics.py basic    # 只跑非流式最小调用
python call_llm_basics.py stream   # 只跑 SSE 流式
python call_llm_basics.py temp     # 只跑温度对照
```

`basic` 段打印连接信息后输出 `🤖 助手: 人工智能是指……`（一句话解释 AI）；
`stream` 段同一骨架换成流式，文字逐字蹦出并报告拼接的字符数；`temp` 段
对 0.0 / 0.5 / 1.0 三档各调一次，输出每档的长度、关键词命中、去重词数。

诚实预期：回复措辞每次运行可能不同（这正是 temperature 在起作用）；连接
被拒先确认 Ollama 在跑：`curl http://localhost:11434/api/tags`。

## How It Works

### messages 数组与 options：角色即协议

```python
"messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user",   "content": prompt}
],
"options": {"temperature": temperature, "num_predict": max_tokens},
"stream": False
```

- `system` 定义角色与规则，`user` 是本轮输入，`assistant` 是历史回复
  （多轮对话时由你手动带回去，见 03 实验）；
- `options` 是 Ollama 的采样参数（采样——模型逐个挑选下一个输出词的过程）：
  `temperature` 控制随机性，`num_predict` 限制生成 token（模型处理文本的
  最小单位）数。

**同一概念在不同 API 里字段名不同**，这是封装掩盖不了的差异（流式指
服务器边生成边发送回复）：

| 维度 | Ollama | OpenAI |
| :--- | :--- | :--- |
| 端点 | `POST /api/chat` | `POST /v1/chat/completions` |
| 认证 | 无需 Key | `Authorization: Bearer sk-xxx` |
| 流式 | `stream: true` → SSE | 相同 |
| 最大 token | `options.num_predict` | `max_tokens` |

### SSE 数据管线：一段文字的旅程

从生成到终端是一条管线：模型逐 token 生成 → HTTP chunked 传输（把响应
拆成小块逐块发送）→ `iter_lines()` 按行切 → 剥掉 `data: ` 前缀后
`json.loads` → 打印并累进 `full_content`。

三个必要条件缺一条就退化回非流式：请求里 `"stream": true`、客户端
`stream=True` 流式读取、打印时 `flush=True` 立即刷新。

两种结束标记本脚本都兼容：Ollama 用 `done: true`（附统计字段），OpenAI
用哨兵值 `[DONE]`（约定的特殊标记值）；解析失败的行（心跳注释行——保持
连接活跃的周期性消息）必须 `try/except` 后 `continue`，不能让整个流崩掉。

实测流式开销约 2%-5%，代价很小。流式结束后的 `full_content` 与非流式的
`message.content` 等价，可用 `basic` 与 `stream` 两模式互相验证。

### temperature：数学上就一个除数

对 logits（模型给每个候选词的原始分数）除以 T 再 softmax（把分数归一化
成概率分布的函数）：T<1 放大分数差异、分布变尖，T→0 等价 argmax（直接取
最高分词），输出可复现；T>1 压平分布，长尾词获得机会。

对照实验是控制变量的：固定 Prompt（含"必须包含'数据'和'模式'"的硬约束）、
system 消息、`num_predict=150`，唯一自变量是 `options.temperature`；
观测量是长度、关键词命中率、去重词数。

**任何结论都必须在这样的控制变量下得出**——24 实验的评估框架复用的
正是这套思路。

一个真实的坑：qwen3.8 是推理模型（会把思考过程单独输出的模型），响应里
可能同时有 `message.thinking` 和 `message.content`，且答案偶尔只在
thinking 里。

`extract_content()` 做三级兜底：`content` → `thinking` 的最后有效行 →
`response` 字段；全部落空时打印响应的字段名列表——这是调试陌生模型响应
结构的通用技巧。

## Pitfalls & Q&A

踩坑清单（每条 = 现象 + 原因 + 解法）：

- **`response.json()` 抛异常**：忘记写 `"stream": False` 时部分版本默认
  流式，返回的不是单个 JSON。解法：显式声明。
- **请求几十秒后超时**：本地模型首次加载（冷启动）慢。解法：`timeout`
  必须给且给足（脚本 60 秒）。
- **打字机效果时有时无**：`flush=True` 的表现受终端影响。解法：换 VS Code
  集成终端。
- **手写按字节切流的循环后 JSON 随机解析失败**：把一行 JSON 切成了两半。
  解法：用默认参数的 `iter_lines()`。
- **长度对比失去意义**：对照实验同时改了 `max_tokens`，两个变量一起变。
  解法：只留 temperature 一个自变量。

**Q1: 不用 SDK 直接调 LLM API，最小需要哪些字段？**

`model` + `messages`，其余（`options`/`stream`）都有默认值。

**Q2: temperature=0 能保证完全确定性吗？**

不能 100% 保证——GPU 浮点并行归约的顺序不定会引入微量非确定性，但工程上
足够当作"可复现"；严格复现需固定 seed（随机数种子）。

**Q3: 多轮对话的"记忆"是怎么实现的？**

把历史的 assistant 消息放回 messages 数组再发——API 本身无状态，记忆完全
由调用方维护（见 03 实验）。

**Q4: SSE 和 WebSocket 的区别？**

SSE 是单向服务器推送（基于 HTTP），WebSocket 全双工。流式回复只需要
服务器→客户端方向，SSE 更简单。
