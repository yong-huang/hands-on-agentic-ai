"""
面试项目 13 — 规划失败检测与重规划

覆盖面试题: 怎么处理规划失败？

核心: 团建组织管线 (5 个子目标), 注入 3 类失败各 1 次:
  ① 工具瞬断   场地查询超时           → 响应: 重试 (第 2 次成功)
  ② 前提失效   大巴 20 座车型无货      → 响应: 改路 (改订 2 辆 10 座)
  ③ 规划错误   餐厅预算分配 3000 超过剩余额度 2000 → 响应: 全局重规划
每步有断言式校验器 (结果形状/语义), 失败按错误签名分类到
RETRY / ALTERNATIVE / REPLAN 三种响应, 输出完整决策轨迹日志。
真机模式追加 LLM 分类器: 把失败结果交给 qwen 判断类别, 与规则对照。

运行:
  MOCK=1 python replan.py    # 离线: 注入故障全规则处置
  python replan.py           # 真实: 追加 LLM 失败分类对照
"""

import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
REMAINING_BUDGET = 2000


def http_chat(messages, num_predict=900):
    body = {"model": MODEL, "messages": messages, "temperature": 0.0,
            "max_tokens": num_predict}
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    return re.sub(r"<think>.*?</think>\s*", "", msg.get("content") or "",
                  flags=re.S).strip() or (msg.get("reasoning") or "")


def extract_json(text):
    text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S)
    for pat in (r"\{[^{}]*\}",):
        for m in reversed(re.findall(pat, text, re.S)):
            try:
                return json.loads(m)
            except json.JSONDecodeError:
                continue
    return None


# ============================================================
# 工具 (带故障注入)
# ============================================================

FAULTS = {"venue_timeout": True}     # ① 第 1 次查询超时
ATTEMPTS = {}


def tool_query_venue(_):
    n = ATTEMPTS.get("venue", 0) + 1
    ATTEMPTS["venue"] = n
    if FAULTS["venue_timeout"] and n == 1:
        return "ERROR: 场地查询超时 (504)"
    return "场地「湖畔厅」预订成功, ¥1200"


def tool_book_bus(seats):
    if int(seats) >= 20:
        return "ERROR: 无 20 座大巴可用"
    return f"{seats} 座中巴预订成功 ×2, 共 ¥800"


def tool_book_restaurant(cost):
    if int(cost) > REMAINING_BUDGET:
        return f"WARNING: 餐厅套餐 ¥{cost} 超过剩余额度 ¥{REMAINING_BUDGET}"
    return f"餐厅预订成功, ¥{cost}"


def tool_verify(_):
    return "总支出 ¥2800 / 总预算 ¥4000, ✓ 通过"


# ============================================================
# 规划: 子目标 = (描述, 动作, 断言校验器, 替代动作)
# ============================================================

def v_ok(res):
    return not res.startswith(("ERROR", "WARNING"))


def v_budget_alloc(res):
    """③ 规划错误: 结果形状正常但语义违规 (超额) —— 断言式校验抓语义。"""
    return "WARNING" not in res


PLAN = [
    {"id": 1, "desc": "查天气", "run": lambda alt: "晴 22°C", "check": v_ok,
     "alt": None, "classify": None},
    {"id": 2, "desc": "订场地(湖畔厅)", "run": lambda alt: tool_query_venue(alt),
     "check": v_ok, "alt": None,
     "classify": lambda res: "RETRY"},            # ① 超时 → 重试
    {"id": 3, "desc": "订 20 座大巴", "run": lambda alt: tool_book_bus(20),
     "check": v_ok,
     "classify": lambda res: "ALTERNATIVE",        # ② 无货 → 改路
     "alt_run": lambda: tool_book_bus(10)},
    {"id": 4, "desc": "订餐厅(套餐¥3000)", "run": lambda alt: tool_book_restaurant(3000),
     "check": v_budget_alloc,
     "classify": lambda res: "REPLAN"},            # ③ 规划本身错 → 全局重规划
    {"id": 5, "desc": "预算校验", "run": lambda alt: tool_verify(alt), "check": v_ok,
     "classify": None},
]

REPLAN_TAIL = [                                  # 重规划后的替代尾部
    {"id": "4'", "desc": "订餐厅(套餐¥1800, 重规划降档)", "run": lambda alt:
        tool_book_restaurant(1800), "check": v_ok, "classify": None},
    {"id": "5'", "desc": "预算校验(重算)", "run": lambda alt: tool_verify(alt),
     "check": v_ok, "classify": None},
]


# ============================================================
# 执行循环: 校验 → 分类 → 三种响应
# ============================================================

def execute(plan, log):
    i, results = 0, []
    while i < len(plan):
        step = plan[i]
        res = step["run"](None)
        if step["check"](res):
            log.append(f"[step {step['id']}] {step['desc']} -> {res}  ✓")
            results.append(res)
            i += 1
            continue
        # --- 失败处理 ---
        category = step.get("classify", lambda r: "RETRY")(res) if MOCK else None
        if not MOCK:
            category = llm_classify(step["desc"], res)
        log.append(f"[step {step['id']}] {step['desc']} -> {res}  ✗ "
                   f"校验失败, 分类={category}")
        if category == "RETRY":
            res2 = step["run"](None)
            ok2 = step["check"](res2)
            log.append(f"           ↳ 响应[重试] 第 2 次尝试 -> {res2}  "
                       f"{'✓' if ok2 else '✗'}")
            if ok2:
                results.append(res2)
                i += 1
            else:
                log.append("           ↳ 重试仍失败, 中止")
                return False
        elif category == "ALTERNATIVE":
            res2 = step["alt_run"]()
            ok2 = step["check"](res2)
            log.append(f"           ↳ 响应[改路] 切换替代动作 -> {res2}  "
                       f"{'✓' if ok2 else '✗'}")
            if ok2:
                results.append(res2)
                i += 1
            else:
                return False
        else:  # REPLAN
            log.append("           ↳ 响应[重规划] 前提变化, 重新生成剩余计划:")
            plan = plan[:i] + REPLAN_TAIL          # 全局重排剩余子目标
            log.append("             " + " -> ".join(s["desc"][:12]
                                                     for s in REPLAN_TAIL))
    return True


CATEGORY_RULE = ("RETRY: 超时/503/限流等瞬断; ALTERNATIVE: 无可用/无货/不可达"
                 "等前提失效, 可换替代方案; REPLAN: 结果表面正常但违反预算/约束,"
                 "是规划本身的问题")


def llm_classify(desc, res):
    r = extract_json(http_chat([{"role": "user", "content":
        f"子目标「{desc}」执行结果: {res}\n失败三分类: {CATEGORY_RULE}\n"
        '只输出 JSON: {"category": "RETRY|ALTERNATIVE|REPLAN"}'}]))
    return (r or {}).get("category", "REPLAN")


def main():
    print("=" * 72)
    print(f"规划失败检测与重规划 -- {'MOCK (注入 3 类失败)' if MOCK else '真实 qwen3.8 分类器'}")
    print("=" * 72)

    log = []
    print("\n==> 执行团建管线 (注入: ①超时 ②无货 ③预算分配错误)")
    ok = execute(PLAN, log)
    for line in log:
        print("  " + line)
    print(f"\n管线{'✓ 全部完成' if ok else '✗ 失败'}")

    # 三种响应的达成核对
    joined = "\n".join(log)
    checks = [("①超时→重试", "响应[重试]" in joined and "第 2 次尝试" in joined),
              ("②无货→改路", "响应[改路]" in joined),
              ("③规划错→重规划", "响应[重规划]" in joined),
              ("最终完成", ok)]
    print("\n" + "=" * 72)
    for name, okc in checks:
        print(f"  {name:<16} {'✓' if okc else '✗'}")

    if not MOCK:
        print("\n==> LLM 分类器对照 (规则 vs 模型)")
        demo = [("订场地超时(504)", "RETRY"), ("无 20 座大巴可用", "ALTERNATIVE"),
                ("餐厅 ¥3000 超过剩余额度 ¥2000", "REPLAN")]
        for res, rule_cat in demo:
            llm_cat = llm_classify("团建子目标", res)
            print(f"  {res[:24]:<26} 规则={rule_cat:<12} LLM={llm_cat} "
                  f"{'✓' if llm_cat == rule_cat else '✗'}")

    print("""
要点: 规划失败怎么处理
  1) 先校验再行动: 每个子目标都要有断言式校验器 (形状 + 语义两层),
     表面正常但违反约束 (超额) 是最隐蔽的失败。
  2) 失败分类决定响应: 瞬断→重试, 前提失效→改路(替代动作),
     规划错误→全局重规划。一律重试会把错误计划执行三遍。
  3) 重规划 ≠ 从头再来: 只重排受影响的剩余子目标, 已完成结果复用
     (与项目 31 断点续跑同一思想)。
""")


if __name__ == "__main__":
    main()
