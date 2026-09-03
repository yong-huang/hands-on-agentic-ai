# 28 · Agent HTTP 服务化：FastAPI + SSE + 会话管理

> 前 27 个实验都是"跑一次脚本"。本篇把 Agent 变成常驻服务：`POST /chat` 接收
> `{session_id, message}`，以 **SSE** 逐 token 流式返回；服务端按 session_id
> 维护多轮会话（滑动窗口控预算），并提供会话的查询与清除接口。`--demo` 模式
> 用预置 token 流演示 SSE 协议，离线可跑。

## 1. 为什么需要它

脚本形态的 Agent 无法被别的系统使用：没有稳定接口、没有会话概念、没有流式
输出。服务化要解决三件事：**协议**（HTTP + SSE，任何语言可接入）、**状态**
（多用户的会话互相隔离）、**体验**（逐 token 推送而非整段等待）。这三件事
正是所有 Agent 产品（网页聊天、IDE 插件、IM 机器人）的服务端骨架。

## 2. 总览：核心机制一图看懂

![Agent 服务化架构](images/agent_server.architecture.svg)

**怎么看这张图**：客户端 POST `/chat`，服务端从会话存储取出该用户的滑动窗口
历史，组装后向 Ollama 发起流式请求，token 逐个包装成 SSE 事件推回；回复
完成后写回会话。`GET/DELETE /sessions/{id}` 提供会话的管理面。

心智模型一句话：**服务化 = 协议（SSE）+ 状态（会话存储）+ 上游（Ollama 流式）。**

🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/28_agent_server/images/agent_server.architecture.html)（或本地打开 [`images/agent_server.architecture.html`](images/agent_server.architecture.html)）。

## 3. 快速开始

```bash
pip install fastapi uvicorn
cd agents/28_agent_server
python agent_server_server.py --demo --port 8011 &   # 离线演示 SSE 协议
python agent_server.py --port 8011 &                 # 真实模式（需 Ollama）
# 测试 (另开终端):
curl -N -X POST localhost:8011/chat -H 'Content-Type: application/json' \
     -d '{"session_id": "s1", "message": "用一句话介绍 RAG"}'
curl localhost:8011/sessions/s1                      # 查看会话历史
```

**实测**：SSE 事件流逐 token 到达（`{"event": "token", "token": "…"}`），流
结束有 `done` 事件并附 token 统计；`/sessions/s1` 可见多轮历史；超预算时
下发 `window` 事件提示淘汰条数。

## 4. 核心概念

### 4.1 SSE 流式协议

每个 token 包装成 `data: {"event": "token", ...}\n\n` 事件帧，`done` 事件
收尾。事件分三种：`token`（增量文本）、`window`（淘汰提示）、`done`（统计）。
客户端用 `curl -N` 或 EventSource 消费。流式把首字延迟从"整段生成完"降到
"第一个 token 生成完"（项目 02 的服务端版）。

### 4.2 会话管理与客户端断开

会话按 `session_id` 隔离，滑动窗口 400 token 预算。**实测细节**：客户端中途
断开（如用户关页面）会触发生成器的 GeneratorExit——服务端捕获后**保留已生成
的部分回复**入库，避免用户刷新后丢失已看到的内容。

### 4.3 生产差距（诚实清单）

| 本篇 | 生产系统 |
| :--- | :--- |
| 会话存内存字典 | Redis / 数据库（多实例共享） |
| 单进程 uvicorn | 多 worker + 负载均衡 |
| 无鉴权 | API Key / JWT + 限流 |
| Ollama 单实例 | 推理服务池 + 排队 |

## 5. 代码关键部分

```python
@app.post("/chat")
def chat(req: ChatRequest):
    def event_stream():
        sid = req.session_id
        window, dropped = build_window(sid, req.message)
        if dropped:
            yield f"data: {json.dumps({'event': 'window', 'dropped': dropped})}\n\n"
        full = ""
        gen = demo_stream(req.message) if DEMO else ollama_stream_gen(window)
        try:
            for token in gen:
                full += token
                yield f"data: {json.dumps({'event': 'token', 'token': token})}\n\n"
        except GeneratorExit:
            pass                       # 客户端断开: 保留部分回复
        commit_reply(sid, full)
        yield f"data: {json.dumps({'event': 'done', 'tokens': estimate_tokens(full)})}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

坑清单：

- 流式响应的函数必须是生成器；`curl` 不加 `-N` 会缓冲整段，看不到逐 token；
- 客户端断开会把生成器杀掉——部分回复的落库策略要显式设计；
- 会话字典无淘汰策略会无限膨胀，生产加 TTL 或 LRU。

## 6. 文件结构

```
28_agent_server/
├── README.md                            # 本篇教程
├── agent_server.py                      # 主脚本（约 180 行）：FastAPI + SSE + 会话
└── images/
    ├── agent_server.architecture.json   # 图源：architecture 类型（服务化组件图）
    ├── agent_server.architecture.html   # 交互版架构图
    └── agent_server.architecture.svg    # 双主题矢量图
```

## 7. 面试要点

- **Q: SSE 与 WebSocket 在 Agent 服务里如何选型？**
  A: 请求-响应式对话用 SSE（单向推送、HTTP 原生、断线语义清晰）；需要服务端
  主动推送/双向交互（任务进度、协作）才用 WebSocket。
- **Q: 会话状态为什么不能放内存？怎么迁移？**
  A: 内存字典无法多实例共享且重启即失；迁移到 Redis（TTL + 原子操作），
  服务无状态化后才能水平扩展。
- **Q: 客户端断开后生成应该继续吗？**
  A: 看业务：聊天场景保留部分回复即可终止（省算力）；后台任务场景应转为
  异步任务继续执行并把结果落存储。
- **Q: 流式接口的安全考量有什么？**
  A: 鉴权（SSE 事件流也要校验）、限流（token 生成是昂贵资源）、输出过滤
  （项目 29 的内容过滤应挂在流式出口）。
- **Q: 首字延迟（TTFT）由什么决定？怎么优化？**
  A: 模型加载/排队 + prompt 长度；优化：流式、模型常驻、prompt 精简
  （项目 16/18 的压缩就是为 TTFT 服务）。

## 8. 总结

协议（SSE）、状态（会话）、上游（流式 Ollama）三件齐备，Agent 从脚本变成
可被任何客户端消费的常驻服务。但对外开放的第一天就会遇到恶意输入——下一篇
给服务装上安全防护：注入检测、白名单与输出过滤。
