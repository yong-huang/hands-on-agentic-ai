# 28 · Agent HTTP 服务化：FastAPI + SSE + 会话管理

> 把 Agent 变成常驻服务：`POST /chat` 接收 `{session_id, message}`，以 SSE 逐 token 流式返回；服务端按 session_id 维护多轮会话（滑动窗口控预算），并提供会话的查询与清除接口。读完本篇你能跑起一个流式 Agent 服务，理解协议、状态、上游三件事怎么拼成产品后端骨架。`--demo` 模式用预置 token 流演示 SSE 协议，离线可跑。

## Background

在没有服务化的做法里，Agent 是一个脚本：命令行里跑一次、打印结果、进程退出。别的系统（网页、插件、机器人框架）拿不到它的输出——它们说不了"命令行"这门语言。

痛点场景：想在网页里做一个聊天框，发现三个缺口。

没有稳定接口可供 HTTP 调用；没有会话概念，第二轮对话的历史无处安放；没有流式输出，用户盯着空白页面等十几秒后整段文字一次性砸出来。

Agent 服务化沿用 Web 后端的成熟方案来补齐这三个缺口：用 FastAPI（Python 的异步 Web 框架）暴露 HTTP 接口，用 SSE（Server-Sent Events，基于 HTTP 的单向服务器推送协议）做逐 token（模型输出的最小文本单位）推送。

服务端存储则按 `session_id` 隔离多轮历史。

这三件事正是所有 Agent 产品（网页聊天、IDE 插件、IM 机器人）的服务端骨架。

## What

Agent 服务化是把命令行脚本形态的 Agent 封装成常驻 HTTP 服务的技术。它要解决三件事：**协议**（HTTP + SSE，任何语言可接入）、**状态**（多用户的会话互相隔离）、**体验**（逐 token 推送而非整段等待）。

服务端流程：客户端 POST `/chat`，服务端从会话存储取出该用户的滑动窗口（只保留最近若干条历史、超预算淘汰最旧内容）历史，组装后向 Ollama（本地运行大模型的工具）发起流式请求，token（模型输出的最小文本单位）逐个包装成 SSE 事件推回；回复完成后写回会话。

`GET/DELETE /sessions/{id}` 提供会话的管理接口。

可以把整个服务想象成一家餐厅：SSE 是服务员把菜一道道端上桌（而不是等全桌做齐一次端上来），会话存储是记住每桌点了什么的账本，Ollama 是后厨。但和餐厅不同的是：这里的账本只保留最近约 400 token 的对话，更早的记录会被主动淘汰，而不是永久留存。

SSE 的流式约定：每个 token 包装成 `data: {"event": "token", ...}\n\n` 事件帧，`done` 事件收尾。

事件分三种：`token`（增量文本）、`window`（淘汰提示）、`done`（统计）。

生产差距（诚实清单）：

| 本篇 | 生产系统 |
| :--- | :--- |
| 会话存内存字典 | Redis / 数据库（多实例共享） |
| 单进程 uvicorn | 多 worker + 负载均衡 |
| 无鉴权 | API Key / JWT（带签名的身份令牌）+ 限流 |
| Ollama 单实例 | 推理服务池 + 排队 |

心智模型一句话：**服务化 = 协议（SSE）+ 状态（会话存储）+ 上游（Ollama 流式）。**

## When to Use

适合在三类时候选它：

- 给面向人的产品做后端时：网页聊天、IDE 插件、IM 机器人都需要一个 HTTP 入口和逐 token 的输出体验。
- 多用户多轮会话需要隔离时：不同 `session_id` 的历史互不可见，由服务端统一管理预算与清除。
- 输出较长、需要改善体感时：流式推送让用户在首字出现后就有内容可读，而不是干等整段。

不要用的三种情况：

- 单人本地自用：CLI 脚本跑一次就够，服务化只增加复杂度。
- 无多轮状态的单次调用：一个普通的整段返回 HTTP 接口即可，不必引入 SSE。
- 需要服务端主动、双向地推消息：选 WebSocket（见下表）。

| 方案 | 差异 | 什么时候选它 |
| :--- | :--- | :--- |
| CLI 脚本 | 一次一跑，进程退出 | 本地自用、开发调试 |
| 普通 HTTP 接口（整段返回） | 有接口，但无流式、会话需自建 | 内部系统的一次性调用 |
| FastAPI + SSE 服务（本篇） | 流式推送 + 会话管理 | 聊天类产品的后端 |
| WebSocket 服务 | 双向长连接 | 任务进度、协作等双向交互场景 |

## Quick Start

前置条件：Python 3 环境，`pip install fastapi uvicorn requests`（FastAPI 是 Web 框架，uvicorn 是运行它的服务器，requests 供脚本调用上游模型——导入在入口，`--demo` 也需要）。

真实模式需要本机 Ollama 可用，`--demo` 模式离线即可。

```bash
pip install fastapi uvicorn requests
cd agents/28_agent_server
python agent_server.py --demo --port 8011 &   # 离线演示 SSE 协议
python agent_server.py --port 8011 &                 # 真实模式（需 Ollama）
# 测试 (另开终端):
curl -N -X POST localhost:8011/chat -H 'Content-Type: application/json' \
     -d '{"session_id": "s1", "message": "用一句话介绍 RAG"}'
curl localhost:8011/sessions/s1                      # 查看会话历史
```

`curl -N` 是禁用 curl 缓冲的参数——不加它就看不到逐 token 效果（见 Pitfalls 第一条）。

诚实预期（实测）：SSE 事件流逐 token 到达（`{"event": "token", "token": "…"}`），流结束有 `done` 事件并附 token 统计；`/sessions/s1` 可见多轮历史；超预算时下发 `window` 事件提示淘汰条数。

demo 模式返回预置 token 流，节奏与真实流一致。

## How It Works

服务端核心——流式响应的函数必须是生成器（用 `yield` 逐个产出值、而不是 `return` 一次性返回的函数）：

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

`chat` 把 `event_stream` 这个生成器交给 `StreamingResponse`（FastAPI 提供的流式响应类型，边产出边发送）。

每 `yield` 一次，就有一个 SSE 事件帧发往客户端——你在 Quick Start 看到的逐 token 到达，就对应循环里的每一次 `yield`。

三个关键点与会话机制：

- `build_window` 先取该 `session_id` 的历史、按 400 token 预算滑动淘汰，淘汰条数通过 `window` 事件提前告知客户端；会话按 `session_id` 隔离，互不可见。
- 回复边生成边累加进 `full`，结束后 `commit_reply` 写回会话——`done` 事件里的统计就来自 `estimate_tokens(full)`。
- 客户端中途断开（如用户关页面）会触发生成器的 `GeneratorExit`（Python 注入生成器、强制其退出的异常信号），服务端捕获后保留已生成的部分回复入库，用户刷新后不会丢失已看到的内容。

## Pitfalls & Q&A

踩坑清单（现象 / 原因 / 解法）：

- 看不到逐 token 输出。现象：`curl` 等十几秒后一次性打印全部内容。原因：curl 默认缓冲收到的响应。解法：加 `-N` 禁用缓冲。
- 刷新后回复丢失。现象：用户中途关页，重开会话发现刚才的回复不在历史里。原因：客户端断开会把生成器杀掉，部分回复没落库。解法：像上文那样捕获 `GeneratorExit` 后 `commit_reply`——落库策略必须显式设计。
- 服务跑久了内存涨。现象：会话字典越来越大。原因：内存字典没有淘汰策略，会话只增不减。解法：加 TTL（到期自动删除的时间限制）或 LRU（淘汰最久未使用条目的策略）。

**Q1: SSE 与 WebSocket 在 Agent 服务里如何选型？**

请求-响应式对话用 SSE（单向推送、HTTP 原生、断线语义清晰）；需要服务端主动推送或双向交互（任务进度、协作）才用 WebSocket。

**Q2: 会话状态为什么不能放内存？怎么迁移？**

内存字典无法多实例共享且重启即失；迁移到 Redis（支持多实例共享的内存键值数据库，自带 TTL 与原子操作（执行中途不会被打断的操作）），服务无状态化后才能水平扩展（靠加机器分摊负载）。

**Q3: 客户端断开后生成应该继续吗？**

看业务：聊天场景保留部分回复即可终止（省算力）；后台任务场景应转为异步任务（交给后台单独执行）继续跑完并把结果落存储。

**Q4: 首字延迟（TTFT，从发出请求到第一个字出现的时间）由什么决定？**

模型加载/排队 + prompt 长度；优化：流式、模型常驻（启动时加载、长期驻留内存）、prompt 精简（16/18 实验的上下文压缩就是为 TTFT 服务）。
