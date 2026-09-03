"""
Agent HTTP 服务化 — FastAPI + SSE 流式 + 会话管理

前 27 个实验都是"跑一次脚本"。本篇把 Agent 变成常驻服务:
  POST /chat            {session_id, message} -> SSE 流式返回 (逐 token)
  GET  /sessions/{sid}  查看会话历史
  DELETE /sessions/{id} 清空会话

要点:
- SSE (Server-Sent Events): 逐 token 推送, 事件流与项目 02 同源
- 会话管理: 内存字典按 session_id 存 messages, 滑动窗口控制预算 (项目 17)
- --demo: 不连 Ollama, 用预置 token 流演示 SSE 协议 (离线可跑)

启动: python agent_server.py [--port 8001] [--demo]
测试: curl -N -X POST localhost:8001/chat -H 'Content-Type: application/json' \\
      -d '{"session_id": "s1", "message": "用一句话介绍 RAG"}'
"""

import json
import os
import sys
import time
import uuid

import requests
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"
SYSTEM_PROMPT = "你是部署在服务端的 Agent 助手，回答简洁准确。"
MAX_WINDOW_TOKENS = 400

app = FastAPI(title="hands-on-agentic-ai Agent Server", version="0.1.0")
SESSIONS = {}          # {session_id: [{"role", "content"}]}
DEMO = "--demo" in sys.argv


# ============================================================
# 会话管理 (滑动窗口, 复用项目 17 的思路)
# ============================================================

def estimate_tokens(text):
    cjk = sum(1 for ch in text if ord(ch) > 0x2E7F)
    return cjk + (len(text) - cjk) // 4


def get_session(sid):
    return SESSIONS.setdefault(sid, [])


def build_window(sid, user_msg, budget=MAX_WINDOW_TOKENS):
    history = get_session(sid)
    history.append({"role": "user", "content": user_msg})
    window, kept = [], []
    for msg in reversed(history):
        cost = estimate_tokens(msg["content"])
        if budget - cost < 0 and kept:
            break
        kept.insert(0, msg)
        budget -= cost
    window = [{"role": "system", "content": SYSTEM_PROMPT}] + kept
    dropped = len(history) - len(kept)
    return window, dropped


def commit_reply(sid, reply):
    get_session(sid).append({"role": "assistant", "content": reply})


# ============================================================
# 生成器: Ollama 流式 / Demo 流式
# ============================================================

def demo_stream(user_msg):
    """预置 token 流: 演示 SSE 协议, 不依赖 Ollama。"""
    for token in ["你好！", " 这是 ", "DEMO 模式。", " 服务端正在逐 token 推送 ",
                  "（SSE 事件流），", "真实模式由 ", " qwen3.8 生成。"]:
        time.sleep(0.08)
        yield token


# ============================================================
# 路由
# ============================================================

class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.post("/chat")
def chat(req: ChatRequest):
    def event_stream():
        sid = req.session_id
        window, dropped = build_window(sid, req.message)
        if dropped:
            yield f"data: {json.dumps({'event': 'window', 'dropped': dropped}, ensure_ascii=False)}\n\n"
        full = ""
        gen = demo_stream(req.message) if DEMO else ollama_stream_gen(window)
        try:
            for token in gen:
                full += token
                yield f"data: {json.dumps({'event': 'token', 'token': token}, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            pass   # 客户端断开: 保留已生成的部分回复
        commit_reply(sid, full)
        yield f"data: {json.dumps({'event': 'done', 'tokens': estimate_tokens(full)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def ollama_stream_gen(window):
    resp = requests.post(BASE_URL, json={
        "model": MODEL, "messages": window, "stream": True, "think": False,
    }, stream=True, timeout=180)
    resp.raise_for_status()
    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if line.startswith("data: "):
            line = line[6:]
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        chunk = data.get("message", {}).get("content", "")
        if chunk:
            yield chunk
        if data.get("done"):
            break


@app.get("/sessions/{sid}")
def get_history(sid: str):
    return {"session_id": sid, "messages": get_session(sid)}


@app.delete("/sessions/{sid}")
def clear_session(sid: str):
    SESSIONS.pop(sid, None)
    return {"cleared": sid}


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    port = 8001
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    print(f"Agent Server 启动: http://localhost:{port}  (demo={DEMO})")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
