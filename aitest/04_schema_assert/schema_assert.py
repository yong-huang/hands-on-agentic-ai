#!/usr/bin/env python3
"""04 · 结构化输出断言 — JSON 提取/修复/校验 (docs/aitest.md 项目 4)

验收: 一条命令演示断言管线三级处理——
  selftest  10 条预置坏输出走规则修复, ≥9/10 过 schema(离线, 硬验收)
  llm_live  真机两连: ①让模型直接按 schema 回答并断言  ②喂坏 JSON 走 LLM 修复重试
  pytest    断言模块测试
Ollama 不在线时 llm_live 诚实跳过, 其余照常。

用法:
  python3 schema_assert.py           # 全流程(含真机)
  python3 schema_assert.py selftest  # 只跑离线自检
"""

import json
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
from testbench.asserts import schema as S  # noqa: E402
from testbench.suts import ollama_alive  # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_selftest():
    step("selftest", "10 条坏输出 × 规则修复(离线硬验收)")
    assert S.selftest(), "规则修复 <9/10"


def do_llm_live():
    step("llm_live", "真机: 模型按 schema 回答 + 坏 JSON 走 LLM 修复重试")
    if not ollama_alive():
        print("  ⚠️ Ollama 不在线, 真机段诚实跳过 —— 预期行为不是故障")
        print("     启动: ollama serve 后重跑 llm_live")
        return

    # ① 模型直接按 schema 回答 → 断言应通过(必要时规则小修)
    prompt = ('只输出一个 JSON 对象, 不要任何解释: {"answer": <一句话回答什么是端口 80>, '
              '"confidence": <0 到 1 的数字>} /no_think')
    raw = qa_llm.chat([{"role": "user", "content": prompt}], temperature=0, num_predict=200)
    r1 = S.check(raw)
    print(f"  [模型直答] ok={r1.ok} 修复={r1.repairs or '无'}")
    assert r1.ok, f"模型直答未过断言: {r1.error}"

    # ② 喂一条规则修不好的坏输出(缺 confidence) → LLM 修复重试路径
    broken = '{"answer": "json 只有半个"}'
    r2 = S.check(broken, chat_fn=lambda msgs, **kw: qa_llm.chat(msgs, temperature=0,
                                                                num_predict=200))
    print(f"  [LLM 重试] ok={r2.ok} 修复={r2.repairs}")
    assert r2.ok, f"LLM 修复重试失败: {r2.error}"
    print("  断言: 直答过 schema ✅ / 缺字段由 LLM 重试补齐 ✅")


def do_pytest():
    step("pytest", "断言模块测试(离线)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_schema_assert.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    table = {"selftest": do_selftest, "llm_live": do_llm_live, "pytest": do_pytest}
    if target in table:
        table[target]()
    elif target == "all":
        do_selftest()
        do_llm_live()
        do_pytest()
        print("\n=====> 项目 4 验收完成: 结构化输出断言 ✅")
    else:
        print("可用: selftest | llm_live | pytest | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
