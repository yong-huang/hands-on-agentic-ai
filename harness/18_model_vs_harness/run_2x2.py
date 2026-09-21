#!/usr/bin/env python3
"""18 · 收尾对照 — 同 Harness 异模型 2×2 实验 (docs/harness.md 项目 18)

闭环整个系列的主线问题: 换模型和换 harness, 哪个影响大?
2×2 设计(复用 16 评测台的任务集与判分器):
  ① qwen3.8  + 裸 loop (baseline 工具)
  ② qwen3.8  + full harness (契约+沙箱+预算)
  ③ qwen3:4b + 裸 loop
  ④ qwen3:4b + full harness
产出 REPORT.md: 2×2 表 + 量化结论。

用法:
  python3 run_2x2.py                 # 真机全量(约 40-60 分钟)
  python3 run_2x2.py --quick         # 每格 4 任务快速版
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

LAB = Path(__file__).resolve().parent
EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL))
sys.path.insert(0, str(EVAL / ".."))

from eval_run import TASKS, build_tools, SYSTEM  # noqa: E402
from mh import llm as mh_llm  # noqa: E402
from mh import loop  # noqa: E402
from mh.budget import Budget, budget_chat_fn  # noqa: E402

PROFILES = {"bare": "baseline", "full": "full"}
MODELS = {"qwen3.8": "qwen3.8:latest", "qwen3:4b": "qwen3:4b"}


def report(rows, out: Path):
    cells = {}
    for r in rows:
        c = cells.setdefault(r["cell"], {"ok": 0, "n": 0, "turns": 0, "tokens": 0})
        c["n"] += 1
        c["ok"] += r["ok"]
        c["turns"] += r["turns"]
        c["tokens"] += r["tokens"]
    lines = ["# 2×2 收尾对照(自动生成)\n",
             "| 格 | 解决率 | 平均轮次 | est token/任务 |", "|:--|:--:|:--:|:--:|"]
    order = ["qwen3.8+bare", "qwen3.8+full", "qwen3:4b+bare", "qwen3:4b+full"]
    for k in order:
        c = cells.get(k)
        if not c:
            continue
        lines.append(f"| {k} | {c['ok']}/{c['n']} | "
                     f"{c['turns']/c['n']:.1f} | {c['tokens']/c['n']:.0f} |")
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="每格 4 任务")
    args = ap.parse_args()
    n = 4 if args.quick else 10
    rows_path = LAB / "rows.json"
    rows = []
    if rows_path.exists():  # 断点续跑
        rows = json.loads(rows_path.read_text())
        done = {(r["cell"], r["task"]) for r in rows}
    else:
        done = set()
    for mk in MODELS:
        for h in PROFILES:
            for i in range(n):
                if (f"{mk}+{h}", i) in done:
                    print(f"  跳过已完成 {mk}+{h} t{i}")
                    continue
                run_one(mk, h, i, rows, rows_path)
    report(rows, LAB / "REPORT.md")


def run_one(mk, h, i, rows, rows_path):
    os.environ["LLM_MODEL"] = MODELS[mk]
    import importlib
    import mh.llm as M
    importlib.reload(M)
    sandbox = Path(tempfile.mkdtemp(prefix=f"ev18_{mk[:4]}_{h}_{i}_"))
    budget = Budget(max_turns=10, max_tokens=8000)
    wrapped = budget_chat_fn(M.chat_with_retry, budget)
    try:
        r = loop.run_agent(TASKS[i][0], build_tools(PROFILES[h]), max_turns=10,
                           chat_fn=wrapped, cwd=str(sandbox),
                           messages=[{"role": "system", "content": SYSTEM},
                                     {"role": "user", "content": TASKS[i][0]}])
        turns = r["turns"]
    except Exception as e:
        turns = 10
    ok = TASKS[i][1](sandbox)
    rows.append({"cell": f"{mk}+{h}", "task": i, "ok": ok, "turns": turns,
                 "tokens": budget.tokens_est})
    rows_path.write_text(json.dumps(rows, indent=1))
    print(f"  [{mk}+{h} t{i}] {'✅' if ok else '❌'} {turns} 轮 ~{budget.tokens_est} tok")


if __name__ == "__main__":
    main()
