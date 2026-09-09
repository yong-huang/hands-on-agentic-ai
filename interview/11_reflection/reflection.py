"""
面试项目 11 — Reflection 反思机制

覆盖面试题: Generative Agents 中的 Reflection 机制怎么工作？

核心: 客服场景事件流 (9 条记忆, 含用户消息与客服动作), 每完成 N=3 个动作
触发一次反思: 把近期记忆归纳为高层洞察 (insight), 按 重要性×新近性 衰减打分
入库 —— Generative Agents 的核心循环。最终用同一个模糊问题对比:
  无 Reflection: 只检索原始记忆 (流水账)        → 回答空泛
  有 Reflection: 洞察 + 原始记忆一起检索        → 回答引用洞察, 指向行动
指标: 洞察被后续回答引用次数 (≥2 达标) + 质量评分 (真机用 LLM-as-Judge)。

运行:
  MOCK=1 python reflection.py    # 离线: 预置洞察与回答
  python reflection.py           # 真实: qwen3.8 做反思、作答与评分
"""

import json, math, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
REFLECT_EVERY = 3          # 每 3 条记忆触发一次反思
HALF_LIFE_H = 72           # 新近性半衰期 (小时)
SYSTEM = "你是资深客服主管, 根据给出的记忆给出具体可执行的建议。"


def http_chat(messages, num_predict=1200):
    body = {"model": MODEL, "messages": messages, "temperature": 0.0,
            "max_tokens": num_predict}
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    content = re.sub(r"<think>.*?</think>\s*", "", msg.get("content") or "",
                     flags=re.S).strip()
    return content or (msg.get("reasoning") or "").strip()


def extract_json(text):
    text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S)
    for pat in (r"\[[^\[\]]*\]", r"\{[^{}]*\}"):
        for m in reversed(re.findall(pat, text, re.S)):
            try:
                return json.loads(m)
            except json.JSONDecodeError:
                continue
    return None


# ============================================================
# 客服场景事件流: (文本, 重要性1-10, 距今小时数, 类型)
# ============================================================

MEMORIES = [
    ("用户下单订单 A1002, 备注尽快发货",            4, 48, "事件"),
    ("[动作] 查询订单 A1002: 物流滞留中转站",        6, 40, "动作"),
    ("用户来电催单, 语气焦急",                     7, 36, "事件"),
    ("[动作] 查询物流: A1002 预计延误 3 天",        6, 30, "动作"),
    ("用户来电抱怨: 自己是 VIP 客户, 不能接受延误",   8, 24, "事件"),
    ("[动作] 发放 20 元优惠券作为补偿",              5, 18, "动作"),
    ("用户再次来电: 优惠券没用, 要求给确定方案",      8, 12, "事件"),
    ("[动作] 升级至高级客服工单",                   6, 6,  "动作"),
    ("用户资料: 偏好电话联系",                      5, 1,  "事件"),
]

# MOCK 预置洞察 (真机由 LLM 归纳)
MOCK_INSIGHTS = [
    ({"insight": "客户因 A1002 延误来电催单, 情绪焦急, 需主动同步物流进展",
      "importance": 6}, 10),
    ({"insight": "VIP 客户对 A1002 延误强烈不满, 20 元优惠券补偿无效, "
                 "需要给出确定性方案", "importance": 9}, 6),
    ({"insight": "该用户偏好电话沟通, 后续处理应主动电话回访",
      "importance": 7}, 1),
]


def recency_score(hours_ago):
    """Generative Agents 式新近性: 指数衰减, 半衰期 72 小时。"""
    return 0.5 ** (hours_ago / HALF_LIFE_H)


def retrieve(memories, k=4):
    scored = sorted(((m[1] * recency_score(m[2]), m) for m in memories),
                    reverse=True)
    return [m for _, m in scored[:k]]


def reflect(memories, n_existing_insights):
    """每 N 条记忆触发: 归纳近期记忆为高层洞察, LLM 同步打重要性分。"""
    if MOCK:
        ins, _ = MOCK_INSIGHTS[n_existing_insights % len(MOCK_INSIGHTS)]
        return ins
    recent = "\n".join(f"- {m[0]}" for m in memories[-REFLECT_EVERY:])
    r = extract_json(http_chat([{"role": "user", "content":
        f"以下是客服会话的近期记忆:\n{recent}\n\n"
        "归纳出 1 条高层洞察(客户是谁/核心诉求/什么有效什么无效), "
        '并打重要性分 1-10。只输出 JSON: {"insight": "...", "importance": 8}'}]))
    if not r or not r.get("insight"):
        return {"insight": "(反思失败, 保留原始记忆)", "importance": 3}
    return r


def build_context(memories, insights, k=4):
    """有 Reflection: 洞察(高重要性) + 原始记忆一起按分数检索。"""
    pool = [(m[1] * recency_score(m[2]), f"[原始] {m[0]}") for m in memories]
    pool += [(ins["importance"] * recency_score(h), f"[洞察] {ins['insight']}")
             for ins, h in insights]
    pool.sort(key=lambda x: -x[0])
    return "\n".join(t for _, t in pool[:k])


QUESTION = "客户又发消息来了, 我现在该怎么处理？"


def answer(context, mode):
    if MOCK:
        if mode == "reflect":
            return ("建议立即电话回访这位 VIP 客户, 就 A1002 延误给出确定性方案"
                    "(如加急转空运+超额补偿), 不要再发优惠券。")
        return "建议先安抚用户情绪, 跟进工单进展, 有消息及时同步。"
    return http_chat([{"role": "system", "content": SYSTEM},
                      {"role": "user", "content":
                       f"记忆如下:\n{context}\n\n{QUESTION}"}], num_predict=600)


def judge(question, ans):
    if MOCK:
        ref = count_refs(ans)
        return round(2.0 + ref * 1.2, 1)          # 引用洞察越多分越高
    score_txt = http_chat([{"role": "user", "content":
        f"问题: {question}\n回答: {ans}\n\n按 rubric 打分(1-5): 是否结合了用户"
        "历史(身份/偏好/无效方案)、是否给出具体可执行动作、是否避免空话。"
        '只输出 JSON: {"score": 4, "reason": "..."}'}], num_predict=1800)
    r = extract_json(score_txt) or {}
    try:
        return float(r.get("score", 0))
    except (TypeError, ValueError):
        pass
    m = re.search(r"score[^0-9]{0,6}([0-5](?:\.\d)?)", score_txt)
    return float(m.group(1)) if m else 0.0


def count_refs(ans):
    """洞察引用计数: 电话偏好 + VIP/优惠券 无效 这两条洞察各算一次。"""
    refs = 0
    if "电话" in ans:
        refs += 1
    if any(k in ans for k in ("VIP", "优惠券", "A1002")):
        refs += 1
    return refs


def main():
    print("=" * 72)
    print(f"Reflection 反思机制 -- {'MOCK (离线)' if MOCK else '真实 qwen3.8'}")
    print(f"事件流 {len(MEMORIES)} 条 | 每 {REFLECT_EVERY} 条触发反思 | "
          f"新近性半衰期 {HALF_LIFE_H}h")
    print("=" * 72)

    # --- 无 Reflection: 只有原始记忆 ---
    print("\n==> 模式 A: 无 Reflection (只检索原始记忆)")
    for m in MEMORIES:
        print(f"  · {m[0]}  (imp={m[1]}, {m[2]}h前)")
    ctx_a = "\n".join(f"[原始] {m[0]}" for m in retrieve(MEMORIES))
    print(f"  检索 Top4: {[m[0][:14] for m in retrieve(MEMORIES)]}")
    ans_a = answer(ctx_a, "baseline")

    # --- 有 Reflection: 每 N 条触发归纳 ---
    print(f"\n==> 模式 B: 有 Reflection (每 {REFLECT_EVERY} 条归纳洞察)")
    memories, insights = [], []
    for i, m in enumerate(MEMORIES, 1):
        memories.append(m)
        if i % REFLECT_EVERY == 0:
            ins = reflect(memories, len(insights))
            hours = max(1, MEMORIES[i - 1][2] - 1)
            insights.append((ins, hours))
            print(f"  [反思 #{len(insights)}] {ins['insight']}  (imp={ins['importance']})")
    ctx_b = build_context(memories, insights)
    print(f"  最终上下文:\n{ctx_b}")
    ans_b = answer(ctx_b, "reflect")

    # --- 对比评估 ---
    refs_a, refs_b = count_refs(ans_a), count_refs(ans_b)
    print("\n" + "=" * 72)
    print(f"{'模式':<16}{'回答':<46}{'洞察引用':>8}{'Judge':>8}")
    print("-" * 80)
    print(f"{'A 无Reflection':<16}{ans_a[:44]:<46}{refs_a:>6}{judge(QUESTION, ans_a):>8}")
    print(f"{'B 有Reflection':<16}{ans_b[:44]:<46}{refs_b:>6}{judge(QUESTION, ans_b):>8}")
    print("-" * 80)
    print(f"洞察引用达标(≥2): {'✓' if refs_b >= 2 else '✗'}   "
          f"质量提升: {judge(QUESTION, ans_b) - judge(QUESTION, ans_a):+.1f}")
    print("""
要点: Generative Agents 的 Reflection 机制
  1) 触发器: 每累计 N 条记忆反思一次, 把流水账蒸馏成高层洞察。
  2) 打分: 重要性(该洞察多关键) × 新近性(指数衰减) 决定检索权重,
     洞察与原始记忆同池竞争——不是替换, 是分层。
  3) 价值: 原始记忆回答"发生过什么", 洞察回答"客户是谁、什么有效"。
     模糊问题(该怎么办)下, 有洞察的回答直接指向行动。
""")


if __name__ == "__main__":
    main()
