"""suites.e2e_task — 端到端任务成功率 (docs/aitest.md 项目 15)

任务集 datasets/tasks.yaml(10 个终态可判任务), 判分只读沙箱磁盘:
    file_exists / files_exist / line_count / line_contains_count
    / content_contains / content_equal
失败任务自动留终态证据(最后回答 + tool_trace 尾部)。
跑两遍比较成功率稳定性(文档口径: 差值 <=1 个任务)。

    run_e2e(sut="mh", runs=2, model=...) -> report dict
"""

import os
import sys
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(os.path.dirname(HERE))
TASKS_PATH = os.path.join(AITEST_DIR, "datasets", "tasks.yaml")
RESULTS_PATH = os.path.join(AITEST_DIR, "results", "e2e_tasks.json")

sys.path.insert(0, AITEST_DIR)

import yaml  # noqa: E402


def load_tasks(path=None):
    data = yaml.safe_load(Path(path or TASKS_PATH).read_text(encoding="utf-8"))
    return data["tasks"]


# ============================================================
# 终态判分器(纯函数, 只读磁盘)
# ============================================================

def check_terminal(check, sandbox):
    """返回 (ok, detail)。沙箱是任务工作目录 Path。"""
    sandbox = Path(sandbox)
    kind = check["kind"]
    try:
        if kind == "file_exists":
            p = sandbox / check["path"]
            return p.is_file(), f"{check['path']} exists={p.is_file()}"
        if kind == "files_exist":
            missing = [x for x in check["paths"]
                       if not (sandbox / x).is_file()]
            return not missing, f"missing={missing or '无'}"
        if kind == "line_count":
            p = sandbox / check["path"]
            if not p.is_file():
                return False, f"{check['path']} 不存在"
            n = len(p.read_text(encoding="utf-8").strip().splitlines())
            return n == check["count"], f"lines={n} 期望={check['count']}"
        if kind == "line_contains_count":
            p = sandbox / check["path"]
            if not p.is_file():
                return False, f"{check['path']} 不存在"
            n = sum(1 for line in p.read_text(encoding="utf-8").splitlines()
                    if check["substr"] in line)
            return n == check["count"], \
                f"含 {check['substr']!r} 的行={n} 期望={check['count']}"
        if kind == "content_contains":
            p = sandbox / check["path"]
            if not p.is_file():
                return False, f"{check['path']} 不存在"
            hit = check["text"] in p.read_text(encoding="utf-8")
            return hit, f"含 {check['text']!r}={hit}"
        if kind == "content_equal":
            pa, pb = sandbox / check["path_a"], sandbox / check["path_b"]
            if not (pa.is_file() and pb.is_file()):
                return False, f"{check['path_a']}/{check['path_b']} 有缺失"
            same = pa.read_text(encoding="utf-8") == pb.read_text(encoding="utf-8")
            return same, f"两文件一致={same}"
        return False, f"未知 check kind: {kind}"
    except Exception as e:                      # noqa: BLE001
        return False, f"判分异常: {type(e).__name__}: {e}"


# ============================================================
# 跑批
# ============================================================

def run_once(tasks=None, sut="mh", model="qwen3:4b", limit=None,
             run_fn=None, verbose=True):
    """跑一遍任务集, 返回 rows(每条含 ok 与失败证据)。"""
    tasks = tasks or load_tasks()
    if limit:
        tasks = tasks[:limit]
    if run_fn is None:
        from testbench import suts
        run_fn = lambda task, sandbox: suts.run_sut(  # noqa: E731
            task, sut=sut, model=model, max_turns=6, sandbox=sandbox)

    rows = []
    for i, t in enumerate(tasks, 1):
        ok, detail, evidence = False, "", {}
        r = None
        try:
            r = run_fn(t["task"], None)
            ok, detail = check_terminal(t["check"], r.get("cwd"))
            if not ok:
                trace = r.get("tool_trace") or []
                evidence = {"final": str(r.get("final", ""))[:200],
                            "trace_tail": str(trace[-3:])[:300]}
        except Exception as e:                  # noqa: BLE001
            detail = f"驱动异常: {type(e).__name__}: {e}"
        rows.append({"id": t["id"], "ok": ok, "detail": detail,
                     "turns": (r or {}).get("turns"),
                     "elapsed_s": (r or {}).get("elapsed_s"),
                     "evidence": evidence})
        if verbose:
            print(f"  [{i:02d}/{len(tasks)}] {t['id']} "
                  f"{'✅' if ok else '❌'} {detail}")
    return rows


def run_e2e(runs=2, sut="mh", model="qwen3:4b", limit=None, verbose=True,
            out_path=None):
    """跑 N 遍, 汇总成功率与稳定性(差值 <=1 个任务)。"""
    tasks = load_tasks()
    if limit:
        tasks = tasks[:limit]
    n = len(tasks)
    per_run = []
    for r_i in range(1, runs + 1):
        if verbose:
            print(f"\n---- 第 {r_i}/{runs} 遍 ({n} 任务) ----")
        rows = run_once(tasks, sut=sut, model=model, verbose=verbose)
        succ = sum(1 for r in rows if r["ok"])
        per_run.append({"success": succ, "total": n,
                        "rate": round(succ / n, 3) if n else 0.0,
                        "rows": rows})
    diffs = [abs(per_run[i]["success"] - per_run[i - 1]["success"])
             for i in range(1, len(per_run))]
    report = {
        "taskset": "e2e_v1", "sut": sut, "model": model,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "runs": per_run,
        "max_diff": max(diffs) if diffs else 0,
        "stable": (max(diffs) <= 1) if diffs else True,
    }
    out = Path(out_path or RESULTS_PATH)
    out.parent.mkdir(exist_ok=True)
    import json
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return report


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="端到端任务成功率")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model", default="qwen3:4b")
    args = ap.parse_args()
    rep = run_e2e(runs=args.runs, model=args.model, limit=args.limit)
    rates = " / ".join(f"{r['success']}/{r['total']}" for r in rep["runs"])
    print(f"\n成功率: {rates} | 最大波动 {rep['max_diff']} 个任务 | "
          f"stable={rep['stable']}")
    sys.exit(0 if rep["stable"] else 1)


if __name__ == "__main__":
    _cli()
