#!/usr/bin/env python3
"""18 · 统一 runner 与结果模型 (⛓️, docs/aitest.md 项目 18)

验收: 一条命令两段——
  pytest  离线单测: schema 契约 / 崩溃隔离 / 七模块注册
  smoke   真机 smoke 跑批: 七模块结果收进单一 results.json 并过 schema
Ollama 不在线时 smoke 段仍可跑(模块自行 skipped, schema 照常校验)。

用法:
  python3 runner_lab.py            # pytest(离线)
  python3 runner_lab.py all        # pytest + smoke 跑批
"""

import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench import runner as R  # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "离线单测(schema/崩溃隔离/注册表)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_runner.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def do_smoke():
    step("smoke", "七模块 smoke 跑批 -> results.json + schema 校验")
    report = R.run_all(level="smoke", sut="mh", model="qwen3:4b",
                       verbose=True)
    out = R.save_and_validate(report)
    names = [m["name"] for m in report["modules"]]
    statuses = {m["name"]: m["status"] for m in report["modules"]}
    errors = [n for n, s in statuses.items() if s == "error"]
    print(f"\n  模块: {statuses}")
    print(f"  落盘 -> {out}")
    assert names == ["eval", "regression", "security", "contract",
                     "e2e", "trajectory", "perf"]
    assert not errors, f"模块崩溃: {errors}"
    assert len(report["modules"]) >= 7
    return report


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    if target == "all":
        do_pytest()
        do_smoke()
    elif target == "pytest":
        do_pytest()
    elif target == "smoke":
        do_smoke()
    else:
        print("可用: pytest | smoke | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
