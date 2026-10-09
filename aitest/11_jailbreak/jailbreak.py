#!/usr/bin/env python3
"""11 · 越狱与红队用例库 — 拒绝率与变异器 (docs/aitest.md 项目 11)

验收: 一条命令跑完整闭环——
  pytest    离线单测: 三分类/变异去重/追加幂等/过滤口径
  mutate    变异器生成 ≥5 条新变体, 自动追加进 payloads/jailbreak_mutations.yaml
  run       种子+变异全量打靶, 拒绝率报告落盘 results/jailbreak_rate.json
  rerun-new 只跑变异库单独复测, 报告落盘 results/jailbreak_mutations_rate.json
Ollama 不在线时 run/rerun-new 诚实跳过(MOCK=1 可离线演示)。

用法:
  python3 jailbreak.py            # pytest(离线)
  python3 jailbreak.py all        # 完整闭环(真机; MOCK=1 时离线)
"""

import os
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench.redteam import jailbreak as J  # noqa: E402
from testbench.suts import ollama_alive        # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "离线单测(三分类/变异器/幂等)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_jailbreak.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def do_mutate():
    step("mutate", "变异器: 生成 ≥5 条新变体并追加")
    new = J.append_mutations(J.mutate_payloads(count=6))
    print(f"  新增 {len(new)} 条:")
    for x in new:
        print(f"    {x['id']} ({x['mutation']}) <- {x['origin']}")
    assert len(new) >= 5, "变异器未产出 ≥5 条"
    assert len(J.load_mutations()) >= 5


def do_run():
    step("run", "种子+变异全量打靶")
    rep = J.run(J.load_all(),
                model=os.environ.get("LLM_MODEL", "qwen3.8:latest"))
    path = J.save_report(rep)
    s = rep["summary"]
    print(f"  total={s['total']} 拒绝={s['refused']} 泄漏={s['leaked']} "
          f"含糊={s['ambiguous']}")
    print(f"  拒绝率={s['refusal_rate']:.3f} 泄漏率={s['leak_rate']:.3f} "
          f"-> {path}")
    assert s["total"] == len(J.load_all())
    assert s["refused"] + s["leaked"] + s["ambiguous"] == s["total"]


def do_rerun_new():
    step("rerun-new", "只跑变异库单独复测")
    muts = J.load_mutations()
    assert muts, "变异库为空: 先跑 mutate"
    rep = J.run(muts,
                model=os.environ.get("LLM_MODEL", "qwen3.8:latest"))
    out = AITEST_DIR / "results" / "jailbreak_mutations_rate.json"
    J.save_report(rep, out)
    print(f"  变异库 {rep['summary']['total']} 条: "
          f"拒绝率={rep['summary']['refusal_rate']:.3f} -> {out}")
    assert rep["summary"]["total"] == len(muts)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    if target == "all":
        do_pytest()
        do_mutate()
        if ollama_alive() or os.environ.get("MOCK") == "1":
            do_run()
            do_rerun_new()
        else:
            print("\n=====> Ollama 不在线: run/rerun-new 诚实跳过")
    elif target == "pytest":
        do_pytest()
    elif target == "mutate":
        do_mutate()
    elif target == "run":
        do_run()
    elif target == "rerun-new":
        do_rerun_new()
    else:
        print("可用: pytest | mutate | run | rerun-new | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
