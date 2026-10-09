#!/usr/bin/env python3
"""20 · CI 门禁分级 (docs/aitest.md 项目 20)

验收: 全离线两段——
  pytest   离线单测: 路由规则/退出码判定
  selftest 假 diff 两态: 只改数据->smoke, 改 SUT->full, 未知->full(fail-safe)
真机整合跑(`make gate`)属 CI 用法, 本脚本只做 --dry-run 演示路由。

用法:
  python3 gate_lab.py all
"""

import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench import gate as G  # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "离线单测(路由规则/退出码判定)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_gate.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def do_selftest():
    step("selftest", "假 diff 两态: 数据->smoke, SUT/未知->full")
    assert G.selftest() is True


def do_dry():
    step("dry-run", "两条假 diff 的路由演示(不跑 runner)")
    for files in (["aitest/datasets/tasks.yaml"],
                  ["harness/mh/loop.py"]):
        res = G.gate(files=files, dry_run=True, verbose=True)
        print(f"  -> level={res['level']}")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target in ("all", "pytest"):
        do_pytest()
    if target in ("all", "selftest"):
        do_selftest()
    if target in ("all", "dry"):
        do_dry()


if __name__ == "__main__":
    main()
