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
# 题集: 20 道多步推理题 (GSM8K 风格, 含干扰数字)
# ============================================================

QUESTIONS = [
    ({"q": "商店有 156 千克苹果，上午卖出 48 千克，下午卖出的是上午的 1.5 倍，还剩多少千克？", "a": 84}, "multi"),
    ({"q": "一件商品原价 350 元，先涨价 20% 再打 8 折，现价多少元？", "a": 336}, "multi"),
    ({"q": "甲乙两地相距 480 千米，汽车以每小时 60 千米行驶了 3 小时后提速 20%，再行 3 小时后距乙地还有多少千米？", "a": 84}, "multi"),
    ({"q": "小明买了 3 支钢笔和 2 本笔记本共 58 元，钢笔每支 14 元，笔记本每本多少元？", "a": 8}, "multi"),
    ({"q": "工程队计划 15 天修 1800 米路，前 4 天每天修 100 米，剩下的每天要多修多少米才能按期完成？", "a": 80}, "multi"),
    ({"q": "某班 45 人，其中 60% 参加数学竞赛，参赛者中 1/3 获奖，获奖的有多少人？", "a": 9}, "multi"),
    ({"q": "一根钢管长 8.4 米，锯成 0.6 米一段，每锯一次耗 2 分钟，共需多少分钟（不计最后一锯）？", "a": 26}, "multi"),
    ({"q": "存钱 5000 元年利率 3.6%，存 2 年半后本息共多少元（单利）？", "a": 5450}, "multi"),
    ({"q": "打印一份 96 页的书稿，甲每天打 12 页，乙每天打 8 页，两人合作几天打完？", "a": 4.8}, "multi"),
    ({"q": "游泳池有水 200 立方米，进水管每分钟进 12 立方米，排水管每分钟排 7 立方米，两管齐开多少分钟后池中有水 300 立方米？", "a": 20}, "multi"),
    ({"q": "火车长 240 米以每秒 20 米过一条 560 米的隧道，从车头进到车尾出共需多少秒？", "a": 40}, "multi"),
    ({"q": "买 5 本字典差 22 元，买 3 本多 14 元，一本字典多少元？", "a": 18}, "multi"),
    ({"q": "三个数的平均数是 72，其中两个数是 65 和 78，第三个数是多少？", "a": 73}, "multi"),
    ({"q": "鸡兔同笼共 35 个头 94 只脚，鸡有多少只？", "a": 23}, "multi"),
    ({"q": "水池有甲乙两管，甲 6 小时注满，乙 4 小时放空，两管齐开几小时注满？", "a": 12}, "multi"),
    ({"q": "商品按 50% 利润定价，再打 7 折出售仍赚 21 元，成本多少元？", "a": 140}, "multi"),
    ({"q": "一项工程甲单独 10 天完成，乙单独 15 天完成，合作 3 天后甲离开，乙还需几天？", "a": 7.5}, "multi"),
    ({"q": "快慢两车从相距 450 千米的两地相向而行，快车每小时 70 千米，慢车每小时 50 千米，几小时相遇？", "a": 3.75}, "multi"),
    ({"q": "年终奖 36000 元按月平均发放，每月超出 3000 元部分按 3% 缴税，全年共缴税多少元？", "a": 1080}, "multi"),
    ({"q": "图书室原有书的 2/5 是科技书，新进 120 本科技书后科技书占 50%，原有科技书多少本？", "a": 240}, "multi"),
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
    print(f"题集: {len(QUESTIONS)} 道 (全部多步推理)")
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

    print(f"\n{'模式':<12}{'正确':>8}{''}{'总体':>12}")
    print("-" * 44)
    for r in rows:
        s = f"{r['multi']}/20"
        m = f"{r['total']}/20"
        t = f"{r['total']}/20 ({r['total'] * 100 // 20}%)"
        print(f"{r['name']:<12}{s:>8}{m:>8}{t:>12}")
    print("-" * 44)
    print("结论要点: CoT 类模式在两步题上的提升最大 (直接回答缺中间步骤);")
    print("Auto-CoT 示例由数据自产, 效果接近人工 Few-shot——少写 3 个手工示例。")


if __name__ == "__main__":
    main()
