#!/usr/bin/env python3
"""14 · 工具调用契约测试 (docs/aitest.md 项目 14)

验收: 一条命令四态自证——
  normal       正确工具描述: 全部契约绿灯
  wrong_type   schema 声明错型: 契约抓到"参数类型错"
  missing_param 必填参数被抹掉: 契约抓到"漏参"
  extra_call   描述被写坏+等价诱饵: 契约抓到"多余调用+漏调"
Ollama 不在线时如实跳过。

用法:
  python3 tool_contract.py            # pytest(离线)
  python3 tool_contract.py all        # pytest + 真机四态(qwen3:4b)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

from testbench.suites import tool_contract as T  # noqa: E402
from testbench.suts import ollama_alive          # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_pytest():
    step("pytest", "离线单测(两类断言/变体构造/录制包装)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_tool_contract.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


EXPECT = {
    "normal": None,                # 期望零违规
    "wrong_type": "wrong_type",
    "missing_param": "missing_param",
    "extra_call": "extra_call",
}


def do_real():
    step("real", "真机四态(qwen3:4b)")
    results = {}
    for variant, expect_kind in EXPECT.items():
        rep = T.run_contract(variant, model="qwen3:4b")
        results[rep["variant"]] = rep
        if expect_kind is None:
            assert rep["violations"] == [], rep["violations"]
        else:
            kinds = {v["kind"] for v in rep["violations"]}
            assert expect_kind in kinds, f"{variant} 未抓到 {expect_kind}: {kinds}"
    out = AITEST_DIR / "results" / "tool_contract.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n  四态: " + " | ".join(
        f"{k}:{len(v['violations'])} 违规" for k, v in results.items()))
    print(f"  落盘 -> {out}")
    return results


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    if target == "all":
        do_pytest()
        if ollama_alive():
            do_real()
        else:
            print("\n=====> Ollama 不在线: 真机四态诚实跳过")
    elif target == "pytest":
        do_pytest()
    elif target == "real":
        do_real()
    else:
        print("可用: pytest | real | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
