import requests
import json
import time

# 配置信息 - 本地 Ollama
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"

HEADERS = {
    "Content-Type": "application/json"
}

PROMPT = "请用一句话描述什么是机器学习，要求包含'数据'和'模式'两个关键词。"

SYSTEM_MSG = "你是一个专业的AI助手，回答简洁准确。"


def call_llm(prompt, temperature, max_tokens=150):
    """调用 API，指定 temperature"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_MSG},
            {"role": "user", "content": prompt}
        ],
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens
        },
        "stream": False
    }

    try:
        response = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=60)

        if response.status_code != 200:
            print(f"  ⚠️  HTTP状态码: {response.status_code}")
            print(f"  📄 响应内容: {response.text[:200]}")
            response.raise_for_status()

        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"  ❌ 请求错误 (temperature={temperature}): {e}")
        return None


def extract_content(response_data):
    """提取响应内容 - 处理 thinking 字段"""
    if not response_data:
        return None

    try:
        # 检查是否包含 thinking（推理过程）
        if "message" in response_data:
            msg = response_data["message"]

            # 如果有 thinking 字段，内容可能在 thinking 中
            if "thinking" in msg and msg["thinking"]:
                thinking = msg["thinking"]
                # 尝试从 thinking 中提取最终答案
                # 通常 thinking 包含推理过程，最终答案在最后
                lines = thinking.strip().split('\n')
                # 寻找最后几行可能包含答案
                for line in reversed(lines):
                    if line.strip() and not line.startswith('Thinking'):
                        return line.strip()
                return thinking.strip()

            # 如果有 content 字段
            if "content" in msg and msg["content"]:
                return msg["content"].strip()

        # 如果有 response 字段
        if "response" in response_data:
            return response_data["response"].strip()

        return None

    except Exception as e:
        print(f"  ❌ 提取内容失败: {e}")
        return None


def run_experiment():
    """运行温度调优实验"""
    temperatures = [0.0, 0.5, 1.0]
    results = {}

    print("=" * 70)
    print("🧪 Temperature 参数调优实验")
    print("=" * 70)
    print(f"📝 提示词: {PROMPT}")
    print(f"🔗 模型: {MODEL}")
    print(f"📍 API: {BASE_URL}\n")

    print("开始实验...\n")

    for temp in temperatures:
        print(f"🌡️  测试 temperature = {temp}")
        print("-" * 40)

        response = call_llm(PROMPT, temp)
        content = extract_content(response)

        if content:
            print(f"📤 输出: {content}")
            results[temp] = content
        else:
            print("❌ 无有效响应")
            if response:
                # 打印完整响应以便调试
                print(f"  完整响应结构:")
                print(f"  - message 字段: {list(response.get('message', {}).keys())}")
                if 'message' in response and 'thinking' in response['message']:
                    thinking = response['message']['thinking']
                    print(f"  - thinking 内容: {thinking[:200]}...")
            results[temp] = None

        print()
        time.sleep(0.5)

    return results


def analyze_results(results):
    """分析对比结果"""
    print("=" * 70)
    print("📊 结果对比分析")
    print("=" * 70)

    if not results:
        print("❌ 无有效结果可分析")
        return

    valid_results = {k: v for k, v in results.items() if v is not None}

    if not valid_results:
        print("❌ 所有请求都失败了")
        print("\n💡 可能原因:")
        print("1. 模型返回的内容在 'thinking' 字段中，需要调整提取逻辑")
        print("2. 模型可能需要特定的提示格式")
        return

    print(f"✅ 成功获取 {len(valid_results)} 个响应\n")

    # 统计各 temperature 的响应
    for temp, content in valid_results.items():
        length = len(content)
        words = len(content.split())
        print(f"🌡️  temp={temp}: 长度 {length} 字符, {words} 词")
        print(f"   📝 {content}")
        print()

    # 对比总结
    print("📌 观察总结:")
    print("-" * 40)

    if len(valid_results) >= 2:
        temps = sorted(valid_results.keys())
        first_temp = temps[0]
        last_temp = temps[-1]

        # 检查关键词
        for temp, content in valid_results.items():
            has_data = "数据" in content
            has_pattern = "模式" in content
            print(f"• temp={temp}: 包含'数据'={has_data}, 包含'模式'={has_pattern}")

        # 长度对比
        if valid_results[first_temp] and valid_results[last_temp]:
            len_first = len(valid_results[first_temp])
            len_last = len(valid_results[last_temp])
            print(f"• 响应长度变化: {len_first} → {len_last} 字符")

        # 词汇多样性
        words_first = set(valid_results[first_temp].split())
        words_last = set(valid_results[last_temp].split())
        print(f"• 词汇多样性: {len(words_first)} → {len(words_last)} 个独特词")

        if len(words_last) > len(words_first):
            print("  ✅ 较高 temperature 产生更多样化的表达")
        elif len(words_first) > len(words_last):
            print("  ✅ 较低 temperature 输出更集中、更确定")
        else:
            print("  ⚖️  词汇多样性相近")

    # 数学上，temperature 作用于 softmax 的 logits：

    # p(x) = softmax(logits / temperature)

    # - **temperature → 0**：logits 被"无限放大"，最高概率 token 的概率趋近 1（argmax）
    # - **temperature = 1**：原始概率分布不变
    # - **temperature > 1**：概率分布被"压平"，低概率 token 也有机会被选中

    print("\n💡 建议:")
    print("• temperature=0.0: 用于需要确定性输出的任务（如代码生成、数据提取）")
    print("• temperature=0.5: 用于平衡创造性和准确性的任务")
    print("• temperature=1.0: 用于创意写作、头脑风暴等需要多样性的场景")
    print("=" * 70)


def main():
    results = run_experiment()
    analyze_results(results)


if __name__ == "__main__":
    main()
