"""mh.llm — mh 包共用 LLM 客户端 (Ollama 原生 /api/chat, 支持 function calling)

约定与 interview/llm.py 一致: LLM_BASE_URL / LLM_MODEL / LLM_API_KEY 环境变量,
默认 http://localhost:11434 + qwen3.8:latest, 免 Key。
返回完整 message dict(含 content / tool_calls), 供 loop 使用。
"""

import json
import os
import re
import urllib.request

BASE = os.environ.get("LLM_BASE_URL", "http://localhost:11434")
MODEL = os.environ.get("LLM_MODEL", "qwen3.8:latest")
API_KEY = os.environ.get("LLM_API_KEY", "ollama")
NO_PROXY_FALLBACK = True  # 本地服务不走系统代理(01 实验踩过的坑)


def chat(messages, tools=None, temperature=0.0, num_predict=1200, timeout=300,
         think=False):
    """调用 Ollama /api/chat。tools 传 JSON Schema 列表即启用 function calling。

    think=False 服务端关闭混合推理模型的思考(qwen3 系)——10 实验发现长任务
    会触发过度思考, 1200 token 全进 thinking 字段导致 content/tool_calls 双空,
    /no_think 提示词拦不住, 只有服务端参数可靠。
    返回 assistant message dict: {"role","content","tool_calls"?}。
    """
    payload = {"model": MODEL, "messages": messages, "stream": False,
               "think": think,
               "options": {"temperature": temperature, "num_predict": num_predict}}
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(
        f"{BASE}/api/chat", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    msg = data.get("message", {})
    content = msg.get("content", "")
    # 兜底剥离推理标签(agents 线踩过的坑)
    msg["content"] = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.S).strip()
    return msg


def chat_with_retry(messages, tools=None, attempts=3, **kw):
    """重试 + 弹性超时(01 实验验证过的最小 harness 第一课)。"""
    for i in range(attempts):
        try:
            return chat(messages, tools=tools,
                        timeout=kw.pop("timeout", 180 * (i + 1)), **kw)
        except (TimeoutError, OSError) as e:
            if i == attempts - 1:
                raise
            print(f"  [mh.retry {i + 1}] llm 失败({e}), 重试…")
