#!/usr/bin/env python3
"""16 · 轨迹评测 (docs/aitest.md 项目 16)

验收: 一条命令三层验证——
  pytest   离线单测: 阈值/归一化/空轨迹/收敛分
  selftest 预置三条轨迹: 快 100 > 慢 60, 死循环 0 分
  real     真机跑 1 个任务, 对返回的 tool_trace 现场打分(可选)
Ollama 不在线时 real 段诚实跳过。

用法:
  python3 trajectory.py            # pytest(离线)
  python3 trajectory.py all        # pytest + selftest + real
"""

import os
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench.suites import trajectory as T  # noqa: E402
from testbench.suts import ollama_alive       # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "离线单测(阈值/归一化/边界)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_trajectory.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def do_selftest():
    step("selftest", "预置轨迹: 快/慢/死循环")
    res = T.self_check()
    print(f"  fast={res['fast']['score']} slow={res['slow']['score']} "
          f"loop={res['loop']['score']}(loop={res['loop']['loop']})")
    print(f"  死循环原因: {res['loop']['loop_reason']}")
    assert res["ok"], "自证失败: 快/慢不可区分或死循环未判 0"
    import json
    out = AITEST_DIR / "results" / "trajectory.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"  落盘 -> {out}")
    return res


def do_real():
    step("real", "真机 1 任务: 对 tool_trace 现场打分(mh, qwen3:4b)")
    from testbench import suts
    r = suts.run_sut("创建 a.txt 并写一行内容, 然后读回确认。",
                     sut="mh", model="qwen3:4b", max_turns=6)
    trace = r.get("tool_trace") or []
    rep = T.score_trajectory(trace, expected_steps=2,
                             completed=bool(str(r.get("final", "")).strip()))
    print(f"  轨迹步数={rep['steps']} 效率={rep['efficiency']} "
          f"冗余={rep['redundancy']} 分数={rep['score']}")
    assert rep["score"] > 0, f"正常任务被误判 0 分: {rep}"
    return rep


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    if target == "all":
        do_pytest()
        do_selftest()
        if ollama_alive():
            do_real()
        else:
            print("\n=====> Ollama 不在线: real 段诚实跳过")
    elif target == "pytest":
        do_pytest()
    elif target == "selftest":
        do_selftest()
    elif target == "real":
        do_real()
    else:
        print("可用: pytest | selftest | real | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
