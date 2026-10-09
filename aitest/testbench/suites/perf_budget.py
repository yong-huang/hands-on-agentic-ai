"""suites.perf_budget — 性能与成本门禁 (docs/aitest.md 项目 17)

跑任务集收集两个指标并按预算断言:
  延迟: 每任务墙钟耗时 -> 每轮 P50/P95 -> 多轮取中位(抗抖动)
  token: 估算值 = (喂入内容+回复) 总字符 / 4(标注为估算, 非精确计量)

预算方向均为"越低越好"; 任一超预算 exit 1, 报告标红。
--strict 把 P50 阈值压到 0.5s, 用于演示两态。

    run_perf(tasks_n=3, rounds=3, model=...) -> report dict
"""

import os
import statistics
import sys
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(os.path.dirname(HERE))
RESULTS_PATH = os.path.join(AITEST_DIR, "results", "perf_budget.json")

sys.path.insert(0, AITEST_DIR)

DEFAULT_BUDGET = {"p50_max_s": 60.0, "p95_max_s": 120.0, "tokens_max": 100_000}
STRICT_BUDGET = {**DEFAULT_BUDGET, "p50_max_s": 0.5}


# ============================================================
# 计量
# ============================================================

def counting_chat_fn(model=None):
    """包装 mh 的聊天函数, 顺带累计字符数(供 token 估算)。"""
    os.environ["LLM_MODEL"] = model or os.environ.get("LLM_MODEL", "qwen3:4b")
    harness_dir = os.path.join(os.path.dirname(AITEST_DIR), "harness")
    if harness_dir not in sys.path:
        sys.path.insert(0, harness_dir)
    import mh.llm as mh_llm
    mh_llm.MODEL = os.environ["LLM_MODEL"]
    acc = {"chars": 0}

    def _chat(messages, tools=None, **kw):
        acc["chars"] += sum(len(str(m.get("content", ""))) for m in messages)
        msg = mh_llm.chat_with_retry(messages, tools=tools, **kw)
        acc["chars"] += len(msg.get("content") or "")
        return msg

    return _chat, acc


def _percentile(values, p):
    """简单最近秩百分位(p=0.5/0.95), 小样本下直观可复算。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(p * (len(ordered) - 1))))
    return ordered[idx]


# ============================================================
# 跑批
# ============================================================

def run_round(tasks, model="qwen3:4b", run_fn=None):
    """跑一轮任务集, 返回 {latencies, tokens, rows}。"""
    from testbench.suites.e2e_task import load_tasks
    tasks = tasks or load_tasks()
    if run_fn is None:
        from testbench import suts
        chat, acc = counting_chat_fn(model)

        def run_fn(task):
            return suts.run_sut(task, sut="mh", model=model, max_turns=6,
                                chat_fn=chat), acc
    rows, lats, toks = [], [], []
    for t in tasks:
        out = run_fn(t["task"])
        r, acc = out if isinstance(out, tuple) else (out, None)
        lat = float(r.get("elapsed_s") or 0.0)
        tok = round((acc or {}).get("chars", 0) / 4)
        lats.append(lat)
        toks.append(tok)
        rows.append({"id": t["id"], "elapsed_s": lat, "tokens_est": tok})
    return {"latencies": lats, "tokens": toks, "rows": rows}


def run_perf(rounds=3, tasks_n=3, model="qwen3:4b", run_fn=None, verbose=True):
    """多轮采样取中位; 返回 report dict。"""
    from testbench.suites.e2e_task import load_tasks
    tasks = load_tasks()[:tasks_n]
    per_round = []
    for i in range(1, rounds + 1):
        rr = run_round(tasks, model=model, run_fn=run_fn)
        p50 = round(statistics.median(rr["latencies"]), 2)
        p95 = round(_percentile(rr["latencies"], 0.95), 2)
        total_tok = sum(rr["tokens"])
        per_round.append({"round": i, "p50_s": p50, "p95_s": p95,
                          "tokens_est": total_tok, "rows": rr["rows"]})
        if verbose:
            print(f"  round {i}: P50={p50}s P95={p95}s "
                  f"tokens≈{total_tok}")
    metrics = {
        "p50_s": round(statistics.median(r["p50_s"] for r in per_round), 2),
        "p95_s": round(statistics.median(r["p95_s"] for r in per_round), 2),
        "tokens_est": round(statistics.median(r["tokens_est"]
                                              for r in per_round)),
    }
    return {"metrics": metrics, "rounds": per_round, "tasks_n": len(tasks)}


# ============================================================
# 预算判定(纯函数)
# ============================================================

def evaluate_budget(metrics, budget=None):
    """方向统一为'越低越好'; tokens_est 标注为估算。返回 (graded, failed)。"""
    budget = {**DEFAULT_BUDGET, **(budget or {})}
    mapping = {"p50_s": "p50_max_s", "p95_s": "p95_max_s",
               "tokens_est": "tokens_max"}
    graded, failed = {}, []
    for metric, limit_key in mapping.items():
        value = metrics.get(metric)
        limit = budget[limit_key]
        ok = value is not None and value <= limit
        graded[metric] = {"value": value, "limit": limit, "pass": ok}
        if not ok:
            failed.append(metric)
    return graded, failed


def render(graded, failed):
    red, green, reset = "\033[31m", "\033[32m", "\033[0m"
    out = []
    for name, d in graded.items():
        mark = green + "PASS" + reset if d["pass"] else red + "FAIL" + reset
        out.append(f"  {name:11s} 值={d['value']} <= 预算={d['limit']} "
                   f"[{mark}]")
    return "\n".join(out)


def _cli():
    import argparse
    import json
    ap = argparse.ArgumentParser(description="性能与成本门禁")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--tasks", type=int, default=3)
    ap.add_argument("--model", default="qwen3:4b")
    ap.add_argument("--strict", action="store_true",
                    help="P50 阈值压到 0.5s(演示失败态)")
    args = ap.parse_args()

    rep = run_perf(rounds=args.rounds, tasks_n=args.tasks, model=args.model)
    graded, failed = evaluate_budget(
        rep["metrics"], STRICT_BUDGET if args.strict else None)
    rep.update({"budget": graded, "failed": failed,
                "generated_at": datetime.now().isoformat(timespec="seconds")})
    out = Path(RESULTS_PATH)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print("\n" + render(graded, failed))
    print(f"报告 -> {out}")
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    _cli()
