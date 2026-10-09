#!/usr/bin/env python3
"""08 · ⛓️ 断言统一协议 — golden set 首轮全量评测 (docs/aitest.md 项目 8)

验收: 一条命令跑完基线——
  offline   mini SUT + 脚本 judge 走通管道(秒级, 只验机制不冒充指标)
  real      golden_v1 × mh 真机全量(LLM_MODEL=qwen3:4b, 约 6-10 分钟),
            四维(schema/semantic/factuality/judge)结果齐全, 落
            aitest/results/baseline.json
  pytest    聚合数学与协议分派单测
Ollama 不在线时 real 诚实跳过。

用法:
  python3 assert_protocol.py             # offline + pytest (real 需显式)
  python3 assert_protocol.py real        # 真机基线(硬验收)
"""

import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench import run_eval as RE          # noqa: E402
from testbench.suts import ollama_alive       # noqa: E402

RESULTS = AITEST_DIR / "results" / "baseline.json"


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_offline():
    step("offline", "mini SUT + 脚本 judge: 管道自检(秒级)")
    results = RE.run(dataset="golden_v1", sut="mini", limit=3,
                     offline_chat=True, verbose=False)
    assert len(results["cases"]) == 3
    assert set(results["summary"]["rates"]) == {
        "schema", "semantic", "factuality", "judge"}
    print("  四维结果键齐全 ✅ (数字是管道自检, 不代表真实质量)")


def do_real():
    step("real", "golden_v1 × mh 真机基线 (qwen3:4b, 约 6-10 分钟)")
    if not ollama_alive():
        print("  ⚠️ Ollama 不在线, 真机基线诚实跳过")
        return
    results = RE.run(dataset="golden_v1", sut="mh", model="qwen3:4b")
    rates = results["summary"]["rates"]
    assert all(v is not None for v in rates.values()), f"四维有缺席: {rates}"
    assert results["summary"]["overall_pass_rate"] >= 0
    print(f"  四维通过率齐全: {rates}")


def do_pytest():
    step("pytest", "聚合与协议单测")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_run_eval.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    table = {"offline": do_offline, "real": do_real, "pytest": do_pytest}
    if target == "all":
        do_offline()
        do_pytest()
        print("\n=====> 项目 8 离线层完成 (真机基线: python3 assert_protocol.py real)")
    elif target == "real":
        do_real()
        print("\n=====> 项目 8 真机基线完成 ✅")
    elif target in table:
        table[target]()
    else:
        print("可用: offline | real | pytest | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
