import requests
import json
import sys
import re

# 配置信息 - 本地 Ollama
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"

HEADERS = {
    "Content-Type": "application/json"
}


# 消息历史会不断增长，但模型的 **context window** 有上限（如 4K/8K/32K tokens）。超出窗口后：
# - 旧消息被截断或忽略
# - 模型"遗忘"早期对话内容

# 实际工程中的处理策略：

# | 策略     | 实现                         | 优缺点                 |
# | :------- | :--------------------------- | :--------------------- |
# | 滑动窗口 | 只保留最近 N 轮              | 简单但丢失远期上下文   |
# | 摘要压缩 | 定期将旧消息压缩为摘要       | 保留关键信息但增加延迟 |
# | 向量检索 | 将旧消息存入向量库，按需检索 | 精确召回但复杂度高     |

# 本项目采用最简单的方案：保留全部历史（无截断），适合短对话场景。


class ChatSession:
    """多轮对话会话管理"""

    def __init__(self, system_prompt=None):
        # 对话历史仅存内存，无持久化（项目 10 解决）
        self.messages = []
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})
        self.conversation_count = 0

    def add_user_message(self, content):
        self.messages.append({"role": "user", "content": content})
        self.conversation_count += 1

    def add_assistant_message(self, content):
        self.messages.append({"role": "assistant", "content": content})

    def get_messages(self):
        # 浅拷贝：外部修改返回的列表会影响内部状态
        return self.messages.copy()

    def get_history_summary(self):
        total = len(self.messages)
        user_msgs = sum(1 for m in self.messages if m["role"] == "user")
        assistant_msgs = sum(1 for m in self.messages if m["role"] == "assistant")
        return f"总消息: {total} | 用户: {user_msgs} | 助手: {assistant_msgs} | 轮次: {self.conversation_count}"


def call_llm_with_history(messages, temperature=0.7, max_tokens=500):
    payload = {
        "model": MODEL,
        "messages": messages,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens
        },
        "stream": False
    }

    try:
        response = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求错误: {e}")
        return None


def extract_response(response_data):
    """提取并清理助手回复"""
    if not response_data:
        return None

    try:
        if "message" in response_data:
            msg = response_data["message"]

            # 优先使用 content
            if "content" in msg and msg["content"]:
                content = msg["content"].strip()
                if content:
                    # 移除开头的符号
                    content = re.sub(r'^\s*[*\-•]\s*', '', content)
                    return content

                        # 如果 content 为空，尝试从 thinking 提取
            if "thinking" in msg and msg["thinking"]:
                thinking = msg["thinking"]

                # 提取最终答案
                patterns = [
                    r'(?:Final\s+)?(?:Answer|Output|结果)[:：]\s*(.+?)(?=\n\n|\Z)',
                    r'(?:所以|因此|最终)[:：]\s*(.+?)(?=\n\n|\Z)',
                    r'返回[:：]\s*(.+?)(?=\n\n|\Z)'
                ]

                for pattern in patterns:
                    match = re.search(pattern, thinking, re.DOTALL | re.IGNORECASE)
                    if match:
                        return match.group(1).strip()

                # 提取包含中文且有意义的行
                lines = [l.strip() for l in thinking.split('\n') if l.strip()]
                chinese_lines = []
                for line in lines:
                    # 过滤掉编号和思考标记
                    if not re.match(r'^\d+\.', line) and not line.lower().startswith('thinking'):
                        if re.search(r'[\u4e00-\u9fff]', line) and len(line) > 15:
                            chinese_lines.append(line)

                if chinese_lines:
                    # 取最后几个有意义的中文句子
                    return ' '.join(chinese_lines[-2:])

                # 取最后非空行
                if lines:
                    return lines[-1]

        if "response" in response_data:
            return response_data["response"].strip()

        return None
    except Exception as e:
        return None


def print_help():
    print("\n📖 命令说明:")
    print("  /exit   - 退出对话")
    print("  /clear  - 清空历史")
    print("  /hist   - 显示历史摘要")
    print("  /help   - 显示此帮助")
    print()


def main():
    print("=" * 60)
    print("🤖 多轮对话系统 (优化版)")
    print(f"📦 模型: {MODEL}")
    print("=" * 60)

    # 强调直接输出
    system_prompt = "你是一个有用的AI助手。请直接回答用户的问题，不要显示思考过程、编号或列表符号。回答要清晰、完整、有帮助。"
    session = ChatSession(system_prompt)

    print_help()

    while True:
        try:
            user_input = input("\n🧑 你: ").strip()

            if not user_input:
                continue

            if user_input.lower() == "/exit":
                print("👋 再见！")
                break

            if user_input.lower() == "/clear":
                session = ChatSession(system_prompt)
                print("✅ 历史已清空")
                continue

            if user_input.lower() == "/hist":
                print(f"📊 {session.get_history_summary()}")
                recent = session.messages[-6:] if len(session.messages) > 6 else session.messages
                if recent:
                    print("  最近消息:")
                    for msg in recent:
                        role = "🧑" if msg["role"] == "user" else "🤖" if msg["role"] == "assistant" else "⚙️"
                        preview = msg["content"][:50] + "..." if len(msg["content"]) > 50 else msg["content"]
                        print(f"    {role} {preview}")
                continue

            if user_input.lower() == "/help":
                print_help()
                continue

            session.add_user_message(user_input)
            messages = session.get_messages()

            print("🤖 助手: ", end="", flush=True)

            response = call_llm_with_history(messages)
            assistant_content = extract_response(response)

            if assistant_content and len(assistant_content) > 5:
                print(assistant_content)
                session.add_assistant_message(assistant_content)
            else:
                print("❌ 抱歉，我无法处理这个请求，请重试。")
                session.messages.pop()

            print(f"\n📊 {session.get_history_summary()}")

        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 再见！")
            break
        except Exception as e:
            print(f"❌ 发生错误: {e}")
            continue


if __name__ == "__main__":
    main()
