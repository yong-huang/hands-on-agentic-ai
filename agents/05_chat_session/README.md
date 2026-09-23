# 05 · 消息历史与多轮对话：模型的"记忆"就是 messages 数组

> 只做一件事：**把累积的 messages 列表整体重发**——这一个动作就让模型
> "记住"了你说过的话。封装成 `ChatSession` 类，配一个可交互的命令行
> REPL，并守住历史一致性：失败的回复要回滚。

## What

多轮对话的本质：API 无状态，客户端把**全部历史**（system + 历轮问答 +
本轮输入）重新发一遍。一个状态机——等待输入 → 把 system + 全部历史 +
新输入组装成 messages → 等待 API 响应 → 回复并记录（历史 +2）→ 回到
等待；异常路径：回复无效则 `messages.pop()` 回滚，保证历史永远成对增长。

历史管理策略对比：

| 策略 | 做法 | 优点 | 代价 |
| :--- | :--- | :--- | :--- |
| 全量保留（本项目） | 原样重发全部历史 | 实现最简、信息无损 | token 随轮次线性增长 |
| 滑动窗口 | 只保留最近 N 轮 | 成本可控 | 早期信息丢失 |
| 摘要压缩 | 旧历史用 LLM 摘成一段 | 省 token 且保留要点 | 摘要有损、需额外调用 |

心智模型一句话：**会话状态 = messages 数组的长度；"记忆" = 每轮全量
重发。**

## Why

"模型有没有记忆？"是最常见的误解。理解"记忆 = 客户端重发历史"这一
点，你就明白了三件事：为什么上下文越长越贵、为什么对话太长会"忘记"
开头、为什么历史管理策略（滑动窗口/摘要压缩）会成为独立课题（项目 18
的伏笔）。

## How

```bash
cd agents/05_chat_session
python chat_session.py
# 🧑 你: 我叫张三，最喜欢吃火锅
# 🤖 助手: ...
# 🧑 你: 我刚才说我叫什么？最喜欢吃什么？
# 🤖 助手: 你叫张三，最喜欢吃火锅……     ← "记忆"生效
```

交互命令：`/hist` 看历史摘要与最近消息、`/clear` 清空重建会话、`/exit`
或 Ctrl+C/Ctrl+D 退出。脚本每轮结束打印 `📊 历史摘要`（总消息/用户/
助手/轮次），**你能亲眼看到 messages 数组每轮 +2**。

与项目 01 唯一的区别就一行：

```python
payload["messages"] = session.get_messages()   # 完整历史列表
```

模型没有任何服务端状态——它"记得"张三，是因为你的请求里就写着张三。

**历史一致性的守护：失败回滚。**流程是先 `add_user_message` 再调用 API；
如果回复为空或太短，必须 `session.messages.pop()` 把刚加的 user 消息弹掉。
否则历史里会留下一条"没有回答的问题"，下轮模型会困惑甚至开始自问自答。
**历史数组只允许成对的 user/assistant 追加**——这是会话管理的不变量。

**推理模型回复的清洗**：qwen3.8 的回复可能带思考痕迹、列表符号。
`extract_response()` 做了三层兜底：`content` → 从 `thinking` 里按
"Final Answer/所以/最终"等线索抽答案 → 退化为过滤编号后取最后两句。再用
正则剥掉行首的 `*`/`-`/`•`。**解析推理模型的输出是脏活，兜底链比单点
解析可靠得多。**

`ChatSession` 类核心：

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

## Deep Dive

**REPL 主循环的两个分支值得读**：回复有效（长度>5）才
`add_assistant_message`；否则打印失败提示并 `messages.pop()` 回滚。
Ctrl+C/Ctrl+D（EOFError）统一优雅退出——**管道输入时 EOFError 不处理
会死循环**，这是本篇修复过的真实 bug。

踩坑清单：

- `get_messages()` 返回浅拷贝，外部改消息内容会污染会话内部状态（代码
  注释里有自评）；
- 长对话后模型"忘记"开头的名字：未超限时注意力也会被长上下文稀释，且
  历史里的错误信息会持续影响后续回答——不是模型的错，是上下文工程问题。

## Q&A

**Q1: 滑动窗口截断要注意什么？**

永远保留 system 消息；最好成对截断（user+assistant 一起丢）；被截断的
信息如有长期价值应写入外部记忆（项目 17 的主题）。

**Q2: 会话状态应该放在哪里？**

短命会话在内存即可；跨进程/重启需要持久化——项目 10 的主题。
