"""
统一 LLM 客户端 — 所有面试项目复用 (qa.md 环境约定)

- OpenAI 兼容接口: base_url / model / api_key 全部从环境变量读取
- 默认指向本地 Ollama (http://localhost:11434/v1, qwen3.8:latest, 免 Key)
- 环境变量: LLM_BASE_URL / LLM_MODEL / LLM_API_KEY
- MOCK=1 时各项目可用 mock_chat() 走预置脚本, 离线可跑
"""

import json
import os
import re
import urllib.request

BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
MODEL = os.environ.get("LLM_MODEL", "qwen3.8:latest")
API_KEY = os.environ.get("LLM_API_KEY", "ollama")


def chat(messages, temperature=0.0, num_predict=500, timeout=180):
    """OpenAI 兼容 /chat/completions。返回助手文本。"""
    body = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": num_predict,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    # 部分 OpenAI 兼容实现会把推理模型的思想留在 content 里, 常见标签兜底剥离
    return re.sub(r"<think>.*?</think>\s*", "", content, flags=re.S).strip()


def extract_number(text):
    """从回答中提取最终数值: 优先 '答案: X', 否则取最后一个数字。"""
    m = re.search(r"答案[:：]?\s*(-?\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    nums = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(nums[-1]) if nums else None


def mock_chat(responses):
    """工厂: 按提问关键词顺序匹配预置回答的 MockLLM (MOCK=1 离线模式用)。"""
    def _mock(messages, temperature=0.0, num_predict=500, timeout=180):
        user = messages[-1]["content"]
        for keyword, answer in responses:
            if keyword in user:
                return answer
        return responses[-1][1]
    return _mock
