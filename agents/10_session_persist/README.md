# 10 · 会话持久化：保存 → 退出 → 恢复 → 接着聊

> `AgentSession` 把消息历史、工具调用审计、元信息三层状态转成 JSON 写入
> 磁盘，重启后按会话 ID 恢复、从断点继续对话，并配 `/save /resume
> /list /delete` 一整套会话管理命令。读完本篇，你能让任何智能体对话
> 活过进程重启，并说清"会话到底由哪些状态构成"。

## Background

在持久化出现之前，对话状态只活在内存里：对话历史是一个 Python 列表变量，工具调用过程散落在打印输出里，进程一退出就全部蒸发。最朴素的补救是把整个对话追加到一个文本文件里，但工具调了哪些工具、用的什么模型这类结构化信息混在纯文本中，事后既查不了也恢复不回来。

三个真实场景会撞上这堵墙。用户第二天回来想接着聊，服务重启后上下文全丢，只能从头自我介绍；客服要回溯"当时智能体到底调了哪些工具、给用户看了什么"，日志里找不到；长任务跑到第 20 步进程崩溃，一切从头再来。

解决思路是把这些运行时状态保存成结构化文件、按会话 ID 存取。LangGraph 的 checkpointer、各类聊天产品的历史记录，做的都是这件事。本实验用纯标准库把它实现出来。

## What

会话持久化（persistence，让数据在程序退出后依然存在的机制）的定义：**把一次会话（session，一段连续对话及其全部状态）在运行过程中持续保存为结构化数据，重启后可无损恢复并继续对话。**

一个会话由三层状态构成：

| 层 | 字段 | 用途 |
| :--- | :--- | :--- |
| 对话历史 | `messages` | 发给 API（程序访问大模型服务的接口）的完整上下文 |
| 审计日志 | `tool_calls` | 每次工具调用的记录（Observation——工具返回的结果——记在这里） |
| 元信息 | `metadata` + `session_id/created_at/updated_at` | 模型名、步数、索引排序 |

可以把持久化想象成游戏存档：保存时把角色状态、背包、进度写进存档文件，读档后从原进度继续。但和游戏存档不同的是，这里的会话不是关键节点才手动存，而是每跑一步就同步写入，存的内容还包括"每次工具调用"这类审计记录。

心智模型一句话：**持久化 = 决定哪些状态构成"会话"，再把它们无损地搬进 JSON（键值对形式的文本格式）。**

## When to Use

这节回答：什么样的智能体需要会话持久化，什么样的不需要。

典型场景：

- **做多轮助手或客服服务时**：用户跨天、跨次启动回来要接着聊，上下文
  必须活过进程重启；
- **长任务需要断点续跑时**：跑到一半崩溃或主动停机，重启后从最近一步
  继续，而不是整轮重来；
- **有审计与合规要求时**：事后要回答"智能体当时调了什么工具、返回了
  什么"，审计日志必须完整落盘。

何时不用：一次性无状态脚本（每次调用相互独立、不需要历史）不需要持久化，内存态即可；纯演示用的短命程序也不必引入文件读写。

同类方案对比：

| 方案 | 差异 | 什么时候选它 |
| :--- | :--- | :--- |
| 纯内存（不持久化） | 重启即丢，无任何读写成本 | 一次性脚本、无状态接口 |
| JSON 文件（本实验） | 零依赖、人能直接读改、按会话 ID 一文件 | 单机、会话量小、原型与学习 |
| SQLite 等数据库 | 并发安全、可按条件查询 | 多会话并存、需要检索统计 |
| LangGraph checkpointer | 框架自带的检查点组件，按图状态存取 | 已用 LangGraph 的生产系统 |

## Quick Start

前置条件：本地装有 Python 3；`--demo` 为离线演示，不调用外部接口；交互模式需要本地 Ollama 已启动且已执行 ollama pull qwen3.8:latest（无需 API Key）。

```bash
cd agents/10_session_persist
python session_persist.py --demo     # 离线演示：保存→恢复→继续→再保存（含 assert 校验）
python session_persist.py            # 交互 CLI（命令行界面）
# You: What is Python?
# ... /save
# 会话已保存: sess_20260902_153045
# （Ctrl+C 退出后重新运行）
# /resume sess_20260902_153045
# 已恢复会话，最近 4 条消息: ...
```

交互模式的诚实预期：对话中输入 `/save` 得到一个 `sess_` 加时间戳的会话
ID；Ctrl+C 退出再启动，输入 `/resume 会话ID` 后模型能接着上文回答，
无需重新交代背景。

`--demo` 做三阶段验证：①固定 ID 的会话跑两轮并保存（打印 JSON 前 15 行）；
②重新 `load` 后用 3 个 `assert`（Python 的断言语句，条件不成立立即报错）
逐字段比对 messages/tool_calls；③恢复的会话继续第三轮对话并再次保存，
最后清理演示文件。

看到三个 assert 全部通过，说明恢复是无损的。

## How It Works

### 数据流：一步一写，落盘即恢复

`agent_step()` 每跑一步就同步写入内存态 `AgentSession`（tool_calls 审计
是并行支路）→ `to_dict+save()` 序列化（把内存对象转成可存储文本的过程）
→ `sessions/*.json` 落盘。

重启后 `from_dict/load()` 逐字段恢复、继续对话。会话文件按 `session_id`
（时间戳生成）命名，`list_sessions()` 扫描目录重建索引。你在 `--demo`
阶段②看到的逐字段比对通过，正是这条链路无损的直接证据。

save/load 的实现只有两个方法，值得注意的点写在注释外：`save` 每次写入
都刷新 `updated_at`，供索引排序；`load` 是类方法，从文件读出字典后逐
字段还原对象：

```python
class AgentSession:
    def save(self, directory=SESSIONS_DIR):
        os.makedirs(directory, exist_ok=True)
        self.updated_at = datetime.now().isoformat()
        path = os.path.join(directory, f"{self.session_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return path

    @classmethod
    def load(cls, session_id, directory=SESSIONS_DIR):
        with open(os.path.join(directory, f"{session_id}.json"), encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
```

### 角色语义的分离：记录 ≠ 发送

`add_observation()` 把工具结果写进 `tool_calls` 审计；但 ReAct 循环
（Reason + Act，"走一步看一步"的对话范式）发请求时，把它转成
`{"role": "user", "content": "Observation: ..."}`。

存储格式与协议格式解耦——哪天换 Function Calling 协议（模型用结构化请求调用函数的官方
协议，11 实验的主题），只需改发送侧，历史数据一个字节不动。

分层的原因也在这里：发给模型的要最小化（省 token，模型按文本长度计费
计长），留给人的要完整（可回溯）。Observation 就是典型——它在审计里是
工具调用记录，发给 API 时却要以 user 角色伪装。

### 断点续跑：每步同步写，而不是跑完一轮才写

`agent_step()` 在循环内每一步都同步写会话（add_assistant / add_observation
/ add_user）。这样进程在任何一步死掉，重启后都能从"半轮"恢复——最多
丢一步，不丢整轮。

### 恢复后的完整性验证

`--demo` 用 `assert` 逐字段比对恢复前后的 messages 长度与内容、tool_calls
数量。生产上等价的做法是给 JSON 加版本号与校验和（对数据算出的摘要值，
用来检测数据是否被改动）。**没有验证的恢复只是"看起来恢复了"。**

## Pitfalls & Q&A

踩坑清单，每条按"现象 → 原因 → 解法"：

- **现象：打开会话文件满屏 `\uXXXX`，中文不可读且文件膨胀。** 原因：
  `json.dump` 默认转义非 ASCII 字符。解法：加 `ensure_ascii=False`。
- **现象：进程崩溃后丢的是最近一整轮对话。** 原因：只在退出时保存，写
  盘频率太低。解法：`agent_step()` 每步同步写，机制见 How It Works 的
  "断点续跑"小节。
- **现象：恢复后模型回答风格突变、像换了个人。** 原因：续聊用的模型与
  会话记录时的模型不同，上下文风格断层。解法：恢复后把
  `metadata["model"]` 与当前模型比对，不一致时给出提示。

深入问答：

**Q: 会话文件会不会无限膨胀？**

会。生产要做轮转/归档/摘要压缩（轮转指旧文件移位归存、新文件顶上；摘
要压缩指把长历史压成一段摘要，18 实验的主题），并限制单会话大小。恢复
正确性如何验证，见 How It Works 的"恢复后的完整性验证"小节。
