# 10 · 会话持久化：保存 → 退出 → 恢复 → 接着聊

> 项目 05 的对话历史活在内存里，进程一退就清零。本篇给 Agent 会话加上
> 完整生命周期：`AgentSession` 把 messages、工具调用审计、元信息三层状态
> 序列化成 JSON 落盘，重启后按会话 ID 恢复，从断点继续对话——并提供
> `/save /resume /list /delete` 一整套会话管理命令。

## 1. 为什么需要它

真实 Agent 服务的会话必须活过进程重启：用户第二天回来要接着聊、客服工单要
回溯历史、长任务中断后要断点续跑。持久化的本质是**把运行时状态变成可序列化
的数据**——这个动作逼你想清楚"会话到底由哪些状态构成"，而这个问题的答案
（messages + tool_calls + metadata 三层）在任何 Agent 框架里都成立。

## 2. 总览：核心机制一图看懂

![会话状态持久化数据流](images/session_state_flow.dataflow.svg)

**怎么看这张图**：从左到右——`agent_step()` 每跑一步就同步写入内存态
`AgentSession`（注意 tool_calls 审计是并行支路）→ `to_dict+save()` 序列化 →
`sessions/*.json` 落盘 → 重启后 `from_dict/load()` 逐字段恢复 → 继续对话。

心智模型一句话：**持久化 = 决定哪些状态构成"会话"，再把它们无损地搬进 JSON。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/10_session_persist/images/session_state_flow.dataflow.html)（或本地打开 [`images/session_state_flow.dataflow.html`](images/session_state_flow.dataflow.html)）。

## 3. 快速开始

```bash
cd agents/10_session_persist
python session_persist.py --demo     # 离线演示：保存→恢复→继续→再保存（含 assert 校验）
python session_persist.py            # 交互 CLI
# You: What is Python?
# ... /save
# 会话已保存: sess_20260902_153045
# （Ctrl+C 退出后重新运行）
# /resume sess_20260902_153045
# 已恢复会话，最近 4 条消息: ...
```

`--demo` 做三阶段验证：①固定 ID 的会话跑两轮并保存（打印 JSON 前 15 行）；
②重新 `load` 后用 3 个 `assert` 逐字段比对 messages/tool_calls；③恢复的
会话继续第三轮对话并再次保存，最后清理演示文件。

## 4. 核心概念

### 4.1 会话状态的三层构成

| 层 | 字段 | 用途 |
| :--- | :--- | :--- |
| 对话历史 | `messages` | 发给 API 的完整上下文 |
| 审计日志 | `tool_calls` | 每次工具调用的记录（Observation 记在这里） |
| 元信息 | `metadata` + `session_id/created_at/updated_at` | 模型名、步数、索引排序 |

**为什么审计和历史分开放**：发给模型的要最小化（省 token），留给人的要
完整（可回溯）。Observation 就是典型——它在审计里是工具调用记录，发给
API 时却要以 user 角色伪装（见 4.2）。

### 4.2 角色语义的分离：记录 ≠ 发送

`add_observation()` 把工具结果写进 `tool_calls` 审计，但 ReAct 循环发请求时
把它转成 `{"role": "user", "content": "Observation: ..."}`。**存储格式与
协议格式解耦**——哪天换 Function Calling 协议，只需改发送侧，历史数据不动。

### 4.3 断点续跑的正确姿势

`agent_step()` 在循环内**每一步都同步写会话**（add_assistant /
add_observation / add_user），而不是跑完一轮才写。这样进程在任何一步死掉，
重启后都能从"半轮"恢复——最多丢一步，不丢整轮。**易错点**：只在退出时保存
的写法，崩溃时丢的正是你最需要的那段。

### 4.4 恢复后的完整性验证

`--demo` 用 `assert` 逐字段比对恢复前后的 messages 长度与内容、tool_calls
数量。生产上等价的做法是给 JSON 加版本号与校验和。**没有验证的恢复只是
"看起来恢复了"。**

## 5. 代码关键部分

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

坑清单：

- `json.dump` 必须 `ensure_ascii=False`，否则中文全变 `\uXXXX` 且文件膨胀；
- 会话文件按 `session_id` 命名（时间戳生成），`list_sessions()` 扫目录重建索引；
- 恢复后记得把 `metadata["model"]` 与当前模型比对——跨模型续聊上下文风格会断层。

## 6. 文件结构

```
10_session_persist/
├── README.md                          # 本篇教程
├── session_persist.py                 # 主脚本（约 465 行）：AgentSession + CLI + demo
├── sessions/                          # 会话 JSON 落盘目录（运行时生成）
└── images/
    ├── session_state_flow.dataflow.json  # 图源：dataflow 类型（状态→磁盘→恢复）
    ├── session_state_flow.dataflow.html  # 交互版架构图
    └── session_state_flow.dataflow.svg   # 双主题矢量图
```

## 7. 面试要点

- **Q: 一个 Agent 会话应该持久化哪些状态？**
  A: 对话历史（发模型的）、工具调用审计（可回溯的）、元信息（模型/步数/
  时间戳）。三者用途不同，不能混成一坨。
- **Q: 什么时候写盘？**
  A: 关键步同步写（每步/每轮），而非进程退出时。持久化的意义就是在崩溃
  后少丢状态。
- **Q: Observation 存储和发送为什么不同？**
  A: 存储面向审计要完整，发送面向协议要合法（user 角色）且精简。存储格式
  与协议格式解耦，换协议不动数据。
- **Q: 会话文件会不会无限膨胀？**
  A: 会。生产要做轮转/归档/摘要压缩（长历史压成摘要段落，项目 18 的主题），
  并限制单会话大小。
- **Q: 如何验证恢复的正确性？**
  A: 序列化加版本号与校验和；恢复后逐字段断言（messages 长度、末条内容、
  tool_calls 计数），demo 里的三个 assert 就是这个思路。

## 8. 总结

会话持久化 = 三层状态建模 + 同步落盘 + 恢复校验。至此 Agent 已经"活得过"
一次进程重启。但它的工具仍是手写循环里的本地函数——下一篇换上协议级的
Function Calling，让模型用 JSON 直接"点菜"。
