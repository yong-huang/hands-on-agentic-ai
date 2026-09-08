"""
面试项目 2 — CoT 失效场景解剖

覆盖面试题: CoT 的局限性是什么？什么时候 CoT 反而降低性能？

实验设计: 构造三类对 CoT 不利的任务
  A 简单常识题     CoT 的"逐步推理"是多余的, 白花 token
  B 干扰项数学题   题面包含无关数字, CoT 推理链容易被带偏
  C 隐藏意图题     需要理解"没说的部分", CoT 反而暴露错误中间结论

每类任务跑 有 CoT / 无 CoT 两种模式, 输出正确率 + token 消耗对比,
最后给出"何时关 CoT"的判断规则。

运行:
  MOCK=1 python cot_failure.py    # 离线: 预置回答
  python cot_failure.py           # 真实: qwen3.8
"""

import os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import chat, extract_number

MOCK = os.environ.get("MOCK") == "1"

# ============================================================
# 三类任务集 (每类 5 题, 共 15 题)
# ============================================================

CASES = [
    # A 简单常识: CoT 多余
    {"cat": "A", "q": "中国的首都是哪里？", "a": "北京"},
    {"cat": "A", "q": "水的化学式是什么？", "a": "H2O"},
    {"cat": "A", "q": "一年有几个月？", "a": "12"},
    {"cat": "A", "q": "太阳从哪个方向升起？", "a": "东方"},
    {"cat": "A", "q": "1 千克等于多少克？", "a": "1000"},
    # B 干扰项数学: 多余数字诱导错误推理链
    {"cat": "B", "q": "小明有 3 个苹果和 7 本书，他买了 5 个苹果，现在有几个苹果？", "a": "8"},
    {"cat": "B", "q": "火车上有 200 名乘客，其中 50 名是儿童，火车经过车站后下车 30 人，车上还有多少名乘客？", "a": "170"},
    {"cat": "B", "q": "一家店有红色和蓝色两种气球，红色 15 个，蓝色 22 个，卖掉了 10 个红色气球，红色气球还剩几个？", "a": "5"},
    {"cat": "B", "q": "仓库原有 80 箱货物，今天进了 3 批共 60 箱（每批 20 箱），现在有多少箱？", "a": "140"},
    {"cat": "B", "q": "图书馆有 300 本中文书和 150 本英文书，新到了 20 本法文书，中文和英文书共有多少本？", "a": "450"},
    # C 隐藏意图: 需要理解"没说的部分"
    {"cat": "C", "q": "一个正方形的面积是 16 平方厘米，它的边长是多少？", "a": "4"},
    {"cat": "C", "q": "小明比小红高 5 厘米，小红 160 厘米，小明多高？", "a": "165"},
    {"cat": "C", "q": "一件衣服降价 20% 后是 80 元，原价是多少？", "a": "100"},
    {"cat": "C", "q": "甲 3 小时完成一项工作，甲乙合作 2 小时完成，乙单独需要几小时？", "a": "6"},
    {"cat": "C", "q": "一个数的 3 倍减去 7 等于 14，这个数是多少？", "a": "7"},
]


PROMPT_DIRECT = "直接回答，不需要解释。"
PROMPT_COT = "请一步步推理后回答，{FOLLOWUP}"


def extract_answer(text):
    """提取回答中的关键内容 (去引号/句号/空白后比较)。"""
    text = text.strip().strip("。").strip("，").strip()
    # 数字类: 提取最后一个数字
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    if nums:
        return nums[-1]
    return text


def grade(answer, expected):
    a = extract_answer(answer)
    e = extract_answer(expected)
    if a and e:
        return a == e
    return expected.lower() in answer.lower()


# ============================================================
# Mock (MOCK=1): 预置正误模式, 离线验证评估管线
#   direct: A 对 100%, B 对 60%, C 对 40%
#   CoT:    A 对 100%, B 对 40% (推理链被干扰数字带偏), C 对 60%
# ============================================================

MOCK_RATES = {
    ("direct", "A"): 1.0, ("direct", "B"): 0.6, ("direct", "C"): 0.4,
    ("cot", "A"): 1.0, ("cot", "B"): 0.4, ("cot", "C"): 0.6,
}


def mock_answer(mode, case):
    import random
    rate = MOCK_RATES[(mode, case["cat"])]
    return case["a"] if (hash(case["q"]) % 100) / 100 < rate else "不知道"


# ============================================================
# 实验
# ============================================================

def run_mode(mode):
    llm = (lambda m: mock_answer(mode, m)) if MOCK else (
        lambda m: chat([{"role": "user", "content": m}]))

    prompt_tpl = (PROMPT_DIRECT if mode == "direct"
                  else PROMPT_COT.format(FOLLOWUP="给出最终答案。"))

    stats = {"A": [0, 0], "B": [0, 0], "C": [0, 0]}
    tokens = 0
    details = []
    for case in CASES:
        prompt = f"{case['q']}\n{prompt_tpl}"
        start = time.time()
        if MOCK:
            answer = mock_answer(mode, case)
        else:
            answer = llm(prompt)
        elapsed = time.time() - start
        tokens += len(answer)
        ok = grade(answer, case["a"])
        stats[case["cat"]][0] += ok
        stats[case["cat"]][1] += 1
        details.append((case["cat"], case["q"][:30], answer[:30], ok, elapsed))
    return stats, tokens, details


import time


def main():
    print("=" * 64)
    print(f"CoT 失效场景解剖 -- {'MOCK (离线预置)' if MOCK else '真实模式'}")
    print(f"题集: 15 题 (A 常识 5 / B 干扰数学 5 / C 隐藏意图 5)")
    print("=" * 64)

    results, token_counts = {}, {}
    details_by_mode = {}
    for mode in ("direct", "cot"):
        stats, tokens, details = run_mode(mode)
        results[mode] = stats
        token_counts[mode] = tokens
        details_by_mode[mode] = details

    # === 对比表 ===
    print(f"\n{'类别':<20}{'direct':>16}{'CoT':>16}{'差异':>10}")
    print("-" * 64)
    labels = {"A": "A·简单常识", "B": "B·干扰数学", "C": "C·隐藏意图"}
    for cat in ("A", "B", "C"):
        d_ok, d_total = results["direct"][cat]
        c_ok, c_total = results["cot"][cat]
        d_pct = d_ok * 100 // d_total if d_total else 0
        c_pct = c_ok * 100 // c_total if c_total else 0
        delta = c_pct - d_pct
        flag = "←CoT有害" if delta < -10 else ("←CoT有益" if delta > 10 else "")
        print(f"{labels[cat]:<20}{d_ok}/{d_total:>10}  {c_ok}/{c_total:>10}  {delta:+d}%  {flag}")

    print(f"\ntoken 消耗: direct={token_counts['direct']}  CoT={token_counts['cot']}  "
          f"(CoT {token_counts['cot'] * 100 // max(token_counts['direct'], 1)}% of direct)")

    print("\n" + "=" * 64)
    print("判断规则: 何时关 CoT")
    print("  A 类 (简单常识): 关 CoT —— 零增益 + 白花 token")
    print("  B 类 (干扰数学): 看干扰强度 —— 强干扰时 CoT 推理链被带偏, 弱干扰时 CoT 有益")
    print("  C 类 (隐藏意图): 开 CoT —— 推理链帮助理解隐含条件")
    print("  生产策略: 用分类器预判任务类型, 简单题跳过 CoT")
    print("=" * 64)

    # 失败案例详情 (真实模式)
    if not MOCK:
        print("\n--- 失败案例详情 ---")
        for mode in ("direct", "cot"):
            for cat, q, ans, ok, elapsed in details_by_mode[mode]:
                if not ok:
                    print(f"  [{mode}][{cat}] {q} → {ans}")


if __name__ == "__main__":
    main()
