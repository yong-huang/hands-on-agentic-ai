#!/usr/bin/env python3
"""15 · 端到端任务成功率 (docs/aitest.md 项目 15)

验收: 一条命令两遍跑批——
  pytest  离线单测: 六类判分器/失败证据/稳定性口径
  real    10 任务 × 2 遍真机(mh, qwen3:4b), 成功率差值 <=1 个任务
Ollama 不在线时真机段诚实跳过(MOCK=1 可离线跑管道)。

用法:
  python3 e2e_task.py            # pytest(离线)
  python3 e2e_task.py all        # pytest + 真机两遍
"""

import os
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench.suites import e2e_task as E  # noqa: E402
from testbench.suts import ollama_alive      # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "离线单测(判分器/证据/稳定性)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_e2e_task.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def do_real():
    step("real", "10 任务 × 2 遍真机(mh, qwen3:4b)")
    rep = E.run_e2e(runs=2, model="qwen3:4b")
    rates = " / ".join(f"{r['success']}/{r['total']}" for r in rep["runs"])
    print(f"\n  成功率: {rates} | 最大波动 {rep['max_diff']} 个任务 | "
          f"stable={rep['stable']}")
    print(f"  落盘 -> {AITEST_DIR / 'results' / 'e2e_tasks.json'}")
    assert rep["stable"], f"两遍差值 {rep['max_diff']} > 1"
    return rep


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    if target == "all":
        do_pytest()
        if ollama_alive() and os.environ.get("MOCK") != "1":
            do_real()
        else:
            print("\n=====> Ollama 不在线或 MOCK=1: 真机两遍诚实跳过")
    elif target == "pytest":
        do_pytest()
    elif target == "real":
        do_real()
    else:
        print("可用: pytest | real | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
