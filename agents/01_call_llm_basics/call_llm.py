import requests
import json


# Ollama 与 OpenAI Chat Completions API 对比：

# | 维度       | Ollama                      | OpenAI                         |
# | :--------- | :-------------------------- | :----------------------------- |
# | 端点       | `POST /api/chat`            | `POST /v1/chat/completions`    |
# | 认证       | 无需 API Key                | `Authorization: Bearer sk-xxx` |
# | 消息格式   | `messages[{role, content}]` | 相同                           |
# | 流式       | `stream: true` → SSE        | 相同                           |
# | 最大 token | `options.num_predict`       | `max_tokens`                   |

# 理解了这个最小骨架后，后续的流式输出、CoT、多轮对话都是在同一基础上的增量扩展。


# 配置信息 - 本地 Ollama
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"

HEADERS = {
    "Content-Type": "application/json"
}


def call_llm(prompt, temperature=0.7, max_tokens=2048):
    """发送原始 HTTP POST 请求调用本地 Ollama API"""

    # `messages` 数组的顺序很重要：system prompt 定义角色，user 消息是本轮输入，assistant 消息是对话历史。
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens
        },
        "stream": False
    }

    try:
        # OpenAI的API调用方式类似，不过url和认证方式不太一样
        response = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"请求错误: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"响应内容: {e.response.text}")
        return None


def extract_content(response_data):
    """从 API 响应中提取回复内容"""

    # 注意：Ollama 的响应结构与 OpenAI 略有不同

    # 这里处理了 `message.content` 字段缺失或格式异常的情况。在真实工程中，响应解析还需要处理：
    # - `finish_reason`：判断是否因 token 上限被截断
    # - `usage`：记录 prompt_tokens / completion_tokens 用于成本计量
    # - 多候选（`n > 1`）：从中选择最优响应

    if not response_data:
        return None
    try:
        return response_data["message"]["content"]
    except KeyError:
        print("响应格式异常:")
        print(json.dumps(response_data, indent=2, ensure_ascii=False))
        return None


def print_usage(response_data):
    """打印统计信息（Ollama 不返回 token 使用，打印响应元数据）"""
    if response_data:
        print(f"\n📊 统计: 模型 {response_data.get('model', 'unknown')} | "
              f"创建时间 {response_data.get('created_at', 'unknown')}")


def main():
    user_prompt = "用一句话解释什么是人工智能。"
    print(f"🧑 用户: {user_prompt}\n")
    print(f"🔗 连接到: {BASE_URL}")
    print(f"📦 模型: {MODEL}\n")

    result = call_llm(user_prompt)
    content = extract_content(result)

    if content:
        print(f"🤖 助手: {content}")
        print_usage(result)
    else:
        print("❌ 未获得有效响应")


if __name__ == "__main__":
    main()
