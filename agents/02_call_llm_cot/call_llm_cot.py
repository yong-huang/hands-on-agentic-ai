import requests
import json
import re
import sys


# 本脚本演示 Prompt 结构设计（角色 + CoT + Few-shot + 输出标签），按模式运行：
#
#   python call_llm_cot.py                    # 单次结构化分析（默认，最快）
#   python call_llm_cot.py all                # 依次跑全部四段
#   python call_llm_cot.py zero-vs-few        # Zero-Shot vs Few-Shot 格式遵循率对照
#   python call_llm_cot.py self-consistency   # Self-Consistency：多次采样投票
#   python call_llm_cot.py roles              # 三种角色实测同一问题的回答差异
#
# Chain-of-Thought（思维链）的主要形态:
#
# 1. Zero-Shot CoT（零样本思维链）
#    不加示例，直接要求"逐步思考"
# 2. Few-Shot CoT（少样本思维链）⭐ 本脚本的 SYSTEM_PROMPT 即此形态
#    提供 3-5 个带推理过程的示例
# 3. Self-Consistency CoT（自洽性思维链）
#    多次采样 + 投票机制，提高准确性 → 见 self-consistency 模式
# 4. Tree-of-Thoughts (ToT)（思维树）
#    多路径探索、评估中间步骤、回溯和剪枝
# 5. Graph-of-Thoughts (GoT)（思维图）
#    允许跨分支的信息传递，适合复杂问题
# 6. ReAct (Reasoning + Acting)
#    推理 + 工具使用，循环迭代 → 本系列 04 实验
# 7. Auto-CoT（自动思维链）
#    自动化示例选择，无需人工编写
# 8. Decomposed CoT（分解式思维链）
#    问题分解、分步解决、最后整合
# 9. Program-Aided CoT（程序辅助思维链）
#    代码执行辅助精确计算，适合数学/逻辑问题
# 10. Multi-Agent CoT（多智能体思维链）
#    多视角分析、角色分工 → 见 roles 模式的轻量版
#
# 推荐实践
# 场景            推荐形态            复杂度
# 简单问答        Zero-Shot CoT       ⭐
# 数学题          Program-Aided CoT   ⭐⭐
# 复杂推理        Few-Shot CoT        ⭐⭐
# 高准确性要求    Self-Consistency    ⭐⭐⭐
# 工具使用        ReAct               ⭐⭐⭐
# 复杂决策        Tree-of-Thoughts    ⭐⭐⭐⭐


# 配置信息 - 本地 Ollama
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"

HEADERS = {
    "Content-Type": "application/json"
}

REQUIRED_FIELDS = ["category", "sentiment", "confidence", "keywords", "summary"]


# 四层结构：角色 → 任务+格式约定 → CoT 指令 → Few-shot 示例
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

# 对照组：Zero-Shot CoT——同样"先想后说"，但没有任何示例。
# 差别只在 Few-shot 层：格式全靠指令描述，没有"照着抄"的锚点。
ZERO_SHOT_PROMPT = """你是一个数据分析助手。请先逐步思考，再输出结果。

1. 先展示你的推理过程
2. 最后输出纯JSON格式的结果，字段包括：
   category, sentiment (positive/neutral/negative), confidence (0.0-1.0),
   keywords (数组), summary (一句话总结)
   只输出 JSON，不要附加其他文字。"""


def call_llm(prompt, system_prompt=SYSTEM_PROMPT, temperature=0.3, max_tokens=1024):
    """调用模型，temperature 默认 0.3（结构化任务要低温）"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
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


def extract_text(response_data):
    """取出模型回复文本（含 thinking 兜底：推理模型可能把正文写进 thinking）"""
    if not response_data:
        return None
    message = response_data.get("message", {})
    content = message.get("content", "").strip()
    if not content and message.get("thinking"):
        return message["thinking"].strip()
    return content or None


def extract_json(text):
    """从响应中提取JSON内容——两级回退"""

    # 第一级精准：<output> 标签内提取；第二级兜底：全文第一个无嵌套 {...}。
    # 模型偶尔忘写标签时第二级仍能救回。正则必须带 re.S（DOTALL），否则
    # 跨行 JSON 匹配失败。工程上更稳健的方案是 function calling / JSON mode，
    # 由服务端强制 JSON schema（见本系列 09 实验）。
    output_match = re.search(r'<output>\s*(\{.*?\})\s*</output>', text, re.DOTALL)
    if output_match:
        return output_match.group(1)

    json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if json_match:
        return json_match.group(0)

    return None


def is_well_formed(json_str):
    """格式遵循判定：可解析 + 五字段齐全 + sentiment 取值合法"""
    if not json_str:
        return False
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return False
    if not all(field in data for field in REQUIRED_FIELDS):
        return False
    return data.get("sentiment") in ("positive", "neutral", "negative")


def parse_structured_output(response_data, verbose=True):
    """解析结构化输出，美观打印"""
    content = None
    try:
        content = extract_text(response_data)
        if content is None:
            print("❌ 响应格式异常")
            return None

        if verbose:
            print("=" * 60)
            print("📝 模型完整响应:")
            print(content)
            print("=" * 60)

        json_str = extract_json(content)
        if json_str:
            return json.loads(json_str)

        print("⚠️ 未找到JSON格式数据")
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


# ============ 模式一：单次结构化分析 ============

def run_single():
    text = ask("🧑 请输入需要分析的文本: ").strip()
    if not text:
        text = "这个产品很好用，质量也很棒！"
        print(f"使用默认文本: {text}\n")

    print(f"🔗 连接到: {BASE_URL}")
    print(f"📦 模型: {MODEL}")
    print(f"🧠 使用 CoT + Few-shot 引导结构化输出\n")

    result = parse_structured_output(call_llm(text))
    if result:
        print_structured_result(result)
    else:
        print("❌ 未能解析结构化结果")


# ============ 模式二：Zero-Shot vs Few-Shot 对照 ============

def run_zero_vs_few(rounds=3):
    """同一输入各跑 N 次，量化两种形态的格式遵循率"""
    text = "这个产品很好用，质量也很棒！"
    print("=" * 60)
    print("🧪 Zero-Shot vs Few-Shot 格式遵循率对照")
    print("=" * 60)
    print(f"📝 输入（固定）: {text}")
    print(f"🔬 设计: 各跑 {rounds} 次，判定 = JSON 可解析 + 五字段齐全"
          f" + sentiment 合法\n")

    scores = {}
    for name, system_prompt in (("Zero-Shot", ZERO_SHOT_PROMPT),
                                ("Few-Shot ", SYSTEM_PROMPT)):
        ok = 0
        for i in range(rounds):
            content = extract_text(call_llm(text, system_prompt=system_prompt))
            well_formed = is_well_formed(extract_json(content) if content else None)
            mark = "✅" if well_formed else "❌"
            preview = (content or "").replace("\n", " ")[:60]
            print(f"  {name} 第{i + 1}轮 {mark} {preview}...")
            ok += well_formed
        scores[name.strip()] = ok
        print()

    print("📊 结论:")
    for name, ok in scores.items():
        print(f"  {name}: {ok}/{rounds} 轮格式合规")
    print("💡 示例的格式一致性是关键——Few-shot 给模型一个『照着抄』的锚点，")
    print("   服从度远高于『按字段描述输出』；但无论哪种形态，解析侧都要留兜底。")


# ============ 模式三：Self-Consistency 投票 ============

def run_self_consistency(samples=3):
    """同一问题高温多次采样，对 sentiment 多数投票"""
    text = "物流太慢了，等了好几天都没到，不过客服态度还不错。"
    print("=" * 60)
    print("🗳️ Self-Consistency：多次采样 + 多数投票")
    print("=" * 60)
    print(f"📝 输入: {text}")
    print(f"🔬 设计: temperature=0.7 采样 {samples} 次，对 sentiment 投票\n")

    votes = []
    for i in range(samples):
        result = parse_structured_output(
            call_llm(text, temperature=0.7, max_tokens=512), verbose=False)
        sentiment = result.get("sentiment") if result else None
        confidence = result.get("confidence", 0.0) if result else 0.0
        mark = sentiment if sentiment in ("positive", "neutral", "negative") else "解析失败"
        print(f"  采样 {i + 1}: {mark} (confidence={confidence:.2f})")
        votes.append(sentiment)

    valid = [v for v in votes if v in ("positive", "neutral", "negative")]
    if not valid:
        print("\n❌ 全部采样解析失败")
        return

    tally = {s: valid.count(s) for s in set(valid)}
    winner, top = max(tally.items(), key=lambda kv: kv[1])
    print(f"\n📊 票型: {tally}")
    if list(tally.values()).count(top) > 1:
        print(f"⚖️ 平票（{tally}）——Self-Consistency 不是万能的，平票时")
        print("   应提高采样数或降低温度重跑，而不是硬选一个。")
    else:
        print(f"✅ 多数投票结论: {winner}（{top}/{len(valid)} 票）")
    print("💡 单条文本看不出差别，换成『混合情感』输入（正负兼具）时，")
    print("   投票比单次采样稳定得多——这正是高准确率场景的用法。")


# ============ 模式四：三角色实测 ============

ROLE_PROMPTS = {
    "数据工程师": "你是一名资深数据工程师，回答侧重数据与实现。",
    "产品经理": "你是一名产品经理，回答侧重用户价值与产品决策。",
    "安全审计师": "你是一名安全审计师，回答侧重风险与合规。",
}


def run_roles():
    """角色层实验：同一问题换三种 system 角色，回答侧重点立刻分化"""
    question = "如何看待这条用户反馈：『这个产品很好用，质量也很棒！』"
    print("=" * 60)
    print("🎭 角色层实验：同一问题 × 三种角色")
    print("=" * 60)
    print(f"📝 问题（固定）: {question}")
    print("🔬 说明: What 层的示例没有 JSON 约束，自由作答看视角差异\n")

    for role, system_prompt in ROLE_PROMPTS.items():
        print(f"👤 {role}:")
        content = extract_text(call_llm(question, system_prompt=system_prompt,
                                        temperature=0.5, max_tokens=300))
        if content:
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            for line in lines[:8]:           # 每个角色最多展示 8 行，够看出视角即可
                print(f"   {line}")
            if len(lines) > 8:
                print(f"   ……（其余 {len(lines) - 8} 行略）")
        else:
            print("   ❌ 无有效响应")
        print()

    print("💡 角色不是玄学：它是对采样分布的条件约束——设定改变了每个词")
    print("   的生成概率，于是工程师谈数据、产品谈价值、审计谈风险。")


def ask(msg: str = "") -> str:
    # 内置 input() 的回显由终端按"列"擦除, 不认识 CJK 宽字符 (一个汉字占 2 列),
    # 退格删除中文会残留半个字。prompt_toolkit 用 raw 模式自绘输入行, 按字符宽度
    # 正确擦除; 未安装时自动回退到内置 input()。
    try:
        from prompt_toolkit import prompt
        return prompt(msg)
    except ImportError:
        return input(msg)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "single"
    modes = ("single", "zero-vs-few", "self-consistency", "roles", "all")
    if mode not in modes:
        print(f"可用模式: {' | '.join(modes)}")
        sys.exit(1)

    if mode in ("single", "all"):
        run_single()
    if mode in ("zero-vs-few", "all"):
        print()
        run_zero_vs_few()
    if mode in ("self-consistency", "all"):
        print()
        run_self_consistency()
    if mode in ("roles", "all"):
        print()
        run_roles()


if __name__ == "__main__":
    main()
