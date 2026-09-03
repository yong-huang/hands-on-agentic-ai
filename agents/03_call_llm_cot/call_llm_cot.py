import requests
import json
import re

# 配置信息 - 本地 Ollama
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"

HEADERS = {
    "Content-Type": "application/json"
}


# Chain-of-Thought 的主要形态:

# 1. Zero-Shot CoT（零样本思维链）
# 特点：不加示例，直接要求"逐步思考"

# 2. Few-Shot CoT（少样本思维链） ⭐
# 特点：提供 3-5 个带推理过程的示例

# 3. Self-Consistency CoT（自洽性思维链）
# 特点：多次采样 + 投票机制，提高准确性

# 4. Tree-of-Thoughts (ToT)（思维树）
# 特点：
# 多路径探索
# 评估每个中间步骤
# 回溯和剪枝

# 5. Graph-of-Thoughts (GoT)（思维图）
# 特点：
# 允许跨分支的信息传递
# 更灵活的推理结构
# 适合复杂问题

# 6. ReAct (Reasoning + Acting)
# 特点：
# 推理 + 工具使用
# 循环迭代
# 适合需要外部信息的任务

# 7. Auto-CoT（自动思维链）
# 特点：
# 自动化示例选择
# 无需人工编写
# 自适应不同任务

# 8. Decomposed CoT（分解式思维链）
# 特点：
# 问题分解
# 分步解决
# 最后整合

# 9. Program-Aided CoT（程序辅助思维链）
# 特点：
# 代码执行辅助
# 精确计算
# 适合数学/逻辑问题

# 10. Multi-Agent CoT（多智能体思维链）
# 特点：
# 多视角分析
# 角色分工
# 综合决策

# 你的脚本可以实现的形态
# 基于你的 call_llm_cot.py，可以支持：
# ✅ 容易实现
# Zero-Shot CoT：添加 "请逐步思考" 提示
# Few-Shot CoT：添加示例到 prompt
# Self-Consistency：多次调用取多数
# ⚠️ 需要扩展
# ReAct：集成工具调用
# Decomposed CoT：问题拆解逻辑
# Program-Aided：代码执行环境
# ❌ 较复杂
# Tree-of-Thoughts：需要搜索树管理
# Graph-of-Thoughts：图结构管理
# Multi-Agent：多模型协调

# 推荐实践
# 场景	推荐形态	复杂度
# 简单问答	Zero-Shot CoT	⭐
# 数学题	Program-Aided CoT	⭐⭐
# 复杂推理	Few-Shot CoT	⭐⭐
# 高准确性要求	Self-Consistency	⭐⭐⭐
# 工具使用	ReAct	⭐⭐⭐
# 复杂决策	Tree-of-Thoughts	⭐⭐⭐⭐
# 需要我帮你实现其中某一种形态吗？

SYSTEM_PROMPT = """你是一个数据分析助手。请按照以下格式输出JSON结果：

1. 首先，在 <thinking> 标签中展示你的推理过程
2. 然后，在 <output> 标签中输出纯JSON格式的结果

JSON格式要求：
{
    "category": "分类名称",
    "sentiment": "positive/neutral/negative",
    "confidence": 0.0-1.0,
    "keywords": ["关键词1", "关键词2"],
    "summary": "一句话总结"
}

Few-shot 示例：
用户: "这个产品很好用，质量也很棒！"
思考: 用户表达了积极态度，提到产品质量好，属于正面评价。
输出: {"category": "product_review", "sentiment": "positive", "confidence": 0.95, "keywords": ["好用", "质量"], "summary": "用户对产品表示满意"}

用户: "物流太慢了，等了好几天都没到"
思考: 用户抱怨物流速度慢，表达不满，属于负面评价。
输出: {"category": "logistics_complaint", "sentiment": "negative", "confidence": 0.9, "keywords": ["物流", "慢"], "summary": "用户对物流速度不满"}

用户: "价格适中，功能基本满足需求"
思考: 用户中性评价，既没有强烈正面也没有强烈负面。
输出: {"category": "product_feedback", "sentiment": "neutral", "confidence": 0.85, "keywords": ["价格", "功能"], "summary": "用户对产品和价格持中性态度"}
"""


def call_llm(prompt, temperature=0.3, max_tokens=1024):
    """调用模型生成结构化输出"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
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
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求错误: {e}")
        return None


def extract_json(text):
    """从响应中提取JSON内容"""

    # 这里使用了两级回退策略：
    # # 第一优先：从 <output> 标签提取
    # output_match = re.search(r'<output>\s*(\{.*?\})\s*</output>', text, re.DOTALL)
    # # 第二优先：从全文中提取第一个 JSON 对象
    # json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)

    # 这种回退策略增强了鲁棒性：即使模型不严格遵循标签格式，也能从自由文本中捕获 JSON。
    # 在工程实践中，更稳健的方案是使用模型的 **function calling / tool use** 功能，由服务端强制 JSON schema。

    # 尝试提取 <output> 标签内的内容
    output_match = re.search(r'<output>\s*(\{.*?\})\s*</output>', text, re.DOTALL)
    if output_match:
        return output_match.group(1)

    # 尝试提取任何JSON对象
    json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if json_match:
        return json_match.group(0)

    return None


def parse_structured_output(response_data):
    """解析结构化输出"""
    if not response_data:
        return None

    try:
        content = response_data["message"]["content"]

        # 打印完整响应（含推理过程）
        print("=" * 60)
        print("📝 模型完整响应:")
        print(content)
        print("=" * 60)

        # 提取并解析JSON
        json_str = extract_json(content)
        if json_str:
            result = json.loads(json_str)
            return result
        else:
            print("⚠️ 未找到JSON格式数据")
            return None

    except KeyError:
        print("❌ 响应格式异常")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析失败: {e}")
        return None


def print_structured_result(result):
    """美观打印结构化结果"""
    if not result:
        return

    print("\n📊 结构化输出结果:")
    print("-" * 40)
    print(f"📂 分类: {result.get('category', 'N/A')}")
    print(f"😊 情感: {result.get('sentiment', 'N/A')}")
    print(f"📈 置信度: {result.get('confidence', 0.0):.2f}")
    print(f"🏷️  关键词: {', '.join(result.get('keywords', []))}")
    print(f"📝 总结: {result.get('summary', 'N/A')}")
    print("-" * 40)


def main():
    user_input = input("🧑 请输入需要分析的文本: ").strip()
    if not user_input:
        user_input = "这个产品很好用，质量也很棒！"
        print(f"使用默认文本: {user_input}\n")

    print(f"🔗 连接到: {BASE_URL}")
    print(f"📦 模型: {MODEL}")
    print(f"🧠 使用 CoT + Few-shot 引导结构化输出\n")

    response = call_llm(user_input)
    result = parse_structured_output(response)

    if result:
        print_structured_result(result)
    else:
        print("❌ 未能解析结构化结果")


if __name__ == "__main__":
    main()
