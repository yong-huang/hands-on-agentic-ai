# 05 · 消息历史与多轮对话：模型的"记忆"就是 messages 数组

> 项目 01-04 每次调用都是"一问一答就失忆"。本篇只做一件事：**把累积的
> messages 列表整体重发**——这一个动作就让模型"记住"了你说过的话。我们把它
> 封装成 `ChatSession` 类，配一个可交互的命令行 REPL，并守住历史一致性：
> 失败的回复要回滚。

## 1. 为什么需要它

"模型有没有记忆？"是新手最常见的误解。API 是无状态的：所谓多轮对话，就是
客户端把**全部历史**（system + 历轮问答 + 本轮输入）重新发一遍。理解这一点
你就明白了三件事：为什么上下文越长越贵、为什么对话太长会"忘记"开头、为什么
历史管理策略（滑动窗口/摘要压缩）会成为独立课题（项目 18 的伏笔）。

## 2. 总览：核心机制一图看懂

![多轮对话一轮的生命周期](images/chat_turn.lifecycle.svg)

**怎么看这张图**：一个状态机——等待输入 → 把 system + 全部历史 + 新输入组装
成 messages → 等待 API 响应 → 回复并记录（历史 +2）→ 回到等待。异常路径：
回复无效则 `messages.pop()` 回滚，保证历史永远成对增长。

心智模型一句话：**会话状态 = messages 数组的长度；"记忆" = 每轮全量重发。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/05_chat_session/images/chat_turn.lifecycle.html)（或本地打开 [`images/chat_turn.lifecycle.html`](images/chat_turn.lifecycle.html)）。

## 3. 快速开始

```bash
cd agents/05_chat_session
python chat_session.py
# 🧑 你: 我叫张三，最喜欢吃火锅
# 🤖 助手: ...
# 🧑 你: 我刚才说我叫什么？最喜欢吃什么？
# 🤖 助手: 你叫张三，最喜欢吃火锅……     ← "记忆"生效
```

交互命令：`/hist` 看历史摘要与最近消息、`/clear` 清空重建会话、`/exit` 或
Ctrl+C/Ctrl+D 退出。脚本每轮结束打印 `📊 历史摘要`（总消息/用户/助手/轮次），
**你能亲眼看到 messages 数组每轮 +2**。

## 4. 核心概念

### 4.1 多轮对话的本质：一行代码

```python
payload["messages"] = session.get_messages()   # 与项目 01 唯一的区别
```

项目 01 每次只发 system + 本轮 user；这里换成**完整历史列表**。模型没有
任何服务端状态——它"记得"张三，是因为你的请求里就写着张三。

### 4.2 历史一致性的守护：失败回滚

流程是先 `add_user_message` 再调用 API；如果回复为空或太短，必须
`session.messages.pop()` 把刚加的 user 消息弹掉。否则历史里会留下一条
"没有回答的问题"，下轮模型会困惑甚至开始自问自答。**历史数组只允许
成对的 user/assistant 追加**——这是会话管理的不变量。

### 4.3 历史管理策略对比

| 策略 | 做法 | 优点 | 代价 |
| :--- | :--- | :--- | :--- |
| 全量保留（本项目） | 原样重发全部历史 | 实现最简、信息无损 | token 随轮次线性增长 |
| 滑动窗口 | 只保留最近 N 轮 | 成本可控 | 早期信息丢失 |
| 摘要压缩 | 旧历史用 LLM 摘成一段 | 省 token 且保留要点 | 摘要有损、需额外调用 |

长对话后模型"忘记"开头的名字？不是模型的问题，是你早已把开头发给过它——
但注意力会稀释。**易错点**：`get_messages()` 返回浅拷贝，外部改消息内容
会污染会话内部状态（代码注释里有自评）。

### 4.4 推理模型回复的清洗

qwen3.8 的回复可能带思考痕迹、列表符号。`extract_response()` 做了三层兜底：
`content` → 从 `thinking` 里按"Final Answer/所以/最终"等线索抽答案 → 退化
为过滤编号后取最后两句。再用正则剥掉行首的 `*`/`-`/`•`。**解析推理模型的
输出是脏活，兜底链比单点解析可靠得多。**

## 5. 代码关键部分

```python
class ChatSession:
    def __init__(self, system_prompt=None):
        self.messages = [{"role": "system", "content": system_prompt}] if system_prompt else []
        self.conversation_count = 0

    def add_user_message(self, content):
        self.messages.append({"role": "user", "content": content})
        self.conversation_count += 1

    def add_assistant_message(self, content):
        self.messages.append({"role": "assistant", "content": content})
```

REPL 主循环的两个分支值得读：回复有效（长度>5）才 `add_assistant_message`；
否则打印失败提示并 `messages.pop()` 回滚。Ctrl+C/Ctrl+D（EOFError）统一优雅
退出——**管道输入时 EOFError 不处理会死循环**，这是本篇修复过的真实 bug。

## 6. 文件结构

```
05_chat_session/
├── README.md                     # 本篇教程
├── chat_session.py               # 主脚本（约 220 行）：ChatSession 类 + REPL
└── images/
    ├── chat_turn.lifecycle.json  # 图源：lifecycle 类型（会话轮次状态机）
    ├── chat_turn.lifecycle.html  # 交互版架构图
    └── chat_turn.lifecycle.svg   # 双主题矢量图
```

## 7. 面试要点

- **Q: LLM API 是如何实现"多轮对话"的？**
  A: API 无状态。客户端把完整对话历史（含历轮 assistant 消息）重新发送，
  模型基于全量上下文生成回复。
- **Q: 为什么对话轮数多了模型会"忘事"？**
  A: 上下文窗口有上限，超限必须截断；未超限时注意力也会被长上下文稀释，
  且历史里的错误信息会持续影响后续回答。
- **Q: 失败的对话轮次要怎么处理？**
  A: 回滚历史（把刚追加的 user 消息弹出），保持 user/assistant 成对出现的
  不变量；否则历史里会留下悬空问题污染后续上下文。
- **Q: 滑动窗口截断要注意什么？**
  A: 永远保留 system 消息；最好成对截断（user+assistant 一起丢）；被截断
  的信息如有长期价值应写入外部记忆（项目 17 的主题）。
- **Q: 会话状态应该放在哪里？**
  A: 短命会话在内存即可；跨进程/重启需要持久化——这正是下一篇的主题。

## 8. 总结

多轮对话 = 全量重发 messages，"记忆"是客户端的义务。但内存里的会话一退出
就没了——下一篇给会话加 JSON 持久化：保存、恢复、接着聊。
