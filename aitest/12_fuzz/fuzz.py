#!/usr/bin/env python3
"""12 · 鲁棒性 fuzz — 畸形输入轰炸 (docs/aitest.md 项目 12)

验收: 一条命令分层验证——
  pytest  离线单测: 生成器规模/驱动异常安全/四种结局分类/留痕
  mini    100 条畸形输入打向离线 SUT(纯模板引擎), 未捕获异常率 = 0
  mh      12 条子集打向真机 SUT(qwen3:4b), findings.jsonl 留痕
Ollama 不在线时 mh 段诚实跳过(mini 段全离线)。

用法:
  python3 fuzz.py            # pytest(离线)
  python3 fuzz.py all        # pytest + mini 100 + mh 子集
"""

import os
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench.suites import fuzz as F  # noqa: E402
from testbench.suts import ollama_alive  # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "离线单测(生成器/驱动安全/分类)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_fuzz.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def do_mini():
    step("mini", "100 条畸形输入 -> 离线 SUT(模板引擎)")
    rep = F.run_fuzz(sut="mini", verbose=True)
    print(f"  结果: {rep['outcomes']} | findings -> {rep['findings_path']}")
    assert rep["total"] == 100
    assert rep["uncaught_exception_rate"] == 0
    return rep


def do_mh(limit=12):
    step("mh", f"{limit} 条子集 -> 真机 SUT(qwen3:4b)")
    rep = F.run_fuzz(sut="mh", limit=limit, model="qwen3:4b", verbose=True)
    print(f"  结果: {rep['outcomes']} | findings -> {rep['findings_path']}")
    assert rep["uncaught_exception_rate"] == 0
    assert rep["total"] == limit
    return rep


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    if target == "all":
        do_pytest()
        do_mini()
        if ollama_alive():
            do_mh()
        else:
            print("\n=====> Ollama 不在线: mh 子集诚实跳过")
    elif target == "pytest":
        do_pytest()
    elif target == "mini":
        do_mini()
    elif target == "mh":
        do_mh()
    else:
        print("可用: pytest | mini | mh | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
