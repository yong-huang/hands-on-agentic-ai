import requests
import json
import sys

# 流式调用通过 **Server-Sent Events（SSE）** 协议，让模型每生成一个 token 就立即推送给客户端，实现"打字机效果"。

# 三个关键细节：
# - `stream=True`：告诉 requests 不要一次性读取全部响应体，而是逐块读取
# - `iter_lines()`：按行迭代 SSE 数据流
# - `flush=True`：强制刷新输出缓冲区，确保终端立即显示

# 配置信息 - 本地 Ollama
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"

HEADERS = {
    "Content-Type": "application/json"
}


def call_llm_stream(prompt, temperature=0.7, max_tokens=2048):
    """发送流式请求，实时打印每个 token"""
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
        "stream": True
    }

    try:
        response = requests.post(
            BASE_URL,
            headers=HEADERS,
            json=payload,
            stream=True,
            timeout=60
        )
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        print(f"\n❌ 请求错误: {e}")
        return None


def process_stream(response):
    """处理 SSE 流式响应，逐字打印"""

    # 每行以 `data: ` 开头，包含一个 JSON 对象。最后一行是 `[DONE]` 标记流结束：

    # data: {"message":{"content":"人"},"done":false}
    # data: {"message":{"content":"工"},"done":false}
    # data: {"message":{"content":"智"},"done":false}
    # ...
    # data: {"message":{"content":"。"},"done":true}
    # data: [DONE]

    if not response:
        return

    print("🤖 助手: ", end="", flush=True)
    full_content = ""

    # response.iter_lines() 逐行读取（非阻塞）
    for line in response.iter_lines():
        if not line:
            continue

        # 流式调用的 overhead 通常在 2-5% 之间，具体取决于：
        #   响应长度（越长相对开销越小）
        #   网络延迟（延迟越高流式优势越大）
        #   数据块大小（块越小开销越大）
        # 实际建议：
        #   ✅ 优先使用流式：用户体验提升远大于性能损失
        #   ✅ 优化 flush 频率：可以每 10-20 个字符 flush 一次
        #   ✅ 处理大响应：流式几乎是必须的

        # 解码并解析 JSON
        try:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                line_str = line_str[6:]

            if line_str == '[DONE]':
                break

            data = json.loads(line_str)

            # 提取内容
            if 'message' in data and 'content' in data['message']:
                chunk = data['message']['content']
                # flush=True 立即输出，不换行
                print(chunk, end="", flush=True)
                full_content += chunk

            # 检查是否完成
            if data.get('done', False):
                break

        except json.JSONDecodeError:
            continue
        except Exception as e:
            print(f"\n⚠️ 处理错误: {e}")
            continue

    print("\n")  # 换行
    return full_content


def print_metadata(response):
    """打印元数据（从最后一个响应中提取）"""
    if not response:
        return

    # 从响应头或最后一行提取，这里简单提示
    print("📊 流式输出完成")


def main():
    user_prompt = input("🧑 请输入提示词: ").strip()
    if not user_prompt:
        user_prompt = "用一句话解释什么是人工智能。"
        print(f"使用默认提示: {user_prompt}\n")

    print(f"🔗 连接到: {BASE_URL}")
    print(f"📦 模型: {MODEL}")
    print(f"⚡ 流式模式: 已启用\n")

    response = call_llm_stream(user_prompt)
    content = process_stream(response)

    if content:
        print_metadata(response)
    else:
        print("❌ 未获得有效响应")


if __name__ == "__main__":
    main()
