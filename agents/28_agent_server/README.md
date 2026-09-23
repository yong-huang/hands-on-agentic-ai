# 28 · Agent HTTP 服务化：FastAPI + SSE + 会话管理

> 把 Agent 变成常驻服务：`POST /chat` 接收 `{session_id, message}`，以
> **SSE** 逐 token 流式返回；服务端按 session_id 维护多轮会话（滑动窗口控
> 预算），并提供会话的查询与清除接口。`--demo` 模式用预置 token 流演示 SSE
> 协议，离线可跑。

## What

服务端流程：客户端 POST `/chat`，服务端从会话存储取出该用户的滑动窗口
历史，组装后向 Ollama 发起流式请求，token 逐个包装成 SSE 事件推回；回复
完成后写回会话。`GET/DELETE /sessions/{id}` 提供会话的管理面。

SSE 流式协议：每个 token 包装成 `data: {"event": "token", ...}\n\n` 事件帧，
`done` 事件收尾。事件分三种：`token`（增量文本）、`window`（淘汰提示）、
`done`（统计）。客户端用 `curl -N` 或 EventSource 消费。

生产差距（诚实清单）：

| 本篇 | 生产系统 |
| :--- | :--- |
| 会话存内存字典 | Redis / 数据库（多实例共享） |
| 单进程 uvicorn | 多 worker + 负载均衡 |
| 无鉴权 | API Key / JWT + 限流 |
| Ollama 单实例 | 推理服务池 + 排队 |

心智模型一句话：**服务化 = 协议（SSE）+ 状态（会话存储）+ 上游（Ollama
流式）。**

## Why

脚本形态的 Agent 无法被别的系统使用：没有稳定接口、没有会话概念、没有
流式输出。服务化要解决三件事：**协议**（HTTP + SSE，任何语言可接入）、
**状态**（多用户的会话互相隔离）、**体验**（逐 token 推送而非整段等待）。
这三件事正是所有 Agent 产品（网页聊天、IDE 插件、IM 机器人）的服务端
骨架。

## How

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

**实测**：SSE 事件流逐 token 到达（`{"event": "token", "token": "…"}`），
流结束有 `done` 事件并附 token 统计；`/sessions/s1` 可见多轮历史；超预算
时下发 `window` 事件提示淘汰条数。

服务端核心——流式响应的函数必须是生成器：

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

## Deep Dive

**会话管理与客户端断开**：会话按 `session_id` 隔离，滑动窗口 400 token
预算。**实测细节**：客户端中途断开（如用户关页面）会触发生成器的
GeneratorExit——服务端捕获后**保留已生成的部分回复**入库，避免用户刷新后
丢失已看到的内容。

踩坑清单：

- `curl` 不加 `-N` 会缓冲整段，看不到逐 token；
- 客户端断开会把生成器杀掉——部分回复的落库策略要显式设计；
- 会话字典无淘汰策略会无限膨胀，生产加 TTL 或 LRU。

## Q&A

**Q1: SSE 与 WebSocket 在 Agent 服务里如何选型？**

请求-响应式对话用 SSE（单向推送、HTTP 原生、断线语义清晰）；需要服务端
主动推送/双向交互（任务进度、协作）才用 WebSocket。

**Q2: 会话状态为什么不能放内存？怎么迁移？**

内存字典无法多实例共享且重启即失；迁移到 Redis（TTL + 原子操作），服务
无状态化后才能水平扩展。

**Q3: 客户端断开后生成应该继续吗？**

看业务：聊天场景保留部分回复即可终止（省算力）；后台任务场景应转为异步
任务继续执行并把结果落存储。

**Q4: 首字延迟（TTFT）由什么决定？怎么优化？**

模型加载/排队 + prompt 长度；优化：流式、模型常驻、prompt 精简（项目
16/18 的压缩就是为 TTFT 服务）。
