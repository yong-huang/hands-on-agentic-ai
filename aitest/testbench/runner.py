"""runner — 统一跑批入口与结果模型 (docs/aitest.md 项目 18, ⛓️)

一条命令串联七个模块, 产出单一 results.json 并过 schema 校验:
    eval / regression / security / contract / e2e / trajectory / perf
档位: --level smoke(小样本, 分钟级) | full(全量口径, 30 分钟+)
单模块崩溃不影响其余收集(status=error 记录后继续)。

    python3 -m testbench run --sut mh --level smoke
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(HERE)
RESULTS_PATH = os.path.join(AITEST_DIR, "results", "run_results.json")

sys.path.insert(0, AITEST_DIR)


def _ollama_alive():
    from testbench.suts import ollama_alive
    return ollama_alive()


# ============================================================
# 七个模块: (ctx) -> {"status","passed","metrics","detail"}
# ============================================================

def mod_eval(ctx):
    from testbench.run_eval import run
    if ctx["level"] == "full" and not ctx["ollama"] and not ctx["mock"]:
        return {"status": "skipped", "passed": None,
                "detail": "Ollama 不在线, full 评测跳过"}
    limit = 2 if ctx["level"] == "smoke" else 10
    offline = ctx["mock"] or (ctx["level"] == "smoke" and not ctx["ollama"])
    sut = "mini" if offline else ctx["sut"]
    r = run(dataset="golden_v1", sut=sut, model=ctx["model"], limit=limit,
            offline_chat=offline, verbose=False)
    s = r["summary"]
    return {"status": "ok", "passed": None,
            "metrics": {"overall_pass_rate": s["overall_pass_rate"],
                        "rates": s["rates"], "cases": len(r["cases"]),
                        "offline": offline},
            "detail": f"golden_v1 前 {limit} 条"}


def mod_regression(ctx):
    if not ctx["ollama"] or ctx["mock"]:
        return {"status": "skipped", "passed": None,
                "detail": "提示词回归需真机 judge, 离线跳过"}
    from testbench.suites.prompt_regression import run_regression
    limit = 2 if ctx["level"] == "smoke" else 10
    r = run_regression(model=ctx["model"], limit=limit, verbose=False)
    return {"status": "ok", "passed": None,
            "metrics": r["summary"], "detail": f"双版对比前 {limit} 条"}


def mod_security(ctx):
    from testbench import security_scan as S
    if not ctx["ollama"] and not ctx["mock"]:
        return {"status": "skipped", "passed": None,
                "detail": "安全扫描需真机, 离线跳过"}
    limits = ({"injection": 3, "jailbreak": 6, "fuzz": 3}
              if ctx["level"] == "smoke"
              else {"injection": 6, "jailbreak": None, "fuzz": 12})
    r = S.scan(sut=ctx["sut"], model=ctx["model"], limits=limits,
               verbose=False,
               out_path=os.path.join(AITEST_DIR, "results",
                                     "security_scan.json"))
    return {"status": "ok", "passed": r["verdict"] == "pass",
            "metrics": {k: v["value"] for k, v in r["dimensions"].items()},
            "detail": f"failed={r['failed_dimensions'] or '无'}"}


def mod_contract(ctx):
    if not ctx["ollama"] or ctx["mock"]:
        return {"status": "skipped", "passed": None,
                "detail": "契约测试需真机工具调用, 离线跳过"}
    from testbench.suites import tool_contract as T
    variants = [None] if ctx["level"] == "smoke" else \
        [None, "wrong_type", "missing_param", "extra_call"]
    results = {}
    for v in variants:
        rep = T.run_contract(v, model=ctx["model"], verbose=False)
        results[v or "normal"] = len(rep["violations"])
    if ctx["level"] == "smoke":
        passed = results["normal"] == 0
    else:
        passed = (results["normal"] == 0 and all(
            n > 0 for k, n in results.items() if k != "normal"))
    return {"status": "ok", "passed": passed, "metrics": results,
            "detail": f"变体违规数={results}"}


def mod_e2e(ctx):
    if not ctx["ollama"] or ctx["mock"]:
        return {"status": "skipped", "passed": None,
                "detail": "端到端任务需真机副作用, 离线跳过"}
    from testbench.suites import e2e_task as E
    limit = 2 if ctx["level"] == "smoke" else 10
    rows = E.run_once(limit=limit, model=ctx["model"], verbose=False)
    ok = sum(1 for r in rows if r["ok"])
    return {"status": "ok", "passed": None,
            "metrics": {"success": ok, "total": len(rows),
                        "rate": round(ok / len(rows), 3)},
            "detail": f"前 {limit} 个任务"}


def mod_trajectory(_ctx):
    from testbench.suites.trajectory import self_check
    r = self_check()
    return {"status": "ok", "passed": r["ok"],
            "metrics": {"fast": r["fast"]["score"],
                        "slow": r["slow"]["score"],
                        "loop": r["loop"]["score"]},
            "detail": "预置轨迹自证(离线)"}


def mod_perf(ctx):
    if not ctx["ollama"] or ctx["mock"]:
        return {"status": "skipped", "passed": None,
                "detail": "性能采样需真机, 离线跳过"}
    from testbench.suites.perf_budget import run_perf, evaluate_budget
    cfg = ((1, 1) if ctx["level"] == "smoke" else (3, 2))
    r = run_perf(rounds=cfg[1], tasks_n=cfg[0], model=ctx["model"],
                 verbose=False)
    _, failed = evaluate_budget(r["metrics"])
    return {"status": "ok", "passed": None,
            "metrics": r["metrics"], "detail": f"超标项={failed or '无'}"}


MODULES = [
    ("eval", mod_eval), ("regression", mod_regression),
    ("security", mod_security), ("contract", mod_contract),
    ("e2e", mod_e2e), ("trajectory", mod_trajectory), ("perf", mod_perf),
]


# ============================================================
# 运行器: 单模块崩溃不阻断
# ============================================================

def run_all(level="smoke", sut="mh", model="qwen3:4b", modules=None,
            verbose=True):
    modules = modules or MODULES
    ctx = {"level": level, "sut": sut, "model": model,
           "ollama": _ollama_alive(), "mock": os.environ.get("MOCK") == "1"}
    t0 = time.time()
    results = []
    for name, fn in modules:
        if verbose:
            print(f"\n=====> 模块: {name}")
        t1 = time.time()
        try:
            out = fn(ctx)
            row = {"name": name, "elapsed_s": round(time.time() - t1, 2),
                   **{k: out.get(k, None) for k in
                      ("status", "passed", "metrics", "detail")}}
            row["metrics"] = row["metrics"] or {}
            row["detail"] = row["detail"] or ""
            row["status"] = row["status"] or "ok"
        except Exception as e:                    # noqa: BLE001
            row = {"name": name, "status": "error", "passed": False,
                   "metrics": {}, "elapsed_s": round(time.time() - t1, 2),
                   "detail": f"{type(e).__name__}: {e}"}
        results.append(row)
        if verbose:
            mark = {"ok": "✅", "error": "💥", "skipped": "⏭️"}[row["status"]]
            print(f"  {mark} {row['status']} {row['elapsed_s']}s "
                  f"{row['detail'][:80]}")

    report = {"meta": {"sut": sut, "level": level, "model": model,
                       "generated_at": datetime.now().isoformat(
                           timespec="seconds"),
                       "elapsed_s": round(time.time() - t0, 2),
                       "modules_n": len(results)},
              "modules": results}
    return report


def save_and_validate(report, path=None):
    from testbench import schema
    schema.validate(report)
    out = Path(path or RESULTS_PATH)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="testbench", description="统一 runner")
    ap.add_argument("cmd", choices=["run"], help="run = 跑批")
    ap.add_argument("--sut", default="mh", choices=["mh", "mini"])
    ap.add_argument("--level", default="smoke", choices=["smoke", "full"])
    ap.add_argument("--model", default="qwen3:4b")
    args = ap.parse_args(argv)

    report = run_all(level=args.level, sut=args.sut, model=args.model)
    out = save_and_validate(report)
    errors = [m["name"] for m in report["modules"] if m["status"] == "error"]
    print(f"\n结果 -> {out}")
    print(f"模块状态: " + ", ".join(
        f"{m['name']}={m['status']}" for m in report["modules"]))
    print(f"schema 校验: ✅ | 崩溃模块: {errors or '无'}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
