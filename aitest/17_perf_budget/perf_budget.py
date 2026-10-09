#!/usr/bin/env python3
"""17 · 性能与成本门禁 (docs/aitest.md 项目 17)

验收: 一条命令两态——
  pytest  离线单测: 百分位/预算方向/fail-closed/假驱动
  real    真机 3 任务 ×3 轮(qwen3:4b): 默认预算应通过
  strict  子进程 CLI --strict(P50 阈值 0.5s): 应退出码 1 且标红 FAIL
Ollama 不在线时真机两段诚实跳过。

用法:
  python3 perf_budget.py            # pytest(离线)
  python3 perf_budget.py all        # pytest + real + strict
"""

import os
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench.suites import perf_budget as P  # noqa: E402
from testbench.suts import ollama_alive        # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "离线单测(百分位/预算方向/fail-closed)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_perf_budget.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def do_real():
    step("real", "3 任务 ×3 轮真机(mh, qwen3:4b), 默认预算")
    rep = P.run_perf(rounds=3, tasks_n=3, model="qwen3:4b")
    graded, failed = P.evaluate_budget(rep["metrics"])
    print("\n" + P.render(graded, failed))
    print(f"  三指标中位: P50={rep['metrics']['p50_s']}s "
          f"P95={rep['metrics']['p95_s']}s "
          f"tokens≈{rep['metrics']['tokens_est']}")
    assert not failed, f"默认预算不应失败: {failed}"
    return rep


def do_strict():
    step("strict", "CLI --strict(P50≤0.5s 不可能达标): 期望退出码 1")
    p = subprocess.run(
        [sys.executable, "-m", "testbench.suites.perf_budget",
         "--tasks", "1", "--rounds", "1", "--strict"],
        cwd=str(AITEST_DIR), capture_output=True, text=True)
    out = p.stdout + p.stderr
    has_fail = "FAIL" in out
    print(f"  exit={p.returncode} | 报告含 FAIL: {has_fail}")
    assert p.returncode == 1 and has_fail


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    if target == "all":
        do_pytest()
        if ollama_alive():
            do_real()
            do_strict()
        else:
            print("\n=====> Ollama 不在线: 真机两段诚实跳过")
    elif target == "pytest":
        do_pytest()
    elif target == "real":
        do_real()
    elif target == "strict":
        do_strict()
    else:
        print("可用: pytest | real | strict | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
