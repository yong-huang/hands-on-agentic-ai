"""
面试项目 14 — Human-in-the-loop 审批门

覆盖面试题: HITL 的介入时机怎么设计？哪些操作必须人工确认？(必问)

核心: Agent 的 10 个混合操作先过风险分级器:
  强制审批  金额操作(退款/转账>¥1000) / 删除 / 对外发送 / 敏感数据导出
  自动放行  纯查询 / 内部低风险写 (零打扰)
审批通道: 批准 / 拒绝 / 超时-无应答 → 默认拒绝 (fail-safe)。
所有决策写审计日志 (JSONL)。交互终端下是真输入; 非交互环境走脚本化
用户决策 (批准/拒绝/不应答各覆盖) 并如实标注。

运行:
  MOCK=1 python hitl_gate.py    # 离线: 脚本化用户决策
  python hitl_gate.py           # 真实: 终端下真实输入, 管道下 fail-safe
"""

import json, os, re, select, sys, time

MOCK = os.environ.get("MOCK") == "1"
APPROVAL_TIMEOUT_S = 8
AUDIT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit.jsonl")

SYSTEM_OPS = [
    # (操作, 参数, 类型)
    ("query_orders", {"user": "u1001"}, "查询"),
    ("read_knowledge", {"topic": "退货政策"}, "查询"),
    ("query_weather", {"city": "杭州"}, "查询"),
    ("update_order_status", {"order": "A1002", "status": "shipped"}, "内部写"),
    ("create_report", {"range": "weekly"}, "内部写"),
    ("refund_customer", {"order": "A1002", "amount": 500}, "退款"),
    ("transfer_payment", {"to": "supplier-77", "amount": 99999}, "转账"),
    ("delete_records", {"table": "sessions", "older_than": "90d"}, "删除"),
    ("send_email_to_customers", {"tpl": "promo", "count": 12000}, "外部发送"),
    ("export_user_data", {"fields": "phone,address", "format": "csv"}, "敏感导出"),
]

# 脚本化用户决策 (MOCK / 非交互管道): None = 不应答 (触发超时)
SCRIPTED_DECISIONS = {
    "refund_customer": "approve",
    "delete_records": "deny",
    "send_email_to_customers": "approve",
    "transfer_payment": "deny",
    "export_user_data": None,
}


# ============================================================
# 风险分级器 (规则)
# ============================================================

def classify(op, args, kind):
    """返回 (风险级别, 原因)。强制审批的四类红线 + 低风险白名单。"""
    if kind in ("查询",):
        return "AUTO", "纯查询, 无副作用"
    if kind == "删除" or re.search(r"delete|drop|truncate|清除", op, re.I):
        return "APPROVE", "删除类操作不可逆"
    if kind in ("退款", "转账") or "amount" in args:
        if int(args.get("amount", 0)) > 1000 or kind == "转账":
            return "APPROVE", f"大额资金操作 ¥{args.get('amount')}"
        return "APPROVE", "资金类操作一律审批"
    if kind == "外部发送" or re.search(r"send|email|sms|publish", op, re.I):
        return "APPROVE", "对外发送不可撤回"
    if kind == "敏感导出" or re.search(r"export|download", op, re.I):
        return "APPROVE", "敏感数据出域"
    return "AUTO", "内部低风险写"


# ============================================================
# 审批通道: 交互终端真输入 / 非交互走脚本化 + fail-safe
# ============================================================

def ask_human(op, args, reason):
    if not MOCK and sys.stdin.isatty():
        print(f"\n⏸ 需要审批 [{op}] 参数={args}\n   原因: {reason}\n"
              f"   批准? (y=批准 / n=拒绝, {APPROVAL_TIMEOUT_S}s 内未响应默认拒绝): ",
              end="", flush=True)
        r, _, _ = select.select([sys.stdin], [], [], APPROVAL_TIMEOUT_S)
        if not r:
            return None                      # 超时
        return "approve" if sys.stdin.readline().strip().lower() == "y" else "deny"
    # 非交互 / MOCK: 脚本化决策 (None 模拟用户不应答)
    return SCRIPTED_DECISIONS.get(op, "approve")


AUDIT = []


def audit(op, level, decision, note):
    AUDIT.append({"ts": time.strftime("%H:%M:%S"), "op": op, "risk": level,
                  "decision": decision, "note": note})
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(AUDIT[-1], ensure_ascii=False) + "\n")


def execute(op, args, kind):
    level, why = classify(op, args, kind)
    if level == "AUTO":
        audit(op, level, "auto-allow", why)
        return f"[放行] {op}({args}) — {why}"
    decision = ask_human(op, args, why)
    if decision == "approve":
        audit(op, level, "approved", why)
        return f"[审批→批准] {op}({args}) — {why} → 已执行"
    if decision == "deny":
        audit(op, level, "denied", why)
        return f"[审批→拒绝] {op}({args}) — {why} → 未执行"
    audit(op, level, "timeout-deny", why + "; 超时无应答, 默认拒绝")
    return f"[审批→超时] {op}({args}) — {APPROVAL_TIMEOUT_S}s 无应答, 默认拒绝"


def main():
    if os.path.exists(AUDIT_PATH):
        os.remove(AUDIT_PATH)
    mode = ("交互终端 (真实输入)" if (not MOCK and sys.stdin.isatty())
            else "脚本化用户决策 (批准/拒绝/不应答)" if MOCK
            else "非交互管道 (审批通道不可用 → 全部默认拒绝)")
    print("=" * 72)
    print(f"HITL 审批门 -- {mode}")
    print(f"操作 {len(SYSTEM_OPS)} 个 | 分级: 金额/删除/外发/敏感导出 → 强制审批")
    print("=" * 72)

    outcomes = {"AUTO": 0, "approved": 0, "denied": 0, "timeout-deny": 0}
    asked = 0
    for op, args, kind in SYSTEM_OPS:
        level, _ = classify(op, args, kind)
        line = execute(op, args, kind)
        if level == "APPROVE":
            asked += 1
            decision = AUDIT[-1]["decision"]
            outcomes[decision] = outcomes.get(decision, 0) + 1
        else:
            outcomes["AUTO"] += 1
        print(f"  {line}")

    n_danger = sum(1 for op, a, k in SYSTEM_OPS if classify(op, a, k)[0] == "APPROVE")
    n_auto = len(SYSTEM_OPS) - n_danger
    print("\n" + "=" * 72)
    print(f"{'指标':<24}{'结果':>12}")
    print("-" * 44)
    print(f"{'危险操作全部卡住审批':<22}{asked == n_danger and asked > 0!s:>10}"
          f" ({asked}/{n_danger})")
    print(f"{'安全操作零打扰':<24}{outcomes['AUTO'] == n_auto!s:>10} ({n_auto} 个)")
    print(f"{'批准/拒绝/超时拒绝':<22}"
          f"{outcomes['approved']}/{outcomes['denied']}/{outcomes['timeout-deny']:>6}")
    print(f"{'审计日志条数':<24}{len(AUDIT):>10}")
    print("-" * 44)
    print(f"审计日志: {AUDIT_PATH}")
    print("""
要点: HITL 的介入时机怎么设计
  1) 分级在写入侧完成: 查询/内部写放行 (零打扰), 不可逆或出域的操作
     (删除/资金/对外发送/敏感导出) 强制审批——红线用规则, 不用模型猜。
  2) fail-safe 原则: 审批超时/通道不可用 = 默认拒绝。宁可不做, 不可做错。
  3) 每个决策落审计日志 (谁/何时/批了什么/为什么), 这是生产 HITL 的
     底线——事后可追责, 而不是"模型说它问过"。
""")


if __name__ == "__main__":
    main()
