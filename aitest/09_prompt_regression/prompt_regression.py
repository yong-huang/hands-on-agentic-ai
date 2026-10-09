#!/usr/bin/env python3
"""09 · 提示词回归套件 — promptfoo 思想自研 (docs/aitest.md 项目 9)

验收: 一条命令自证"套件能抓劣化"——
  pytest     三态判定与报告渲染单测(离线)
  selftest   预置劣化 prompt 变体 vs 严谨 base, 真机全量 20 条 ×2 版
             (约 8 分钟), 验收口径 报告标出 ≥1 个劣化项
Ollama 不在线时 selftest 诚实跳过。

用法:
  python3 prompt_regression.py            # pytest + selftest
  python3 prompt_regression.py pytest     # 只跑离线
"""

import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench.suts import ollama_alive  # noqa: E402
from testbench.suites import prompt_regression as PR  # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "三态判定/报告渲染单测")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_prompt_regression.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def do_selftest():
    step("selftest", "劣化变体 vs 严谨 base, 20 条 ×2 版真机")
    results = PR.run_regression()
    report = AITEST_DIR / "results" / "regression_report.md"
    report.write_text(PR.render_report(results), encoding="utf-8")
    print(f"  报告 -> {report}")
    print(PR.render_report(results))
    assert results["summary"]["degraded"] >= 1, \
        "预置劣化变体未被抓到 —— 套件灵敏度不足, 不能信任它的'无劣化'结论"


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    table = {"pytest": do_pytest, "selftest": do_selftest}
    if target == "all":
        do_pytest()
        if ollama_alive():
            do_selftest()
        else:
            print("\n=====> Ollama 不在线: selftest 诚实跳过")
    elif target in table:
        table[target]()
    else:
        print("可用: pytest | selftest | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
