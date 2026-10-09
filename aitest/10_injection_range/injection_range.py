#!/usr/bin/env python3
"""10 · 提示注入靶场 — ASR 度量与权限对照 (docs/aitest.md 项目 10)

验收: 一条命令跑双 profile 对照——
  pytest    权限门语义/判定双通道/弹药库完整性(离线 8 条)
  compare   15 条 payload × baseline|full 两配置真机(约 15-25 分钟),
            ASR 均落盘且 full < baseline(硬验收)
Ollama 不在线时 compare 诚实跳过。

用法:
  python3 injection_range.py           # pytest(离线)
  python3 injection_range.py compare   # 真机对照(硬验收)
"""

import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench.redteam import injection as I  # noqa: E402
from testbench.suts import ollama_alive       # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "离线单测(权限门/判定通道/弹药库)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_injection.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def do_compare():
    step("compare", "15 payload × 双 profile (硬验收: full < baseline)")
    result = I.run_compare()
    out = AITEST_DIR / "results" / "injection_asr.json"
    out.parent.mkdir(exist_ok=True)
    import json
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"  落盘 -> {out}")
    assert result["verdict_gate_effective"], "full ASR 未低于 baseline"
    print("  断言: full < baseline ✅ 权限门有效")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    table = {"pytest": do_pytest, "compare": do_compare}
    if target == "all":
        do_pytest()
        if ollama_alive():
            do_compare()
        else:
            print("\n=====> Ollama 不在线: compare 诚实跳过")
    elif target in table:
        table[target]()
    else:
        print("可用: pytest | compare | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
