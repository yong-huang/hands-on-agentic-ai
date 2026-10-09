#!/usr/bin/env python3
"""06 · 幻觉检测器 — claims 三级核验 (docs/aitest.md 项目 6)

验收: 一条命令跑完混淆矩阵——
  probe     Ollama 探活
  selftest  5 段 source × 20 条预置回答(10 幻觉 + 10 忠实), 真机 judge,
            验收口径 检出 ≥9/10 且 误报 ≤1/10(实测 10/10 · 0/10)
  pytest    离线单测(拆分/数字规则/覆盖率子串/裁判解析)
Ollama 不在线时 selftest 诚实跳过。

用法:
  python3 factuality.py            # 全流程(真机 judge 约 2 分钟)
  python3 factuality.py pytest     # 只跑离线单测
"""

import functools
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))
sys.path.insert(0, str(AITEST_DIR.parent / "qa"))

import os as _os

_os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
_os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

import llm as qa_llm  # noqa: E402
from testbench.asserts import factuality as F  # noqa: E402
from testbench.suts import ollama_alive  # noqa: E402

# judge 用 300 token: 60 会被 qwen3 的思考段吃空(实测), 300 起才有干净正文
JUDGE_CHAT = functools.partial(qa_llm.chat, num_predict=300, temperature=0)


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_probe():
    step("probe", "Ollama 探活")
    alive = ollama_alive()
    print(f"  {'存活 ✅' if alive else '不在线 ❌ (真机段诚实跳过)'}")
    return alive


def do_selftest():
    step("selftest", "20 条样本真机 judge, 混淆矩阵验收")
    assert F.selftest(JUDGE_CHAT), "幻觉检测未达验收口径(检出 ≥9 且 误报 ≤1)"


def do_pytest():
    step("pytest", "离线单测")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_factuality.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    table = {"probe": do_probe, "selftest": do_selftest, "pytest": do_pytest}
    if target == "all":
        online = do_probe()
        if online:
            do_selftest()
        else:
            print("  (selftest 跳过: judge 需要真机)")
        do_pytest()
        print("\n=====> 项目 6 验收完成: 幻觉检测器 "
              + ("✅ 真机混淆矩阵" if online else "✅ 离线层(真机段跳过)"))
    elif target in table:
        table[target]()
    else:
        print("可用: probe | selftest | pytest | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
