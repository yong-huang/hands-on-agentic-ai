#!/usr/bin/env python3
"""21 · 🏁 终极四维体检 (docs/aitest.md 项目 21)

验收: 一条命令两段——
  pytest  离线单测: 四维汇总/评级/建议/报告渲染
  quick   真机 quick 体检(smoke 口径, 约 7 分钟): 产出 FINAL_REPORT.md
(全量口径用 `make checkup`, 约 30 分钟; 离线时真机模块 skipped, 评级照常)

用法:
  python3 checkup_lab.py            # pytest(离线)
  python3 checkup_lab.py all        # pytest + quick 体检
"""

import os
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from final_checkup import checkup as C  # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "离线单测(四维汇总/评级/建议/渲染)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_checkup.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def do_quick():
    step("quick", "四维体检(smoke 口径) -> FINAL_REPORT.md")
    res = C.run_checkup(level="quick", model="qwen3:4b",
                        out=AITEST_DIR / "FINAL_REPORT.md")
    md = Path(res["path"]).read_text(encoding="utf-8")
    for sec in ("## 总评级", "## 功能", "## 安全", "## 性能", "## 回归",
                "## 修复建议"):
        assert sec in md, f"报告缺区块: {sec}"
    print(f"  四区块 + 评级 + 建议齐全 | 评级 {res['summary']['grade']}")
    return res


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    if target == "all":
        do_pytest()
        do_quick()
    elif target == "pytest":
        do_pytest()
    elif target == "quick":
        do_quick()
    else:
        print("可用: pytest | quick | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
