import requests
import json
import time
import sys


# 本脚本把调用 LLM 的三件基础事放进一个文件，按模式演示：
#
#   python call_llm_basics.py          # 依次跑全部三段（默认）
#   python call_llm_basics.py basic    # 非流式最小调用：组装 → POST → 解析
#   python call_llm_basics.py stream   # SSE 流式：逐 token 打字机效果
#   python call_llm_basics.py temp     # 温度对照：0.0 / 0.5 / 1.0 横向量化
#
# Ollama 与 OpenAI Chat Completions API 对比（同一概念，字段名不同）：
#
# | 维度       | Ollama                      | OpenAI                         |
# | :--------- | :-------------------------- | :----------------------------- |
# | 端点       | `POST /api/chat`            | `POST /v1/chat/completions`    |
# | 认证       | 无需 API Key                | `Authorization: Bearer sk-xxx` |
# | 消息格式   | `messages[{role, content}]` | 相同                           |
# | 流式       | `stream: true` → SSE        | 相同                           |
# | 最大 token | `options.num_predict`       | `max_tokens`                   |
#
# 理解了这个最小骨架后，后续的结构化输出、多轮对话、Agent 循环都是在
# 同一基础上的增量扩展。


# 配置信息 - 本地 Ollama
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"

HEADERS = {
    "Content-Type": "application/json"
}


# ============ 第一段：非流式最小调用 ============

def call_llm(prompt, temperature=0.7, max_tokens=2048):
    """发送原始 HTTP POST 请求调用本地 Ollama API"""

    # `messages` 数组的顺序很重要：system prompt 定义角色，user 消息是本轮输入，
    # assistant 消息是对话历史（多轮对话时由调用方手动带回去）。
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        "options": {
            "temperature": temperature,      # 采样随机性，温度对照见 run_temperature
            "num_predict": max_tokens        # Ollama 的最大生成 token 数
        },
        "stream": False                      # False: 一次性等完整 JSON
    }

    try:
        # OpenAI 的 API 调用方式类似，不过 url 和认证方式不太一样
        response = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=60)
        response.raise_for_status()          # 4xx/5xx 直接抛异常，不让坏响应溜进解析
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求错误: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"响应内容: {e.response.text[:200]}")
        return None


def extract_content(response_data):
    """提取回复内容，带推理模型 thinking 字段的兜底"""

    # qwen3.8 是推理模型（会把思考过程单独输出），响应里可能同时有
    # message.thinking 与 message.content，且答案偶尔只出现在 thinking 里。
    # 所以做三级兜底：content → thinking 的最后有效行 → response 字段。
    if not response_data:
        return None
    try:
        message = response_data.get("message", {})
        content = message.get("content", "").strip()
        if not content and message.get("thinking"):     # 推理模型兜底
            for line in reversed(message["thinking"].splitlines()):
                line = line.strip()
                if line and not line.startswith("Thinking"):
                    return line                         # thinking 里最后一条有效行
        return content or response_data.get("response")  # generate 接口风格兜底
    except KeyError:
        # 结构完全对不上时打印原始 JSON——调试陌生模型响应的通用技巧
        print("响应格式异常:")
        print(json.dumps(response_data, indent=2, ensure_ascii=False))
        return None


def print_usage(response_data):
    """打印元数据（Ollama 不按 token 计费，打印模型与时间戳）"""
    if response_data:
        print(f"\n📊 统计: 模型 {response_data.get('model', 'unknown')} | "
              f"创建时间 {response_data.get('created_at', 'unknown')}")


def run_basic():
    """非流式最小调用：组装 payload → POST → 从完整 JSON 里取 message.content"""
    print("=" * 70)
    print("🔶 第一段 · 非流式最小调用（组装 → POST → 解析）")
    print("=" * 70)
    user_prompt = "用一句话解释什么是人工智能。"
    print(f"🧑 用户: {user_prompt}")
    print(f"🔗 连接到: {BASE_URL}")
    print(f"📦 模型: {MODEL}\n")

    result = call_llm(user_prompt)
    content = extract_content(result)

    if content:
        print(f"🤖 助手: {content}")
        print_usage(result)
    else:
        print("❌ 未获得有效响应")
    print()


# ============ 第二段：SSE 流式输出 ============

def call_llm_stream(prompt, temperature=0.7, max_tokens=2048):
    """发送流式请求，返回未消费的响应对象"""
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
        "stream": True                       # True: 服务端逐 token 推送（SSE）
    }

    try:
        # stream=True 告诉 requests 不要一次性读完响应体，而是拿到字节流慢慢迭代
        response = requests.post(BASE_URL, headers=HEADERS, json=payload,
                                 stream=True, timeout=60)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求错误: {e}")
        return None


def process_stream(response):
    """逐行解析 SSE 流，打字机式打印并拼接完整文本"""

    # 流式响应在网络上长这样——每行一个 `data: ` 前缀 + 一段 JSON：
    #   data: {"message":{"content":"人"},"done":false}
    #   data: {"message":{"content":"工"},"done":false}
    #   ...
    #   data: {"message":{"content":"。"},"done":true}
    #   data: [DONE]
    if not response:
        return None

    print("🤖 助手: ", end="", flush=True)
    full_content = ""

    # iter_lines() 自带按行缓冲。不要手写 iter_content 按字节切——容易把
    # 一行 JSON 切成两半导致解析随机失败
    for line in response.iter_lines():
        if not line:
            continue

        try:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                line_str = line_str[6:]      # 剥掉 "data: " 前缀

            if line_str == '[DONE]':         # OpenAI 风格的结束哨兵
                break

            data = json.loads(line_str)
            chunk = data.get('message', {}).get('content', '')
            if chunk:
                # flush=True 立即刷新输出缓冲区——没有它终端攒够缓冲才显示，
                # 打字机效果就没了
                print(chunk, end="", flush=True)
                full_content += chunk

            if data.get('done', False):      # Ollama 风格的结束标记（带统计字段）
                break

        except json.JSONDecodeError:
            continue                         # 心跳注释行/空行：跳过，别让流崩掉
        except Exception as e:
            print(f"\n⚠️ 处理错误: {e}")
            continue

    print("\n")
    return full_content


def run_stream():
    """流式演示：同一个问题，看回复如何逐 token 到达终端"""
    print("=" * 70)
    print("⚡ 第二段 · SSE 流式输出（打字机效果）")
    print("=" * 70)
    print(f"🧑 用户: 用一句话解释什么是机器学习。")
    print(f"🔗 连接到: {BASE_URL}")
    print(f"📦 模型: {MODEL}")
    print(f"⚡ 流式模式: 已启用\n")

    response = call_llm_stream("用一句话解释什么是机器学习。")
    content = process_stream(response)

    if content:
        # 流式结束后拼接出的 full_content 与非流式的 message.content 等价，
        # 可以和第一段互相验证
        print(f"📏 拼接完成，共 {len(content)} 字符（与非流式结果等价）")
    else:
        print("❌ 未获得有效响应")
    print()


# ============ 第三段：温度对照实验 ============

TEMP_PROMPT = "请用一句话描述什么是机器学习，要求包含'数据'和'模式'两个关键词。"
TEMP_SYSTEM = "你是一个专业的AI助手，回答简洁准确。"


def call_with_temperature(temperature, max_tokens=150):
    """固定提示词与 max_tokens，只把 temperature 当自变量"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": TEMP_SYSTEM},
            {"role": "user", "content": TEMP_PROMPT}
        ],
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
        print(f"  ❌ 请求错误 (temperature={temperature}): {e}")
        return None


def run_temperature():
    """对照实验：固定一切，只改 temperature（0.0 / 0.5 / 1.0）"""
    print("=" * 70)
    print("🌡️ 第三段 · Temperature 参数对照实验")
    print("=" * 70)
    print(f"📝 提示词: {TEMP_PROMPT}")
    print("🔬 设计: 固定提示词/system/num_predict=150，唯一自变量是 temperature\n")

    results = {}
    for temp in (0.0, 0.5, 1.0):
        print(f"🌡️  temperature = {temp}")
        print("-" * 40)
        content = extract_content(call_with_temperature(temp))
        if content:
            print(f"📤 输出: {content}")
            results[temp] = content
        else:
            print("❌ 无有效响应")
            results[temp] = None
        print()
        time.sleep(0.5)                      # 本地推理有排队，间隔避免互相污染计时

    analyze_temperature(results)


def analyze_temperature(results):
    """量化对比：长度、关键词命中、词汇多样性（评估 Agent 的基本功）"""
    print("📊 对照分析")
    print("-" * 40)
    valid = {t: c for t, c in results.items() if c}
    if not valid:
        print("❌ 无有效结果可分析")
        return

    for temp, content in valid.items():
        hits = f"'数据'={'✓' if '数据' in content else '✗'} " \
               f"'模式'={'✓' if '模式' in content else '✗'}"
        # 中文没有空格分词，按去重汉字数衡量词汇多样性
        diversity = len(set(c for c in content if '\u4e00' <= c <= '\u9fff'))
        print(f"• temp={temp}: {len(content)} 字符 | {hits} | 去重汉字数 {diversity}")

    # 数学上 temperature 作用于 softmax 的 logits：p(x) = softmax(logits / T)
    #   T→0  分布退化成 argmax，输出可复现 → 工具调用/分类/抽取
    #   T=1  原始分布 → 日常对话、摘要
    #   T>1  分布被压平，长尾词有机会 → 创意写作，但牺牲指令遵循
    lows = [c for t, c in valid.items() if t == 0.0]
    highs = [c for t, c in valid.items() if t == 1.0]
    if lows and highs:
        same = lows[0] == highs[0]
        print(f"• 0.0 与 1.0 档输出{'完全一致' if same else '不同'}——"
              f"低温更可复现，高温更多样")
    print("📌 结论: 输出要被程序解析选低温，要多样表达选高温；"
          "结论必须来自控制变量 + 量化指标，不凭印象。")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode not in ("all", "basic", "stream", "temp"):
        print("可用模式: all | basic | stream | temp")
        sys.exit(1)
    if mode in ("all", "basic"):
        run_basic()
    if mode in ("all", "stream"):
        run_stream()
    if mode in ("all", "temp"):
        run_temperature()


if __name__ == "__main__":
    main()
