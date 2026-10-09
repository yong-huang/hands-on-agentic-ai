#!/usr/bin/env python3
"""13 · 安全门统一扫描器 (⛓️, docs/aitest.md 项目 13)

验收: 一条命令两态验证——
  正常态: 真机三维扫描(注入子集/越狱全量/fuzz 子集), 默认阈值下 verdict=pass
  失败态: MOCK 离线 + 故意收紧阈值, CLI 退出码 = 1 且报告标红 FAIL
Ollama 不在线时真实扫描诚实跳过(失败态用 MOCK 始终可验)。

用法:
  python3 security_scan.py            # pytest(离线)
  python3 security_scan.py all        # pytest + 真机扫描 + 失败态两态
"""

import os
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench import security_scan as S  # noqa: E402
from testbench.suts import ollama_alive    # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "离线单测(门禁判定/组装/渲染)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_security_scan.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def do_real():
    step("scan", "真机三维扫描(mh, qwen3:4b; 注入/越狱/fuzz 按子集)")
    rep = S.scan(sut="mh", model="qwen3:4b",
                 limits={"injection": 6, "jailbreak": None, "fuzz": 6})
    print("\n" + S.render(rep))
    assert rep["verdict"] == "pass", rep["failed_dimensions"]
    assert not rep["failed_dimensions"]
    return rep


def do_strict():
    step("strict", "收紧阈值(不可能达标): 必须判 fail(两态可验)")
    os.environ["MOCK"] = "1"      # 离线跑, 秒级
    try:
        rep = S.scan(sut="mini", model=None,
                     limits={"injection": 3, "jailbreak": 3, "fuzz": 3},
                     thresholds={"injection_asr": -0.01})   # 不可能达标
    finally:
        os.environ.pop("MOCK", None)
    print("\n" + S.render(rep))
    assert rep["verdict"] == "fail"
    assert "injection" in rep["failed_dimensions"]
    return rep


def do_cli_exit():
    step("cli-exit", "CLI 退出码: MOCK 离线 + 不可能阈值 -> 期望 1")
    env = dict(os.environ, MOCK="1")
    p = subprocess.run(
        [sys.executable, "-m", "testbench.security_scan", "--sut", "mini",
         "--injection-limit", "3", "--jailbreak-limit", "3",
         "--fuzz-limit", "3", "--threshold-refusal", "1.1"],
        cwd=str(AITEST_DIR), capture_output=True, text=True, env=env)
    out = p.stdout + p.stderr
    print(f"  exit={p.returncode} | 报告含 FAIL: {'FAIL' in out}")
    assert p.returncode == 1
    assert "FAIL" in out


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    if target == "all":
        do_pytest()
        if ollama_alive() and os.environ.get("MOCK") != "1":
            do_real()
        else:
            print("\n=====> Ollama 不在线或 MOCK=1: 真机扫描诚实跳过")
        do_strict()
        do_cli_exit()
    elif target == "pytest":
        do_pytest()
    elif target == "scan":
        do_real()
    elif target == "strict":
        do_strict()
    elif target == "cli-exit":
        do_cli_exit()
    else:
        print("可用: pytest | scan | strict | cli-exit | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
