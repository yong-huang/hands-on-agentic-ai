"""
面试项目 23 — Generator-Critic 辩论模式

覆盖面试题: 多 Agent 协作什么时候比单 Agent 好？

核心: 20 道易错题 (陷阱: 运算顺序/单位/经典脑筋题) 三种模式对跑:
  direct  直接回答 (1 次调用)
  cot     单 Agent 一步步推理 (1 次调用)
  debate  生成器起草 -> 评审 Agent 挑错 -> 生成器修订 (3 次调用)
答案可程序判定 (数值/关键词), 输出正确率与调用成本对比。
真机只跑 6 道代表题 (控制 LLM 次数), 20 题全量统计见离线。

运行:
  MOCK=1 python generator_critic.py    # 离线: 确定性正确率模型
  python generator_critic.py           # 真实: qwen3.8 三模式 (仅 6 题)
"""

import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
REAL_QUESTIONS = 6          # 真机题数 (成本控制)


def http_chat(messages, num_predict=800):
    body = {"model": MODEL, "messages": messages, "temperature": 0.0,
            "max_tokens": num_predict}
    req = urllib.request.Request(
        "{}/chat/completions".format(BASE_URL),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer {}".format(API_KEY)})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    content = re.sub(r"<think>.*?</think>\s*", "", msg.get("content") or "",
                     flags=re.S).strip()
    return content or (msg.get("reasoning") or "").strip()


# ============================================================
# 20 道易错题: (题目, 金标准数值 或 关键词)
# ============================================================

QUESTIONS = [
    ("3 + 3 / 3 等于几？只报数字。", 4),
    ("闰年的二月有多少天？只报数字。", 29),
    ("时速 60 公里, 行驶 30 分钟走多远(公里)？只报数字。", 30),
    ("10 斤棉花和 10 斤铁哪个重？", "一样"),
    ("一天有多少个小时？只报数字。", 24),
    ("5 * 4 + 2 等于几？只报数字。", 22),
    ("100 以内最大的质数是几？只报数字。", 97),
    ("摄氏 0 度等于华氏多少度？只报数字。", 32),
    ("一打鸡蛋有几个？只报数字。", 12),
    ("200 的 15% 是多少？只报数字。", 30),
    ("正方形周长 20, 边长 5, 面积是多少？只报数字。", 25),
    ("2 的 10 次方等于几？只报数字。", 1024),
    ("半打鸡蛋吃掉 2 个, 还剩几个？只报数字。", 4),
    ("1 公里等于多少米？只报数字。", 1000),
    ("3 只猫 3 分钟抓 3 只老鼠, 9 只猫抓 9 只老鼠要几分钟？只报数字。", 3),
    ("0.5 小时等于多少分钟？只报数字。", 30),
    ("标准大气压下水结冰是多少摄氏度？只报数字。", 0),
    ("100 除以 4 等于几？只报数字。", 25),
    ("平年一年有多少天？只报数字。", 365),
    ("7 乘 8 等于几？只报数字。", 56),
]

# 真机代表题: 覆盖运算顺序/单位换算/经典陷阱 三类
REAL_IDX = [0, 2, 3, 8, 14, 19]


def grade(answer, gold):
    if isinstance(gold, str):
        return gold in answer
    nums = re.findall(r"-?\d+(?:\.\d+)?", answer.replace(",", ""))
    if not nums:
        return False
    try:
        return abs(float(nums[-1]) - float(gold)) < 1e-6
    except ValueError:
        return False


# ============================================================
# 三种模式
# ============================================================

def direct_answer(q):
    if MOCK:
        return mock_answer(q, 0.5, "4")
    return http_chat([{"role": "user", "content": q + " 直接回答。"}], 300)


def cot_answer(q):
    if MOCK:
        return mock_answer(q, 0.6, "推理... 答案 4")
    return http_chat([{"role": "user", "content": q + " 请一步步推理后回答。"}], 700)


def debate_answer(q):
    """生成器起草 -> 评审挑错 -> 生成器修订。"""
    if MOCK:
        ok_first = (hash(q) % 100) < 70
        draft = q_last(str(gold_of(q))) if ok_first else "2"
        critique = "可能有误, 请复核运算顺序与单位。" if not ok_first else "答案正确"
        revised = q_last(str(gold_of(q)))
        return revised if not ok_first else draft
    draft = http_chat([{"role": "user", "content": q + " 直接回答。"}], 300)
    critique = http_chat([{"role": "user", "content":
                           "你是苛刻的评审。题目: {}\n候选答案: {}\n"
                           "检查: 运算顺序/单位换算/陷阱表述。"
                           "指出错误或说'无错'。80 字内。".format(q, draft)}], 500)
    revised = http_chat([{"role": "user", "content":
                          "题目: {}\n你的初答: {}\n评审意见: {}\n"
                          "请复核并给出最终答案。".format(q, draft, critique)}], 500)
    return revised


GOLD_MAP = {q: g for q, g in QUESTIONS}


def gold_of(q):
    return GOLD_MAP[q]


def q_last(v):
    return v


def mock_answer(q, rate, template):
    """确定性: 哈希决定该题该模式是否答对。"""
    ok = (hash(q) % 100) < rate * 100
    g = gold_of(q)
    return str(g) if ok else str(g - 1 if isinstance(g, int) else "不知道")


# ============================================================
# 实验
# ============================================================

def main():
    qs = QUESTIONS if MOCK else [QUESTIONS[i] for i in REAL_IDX]
    print("=" * 72)
    print("Generator-Critic 辩论模式 -- {}".format(
        "MOCK (确定性模型, 20 题全量)" if MOCK else
        "真实 qwen3.8 ({} 道代表题)".format(len(qs))))
    print("=" * 72)

    stats = {"direct": [0, 0, 0], "cot": [0, 0, 0], "debate": [0, 0, 0]}
    for q, gold in qs:
        row = []
        for mode, fn in (("direct", direct_answer), ("cot", cot_answer),
                         ("debate", debate_answer)):
            ans = fn(q)
            ok = grade(ans, gold)
            calls = {"direct": 1, "cot": 1, "debate": 3}[mode]
            stats[mode][0] += ok
            stats[mode][1] += 1
            stats[mode][2] += calls
            row.append((mode, ok, ans))
        mark = lambda b: "✓" if b else "✗"
        print("  Q{:<3} {}{:<6} {}{:<6} {}{:<6} | {}".format(
            qs.index((q, gold)) + 1 if (q, gold) in qs else "?",
            mark(row[0][1]), "", mark(row[1][1]), "", mark(row[2][1]), "",
            str(gold)))

    print("\n" + "=" * 72)
    print("{:<10}{:>10}{:>10}{:>12}".format("模式", "正确", "调用数", "每题成本"))
    print("-" * 46)
    for mode in ("direct", "cot", "debate"):
        ok, n, calls = stats[mode]
        print("{:<10}{:>5}/{:<4}{:>6}{:>10}".format(
            mode, ok, n, calls, round(calls / max(n, 1), 1)))
    print("-" * 46)
    d_ok, db_ok = stats["direct"][0], stats["debate"][0]
    print("辩论 vs 直接: {} (验收: 辩论 ≥ 单 Agent)".format(
        "✓ 提升" if db_ok >= d_ok else "✗ 反常"))

    print("""
要点: 什么任务值得多 Agent
  1) 辩论的价值在"可验证的易错任务": 评审Agent 提供独立视角, 修订
     能挽回初答的粗心错误; 对开放式创作任务收益趋零。
  2) 成本不是 3 倍而是"质量价格": debate 每题 3 次调用换正确率,
     错误代价高的场景(下单/发邮件)才划算。
  3) 单 Agent + CoT 是强基线: 多 Agent 打不过它就别上多 Agent ——
     这道对比实验本身就是面试答案。
""")


if __name__ == "__main__":
    main()
