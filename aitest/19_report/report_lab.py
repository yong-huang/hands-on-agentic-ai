#!/usr/bin/env python3
"""19 · 评测报告生成器 (docs/aitest.md 项目 19)

验收: 一条命令两段——
  pytest  离线单测: 五区块/数字内嵌/篡改检出/红色高亮/CLI
  real    用 18 线真实产出的 results.json 生成 report.html 并抽查数字
(18 的 run_results.json 不存在时先提示跑 18; 全流程离线)

用法:
  python3 report_lab.py            # pytest(离线)
  python3 report_lab.py all        # pytest + 真数据生成报告
"""

import json
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench import report as RP  # noqa: E402

RUN_RESULTS = AITEST_DIR / "results" / "run_results.json"


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "离线单测(五区块/抽查/篡改检出)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_report.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def do_real():
    step("real", "用 18 线 results.json 生成报告并抽查")
    if not RUN_RESULTS.exists():
        print(f"  ⏭️ 缺少 {RUN_RESULTS}: 先跑 18 线 smoke(examples: "
              f"python3 -m testbench run --level smoke)")
        return None
    report = json.loads(RUN_RESULTS.read_text(encoding="utf-8"))
    html = RP.build_html(report)
    out = AITEST_DIR / "results" / "report.html"
    out.write_text(html, encoding="utf-8")
    checks = RP.verify(html, report, samples=3)
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} 抽查 {name}")
    print(f"  五区块 html -> {out} ({len(html)} 字节)")
    assert checks and all(ok for _, ok in checks)
    return out


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    if target == "all":
        do_pytest()
        do_real()
    elif target == "pytest":
        do_pytest()
    elif target == "real":
        do_real()
    else:
        print("可用: pytest | real | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
