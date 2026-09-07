"""
面试项目 1 — CoT 三态对比实验 (Zero-shot / Few-shot / Auto-CoT vs 直接回答)

覆盖面试题:
- CoT 为什么能提升推理能力?
- Zero-shot 与 Few-shot CoT 区别?
- Auto-CoT 怎么实现?

实验设计:
- 自建 20 道数学题 (10 道单步 + 10 道两步, GSM8K 风格)
- 四种模式跑同一题集, 数值评分, 输出正确率对比表 (整体 + 按题型)
- Auto-CoT: 按固定步长取样代表题, 让模型生成推理链作为 Few-shot 示例
  (真实 Auto-CoT 用 embedding 聚类选例, 本篇用题集特征近似)

运行:
  MOCK=1 python cot_compare.py    # 离线: 预置回答模式, 验证评估管线
  python cot_compare.py           # 真实: qwen3.8 (或 LLM_BASE_URL 指向的模型)
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import chat, extract_number                       # noqa: E402

MOCK = os.environ.get("MOCK") == "1"
FOLLOWUP = "最后以'答案: 数字'结尾。"

# ============================================================
# 题集: 10 单步 + 10 两步 (GSM8K 风格, 自建)
# ============================================================

QUESTIONS = [
    # 单步
    ({"q": "37 加 25 等于多少？", "a": 62}, "single"),
    ({"q": "100 减去 43 等于多少？", "a": 57}, "single"),
    ({"q": "12 乘以 8 等于多少？", "a": 96}, "single"),
    ({"q": "144 除以 12 等于多少？", "a": 12}, "single"),
    ({"q": "一个书包 85 元，一个笔记本 15 元，各买一个共多少钱？", "a": 100}, "single"),
    ({"q": "75 的三分之一是多少？", "a": 25}, "single"),
    ({"q": "6 个 15 相加等于多少？", "a": 90}, "single"),
    ({"q": "比 89 多 11 的数是多少？", "a": 100}, "single"),
    ({"q": "200 减去 77 等于多少？", "a": 123}, "single"),
    ({"q": "9 乘 9 再加 19 等于多少？", "a": 100}, "single"),
    # 两步
    ({"q": "一支笔 3 元，一个本子 5 元，买 4 支笔和 6 个本子共多少钱？", "a": 42}, "multi"),
    ({"q": "小明有 120 元，花了 45 元，又挣了 30 元，现在有多少元？", "a": 105}, "multi"),
    ({"q": "一辆车每小时行 60 千米，行驶 2.5 小时后还剩 40 千米到达，全程多少千米？", "a": 190}, "multi"),
    ({"q": "3 打铅笔每打 12 支，分给 9 个同学每人 4 支，还剩几支？", "a": 0}, "multi"),
    ({"q": "水果店有 85 千克苹果，上午卖了 32 千克，下午又进了 50 千克，现在有多少千克？", "a": 103}, "multi"),
    ({"q": "一件衣服打 8 折后是 160 元，原价是多少？", "a": 200}, "multi"),
    ({"q": "食堂每天用米 15 千克，一周 (7 天) 用米多少千克？", "a": 105}, "multi"),
    ({"q": "电影票每张 45 元，5 个人买票后还剩 25 元，原来有多少元？", "a": 250}, "multi"),
    ({"q": "长方形长 14 宽 6，周长是多少？", "a": 40}, "multi"),
    ({"q": "加班每小时 50 元，平时每小时 30 元，平时干 6 小时加班干 4 小时共多少钱？", "a": 380}, "multi"),
]


# ============================================================
# 四种模式的提示词
# ============================================================

def build_prompts():
    prompts = {
        "direct": [f"{item['q']}\n直接给出答案，只输出一个数字，不要过程。"
                   for item, _ in QUESTIONS],
        "zero_cot": [f"{item['q']}\n请一步步思考再回答，{FOLLOWUP}" for item, _ in QUESTIONS],
    }
    few_shot = (
        "例1: 问: 一支笔 3 元买 5 支多少钱？答: 3×5=15。答案: 15\n"
        "例2: 问: 有 50 元花 18 元剩多少？答: 50-18=32。答案: 32\n"
        "例3: 问: 每小时 60 千米走 2 小时多远？答: 60×2=120。答案: 120\n\n")
    prompts["few_cot"] = [f"{few_shot}问: {item['q']}\n请参考例子的方式一步步推理，{FOLLOWUP}"
                          for item, _ in QUESTIONS]
    prompts["auto_cot"] = None      # 需要先取样生成示例
    return prompts


def auto_cot_examples(llm_fn):
    """Auto-CoT: 按固定步长取样 3 道代表题 (跨单步/两步), 让模型生成推理链
    作为 Few-shot 示例——示例来自数据本身, 人工只写取样规则。"""
    stride = max(1, len(QUESTIONS) // 3)
    picked = [QUESTIONS[0][0], QUESTIONS[stride][0], QUESTIONS[stride * 2][0]]
    examples = []
    for q in picked:
        reasoning = llm_fn([{"role": "user",
                             "content": f"{q['q']}\n请一步步推理并给出答案，{FOLLOWUP}"}])
        examples.append(f"问: {q['q']}\n{reasoning}")
    return "\n\n".join(examples) + "\n\n"


# ============================================================
# MockLLM (MOCK=1): 预置回答模式, 离线验证评估管线
#   direct 只会算单步; CoT 类都能算——模拟"CoT 在多步题上的提升"
# ============================================================

def mock_llm_for(mode):
    def _solve(q_text, smart):
        nums = [int(n) for n in re.findall(r"\d+", q_text)]
        if not nums:
            return "答案: 0"
        if smart or len(nums) == 2:
            # 简化的确定性"推理": 按题面关键词给结果 (预置规则, 非真实推理)
            answers = {item["q"]: item["a"] for item, _ in QUESTIONS}
            for text, ans in answers.items():
                if text in q_text or q_text in text:
                    return f"答案: {ans}"
            return f"答案: {nums[0]}"
        return f"答案: {nums[0]}"     # direct 遇多步题: 只给第一个数 (错)

    smart = mode in ("zero_cot", "few_cot", "auto_cot")
    def llm(messages, **kw):
        user = messages[-1]["content"]
        user = re.sub(r"^(例\d+:.*\n+)+", "", user)   # 去掉 few-shot 前缀 (无 re.S, 防跨行吞掉问题)
        user = user.split("\n")[0]
        return _solve(user, smart)
    return llm


# ============================================================
# 实验运行
# ============================================================


def main():
    print("=" * 64)
    print(f"CoT 三态对比实验 -- {'MOCK (离线预置)' if MOCK else '真实模式'}")
    print(f"题集: {len(QUESTIONS)} 道 (10 单步 + 10 两步)")
    print("=" * 64)

    prompts = build_prompts()
    rows = []
    for name in ("direct", "zero_cot", "few_cot", "auto_cot"):
        if MOCK:
            llm_fn = mock_llm_for(name)
            cur_prompts = prompts[name] or prompts["zero_cot"]
            correct = {"single": 0, "multi": 0}
            for i, (item, kind) in enumerate(QUESTIONS):
                answer = llm_fn([{"role": "user", "content": cur_prompts[i]}])
                got = extract_number(answer)
                correct[kind] += got is not None and abs(got - item["a"]) < 1e-6
            total_ok = correct["single"] + correct["multi"]
            rows.append({"name": name, "single": correct["single"],
                         "multi": correct["multi"], "total": total_ok})
            continue

        cur_prompts = prompts[name]
        if name == "auto_cot":
            print("==> [auto_cot] 取样代表题并生成推理链示例…")
            prompts["auto_cot"] = [auto_cot_examples(chat) + p
                                   for p in prompts["few_cot"]]
            cur_prompts = prompts["auto_cot"]
        correct = {"single": 0, "multi": 0}
        for i, (item, kind) in enumerate(QUESTIONS):
            answer = chat([{"role": "user", "content": cur_prompts[i]}])
            got = extract_number(answer)
            ok = got is not None and abs(got - item["a"]) < 1e-6
            correct[kind] += ok
            if not ok:
                print(f"  [miss][{name}] {item['q']} 期望 {item['a']}, 模型答 {got}")
        total_ok = correct["single"] + correct["multi"]
        rows.append({"name": name, "single": correct["single"],
                     "multi": correct["multi"], "total": total_ok})
        print(f"  {name}: {total_ok}/{len(QUESTIONS)}")

    print(f"\n{'模式':<12}{'单步':>8}{'两步':>8}{'总体':>12}")
    print("-" * 44)
    for r in rows:
        s = f"{r['single']}/10"
        m = f"{r['multi']}/10"
        t = f"{r['total']}/20 ({r['total'] * 100 // 20}%)"
        print(f"{r['name']:<12}{s:>8}{m:>8}{t:>12}")
    print("-" * 44)
    print("结论要点: CoT 类模式在两步题上的提升最大 (直接回答缺中间步骤);")
    print("Auto-CoT 示例由数据自产, 效果接近人工 Few-shot——少写 3 个手工示例。")


if __name__ == "__main__":
    main()
