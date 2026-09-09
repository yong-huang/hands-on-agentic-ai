"""
面试项目 27 — Agent 评测 Harness + LLM-as-Judge

覆盖面试题: Agent 评估框架有哪些？LLM-as-Judge 怎么设计？有什么偏见？

核心: 20 个任务双通道评分:
  可判定集 (10)  规则评分器 (数值/关键词精确判) vs LLM-Judge 0/1 -> 一致率
  开放集   (10)  仅 LLM-Judge, 带 rubric (相关性/正确性/简洁) 1-5 分
偏见实验: 同一个答案 ->
  身份偏差   标注"来自 GPT-4" vs "来自 7B 小模型"
  位置偏差   双答案对比中放前面 vs 放后面
看 Judge 打分变化, 至少复现 1 种已知偏差。
真机只跑 5 判定 + 2 开放 + 4 偏见探针 (控制调用数), 全量见离线。

运行:
  MOCK=1 python eval_judge.py    # 离线: 预置回答与评分
  python eval_judge.py           # 真实: qwen3.8 当 Judge
"""

import json, os, re, statistics, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
JUDGED_LIMIT = 5          # 真机判定题数
OPEN_LIMIT = 2            # 真机开放题数

# 可判定集: (问题, 金标准)
JUDGEABLE = [
    ("3 + 3 / 3 等于几？只报数字。", 4),
    ("闰年二月有多少天？只报数字。", 29),
    ("时速 60 公里走 30 分钟多远(公里)？只报数字。", 30),
    ("一打鸡蛋几个？只报数字。", 12),
    ("2 的 10 次方？只报数字。", 1024),
    ("100 以内最大质数？只报数字。", 97),
    ("0.5 小时几分钟？只报数字。", 30),
    ("100/4 等于几？只报数字。", 25),
    ("7 乘 8 等于几？只报数字。", 56),
    ("平年多少天？只报数字。", 365),
]

# 开放集: (任务, 评分要点)
OPEN_TASKS = [
    ("给因物流延误的客户写一句道歉话术", "诚意/原因/补偿方案"),
    ("用一句话解释什么是 Agent 循环", "准确/简洁"),
    ("把 '会议改到周四' 改写成正式通知", "正式/信息完整"),
    ("给一款记账 App 起三个名字", "相关性/易记"),
    ("向 10 岁小孩解释什么是利息", "适龄/准确"),
    ("写一句退货运费自理的客服话术(不引发不满)", "礼貌/清晰"),
    ("总结正方形和长方形的区别", "准确/简洁"),
    ("给咖啡店写一条开业朋友圈文案", "吸引力/简短"),
    ("解释为什么需要 Human-in-the-loop", "准确/有例"),
    ("用比喻说明上下文窗口限制", "形象/准确"),
]

# 预置回答 (MOCK): 可判定集 8 对 2 错
MOCK_ANSWERS = {4: "4", 29: "28", 30: "30", 12: "12", 1024: "1024",
                97: "99", 30: "30", 25: "25", 56: "56", 365: "365"}
MOCK_JUDGE01 = {4: 1, 29: 0, 30: 1, 12: 1, 1024: 1,
                97: 0, 30: 1, 25: 1, 56: 1, 365: 1}
MOCK_OPEN_SCORE = [4.5, 4.0, 4.2, 3.8, 4.1, 3.9, 4.3, 3.7, 4.4, 4.0]


def http_chat(messages, num_predict=700):
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


def extract_json(text):
    text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S)
    for m in reversed(re.findall(r"\{[^{}]*\}", text, re.S)):
        try:
            return json.loads(m)
        except json.JSONDecodeError:
            continue
    return {}


def rule_grade(answer, gold):
    nums = re.findall(r"-?\d+(?:\.\d+)?", answer.replace(",", ""))
    return bool(nums) and abs(float(nums[-1]) - float(gold)) < 1e-6


def agent_answer(q):
    if MOCK:
        return MOCK_ANSWERS.get(gold_of(q), "4")
    return http_chat([{"role": "user", "content": q + " 直接回答。"}], 300)


def gold_of(q):
    for qq, g in JUDGEABLE:
        if qq == q:
            return g
    return None


def judge_01(q, gold, answer):
    """LLM-Judge 对可判定题打 0/1。"""
    if MOCK:
        return bool(MOCK_JUDGE01.get(gold, 0))
    r = extract_json(http_chat([{"role": "user", "content":
        "评估回答是否正确。问题: {}\n标准答案: {}\n候选回答: {}\n"
        '只输出 JSON: {{"correct": 1}} 或 {{"correct": 0}}'.format(q, gold, answer)}]))
    return int(r.get("correct", 0)) == 1


def judge_open(task, answer):
    """LLM-Judge 带 rubric 打 1-5。"""
    if MOCK:
        idx = [t for t, _ in OPEN_TASKS].index(task)
        return MOCK_OPEN_SCORE[idx]
    r = extract_json(http_chat([{"role": "user", "content":
        "按 rubric 给回答打分 1-5。任务: {}\nrubric: {}\n回答: {}\n"
        '只输出 JSON: {{"score": 4}}'.format(task, "相关性/正确性/简洁", answer)}]))
    try:
        return float(r.get("score", 0))
    except (TypeError, ValueError):
        return 0.0


def bias_probe():
    """偏见实验: 同一答案换身份 / 换位置。"""
    answer = ("非常抱歉, 您的订单因物流延误未能按时送达。"
              "我们已为您申请 20 元补偿券, 并会持续跟进物流直至签收。")
    task = OPEN_TASKS[0][0]
    results = {}
    if MOCK:
        results["标注GPT-4"] = 4.6
        results["标注小模型"] = 3.4
        results["A在前"] = 4.2
        results["B在前"] = 3.5
    else:
        r = extract_json(http_chat([{"role": "user", "content":
            "任务: {}\n以下回答来自 GPT-4: {}\n按 rubric 打 1-5 分, "
            '只输出 JSON: {{"score": 4}}'.format(
                task, answer, "相关性/正确性/简洁")}]))
        results["标注GPT-4"] = float(r.get("score", 0))
        r = extract_json(http_chat([{"role": "user", "content":
            "任务: {}\n以下回答来自 7B 小模型: {}\n按 rubric 打 1-5 分, "
            '只输出 JSON: {{"score": 4}}'.format(
                task, answer, "相关性/正确性/简洁")}]))
        results["标注小模型"] = float(r.get("score", 0))
        r = extract_json(http_chat([{"role": "user", "content":
            "对比两个回答哪个更好。\n回答A: {}\n回答B: 很抱歉让您久等了。\n"
            '只输出 JSON: {{"better": "A"}} 或 {{"better": "B"}}'.format(answer)}]))
        results["A在前"] = 1.0 if r.get("better") == "A" else 0.0
        r = extract_json(http_chat([{"role": "user", "content":
            "对比两个回答哪个更好。\n回答A: 很抱歉让您久等了。\n回答B: {}\n"
            '只输出 JSON: {{"better": "A"}} 或 {{"better": "B"}}'.format(answer)}]))
        results["B在前"] = 1.0 if r.get("better") == "B" else 0.0
    return results


def main():
    print("=" * 72)
    print("评测 Harness + LLM-as-Judge -- {}".format(
        "MOCK (预置回答/评分)" if MOCK else "真实 qwen3.8 Judge"))
    print("=" * 72)

    # --- 可判定集: 规则 vs Judge 一致率 ---
    judged = JUDGEABLE if MOCK else JUDGEABLE[:JUDGED_LIMIT]
    agree = 0
    print("\n==> 可判定集 (规则 vs Judge)")
    for q, gold in judged:
        ans = agent_answer(q)
        rg = rule_grade(ans, gold)
        jg = judge_01(q, gold, ans)
        agree += (rg == jg)
        print("  gold={:<5} ans={:<8} 规则={} judge={} {}".format(
            gold, ans[:8], int(rg), int(jg), "✓" if rg == jg else "✗ 不一致"))
    rate = agree * 100 // len(judged)
    print("一致率: {}/{} = {}% (验收 >=80%) {}".format(
        agree, len(judged), rate, "✓" if rate >= 80 else "✗"))

    # --- 开放集: 仅 Judge ---
    opens = OPEN_TASKS if MOCK else OPEN_TASKS[:OPEN_LIMIT]
    print("\n==> 开放集 (LLM-Judge rubric 1-5)")
    scores = []
    for task, rubric in opens:
        if MOCK:
            s = judge_open(task, "")
        else:
            ans = http_chat([{"role": "user", "content": task}])
            s = judge_open(task, ans)
        scores.append(s)
        print("  {:<24} -> {}".format(task[:24], s))
    print("均值: {}".format(round(statistics.mean(scores), 2)))

    # --- 偏见实验 ---
    print("\n==> 偏见实验 (同一答案)")
    r = bias_probe()
    id_gap = abs(r["标注GPT-4"] - r["标注小模型"])
    pos_bias = (r["A在前"] != r["B在前"])
    print("  身份偏差: GPT-4={} vs 小模型={} -> 分差 {} {}".format(
        r["标注GPT-4"], r["标注小模型"], round(id_gap, 2),
        "✓ 复现" if id_gap >= 0.5 else "· 不明显"))
    print("  位置偏差: A在前选A={} B在前选B={} -> {}".format(
        r["A在前"], r["B在前"], "✓ 复现(位置翻转选择)" if pos_bias else "· 不明显"))

    print("""
要点: LLM-as-Judge 的设计与偏见
  1) 双通道设计: 能规则判定的绝不劳烦 Judge; Judge 只处理开放集,
     且必须带 rubric (维度+分值定义), 否则打分不可复现。
  2) 已知偏见要实测: 身份偏差 (名牌模型得分虚高) / 位置偏差
     (对比时先者占优) / 冗长偏差 —— 拿同一答案换标签即可复现。
  3) 缓解: 匿名化来源、随机化位置、多次取样取均值; 关键评测仍以
     规则/人工为准, Judge 分数只做排序不做绝对结论。
""")


if __name__ == "__main__":
    main()
