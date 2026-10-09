#!/usr/bin/env python3
"""07 · LLM-as-Judge 校准 — rubric 评分与人工对齐 (docs/aitest.md 项目 7)

验收: 一条命令跑完校准双指标——
  probe     Ollama 探活
  selftest  20 条人工预标注 × 2 轮 judge(40 次调用, 约 3 分钟):
            相邻一致率 ≥80% 且 重复一致率 ≥90%(硬验收)
  pytest    离线单测(解析链路/对齐数学)
Ollama 不在线时 selftest 诚实跳过。LLM_MODEL 默认 qwen3:4b(画像实测足够,
换 qwen3.8 更强但慢 10 倍)。

用法:
  python3 judge_rubric.py            # 全流程
  python3 judge_rubric.py selftest   # 只跑真机校准
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
from testbench.judges import rubric as R  # noqa: E402
from testbench.suts import ollama_alive  # noqa: E402

JUDGE_CHAT = functools.partial(qa_llm.chat, num_predict=800, temperature=0)


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_probe():
    step("probe", "Ollama 探活")
    alive = ollama_alive()
    print(f"  {'存活 ✅' if alive else '不在线 ❌ (真机段诚实跳过)'}"
          f"  LLM_MODEL={_os.environ.get('LLM_MODEL', 'qwen3:4b (默认)')}")
    return alive


def do_selftest():
    step("selftest", "校准双指标: 对齐 ≥80% + 稳定 ≥90% (40 次 judge)")
    assert R.selftest(JUDGE_CHAT), "judge 校准未达验收口径"


def do_pytest():
    step("pytest", "离线单测")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_judge_rubric.py", "-q"],
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
        do_pytest()
        print("\n=====> 项目 7 验收完成: LLM-as-Judge 校准 "
              + ("✅ 真机双指标" if online else "✅ 离线层(真机段跳过)"))
    elif target in table:
        table[target]()
    else:
        print("可用: probe | selftest | pytest | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
