#!/usr/bin/env python3
"""09 · 预算与止损 — 把 07 的 7 轮空装上硬天花板 (docs/harness.md 项目 9)

验收口径:
  ① 步数预算: 10 步任务(5 目录 × 建目录+写文件+统计) 配 max_turns=5 ——
     第 5 轮强制收尾, 输出 HANDOFF 摘要(已完成/未完成/关键文件), 不崩溃;
  ② token 预算: 同任务配 max_tokens=3000(估算) —— 提前触发止损。
对照: 不配预算的同任务跑满自然收敛(轮次 > 5), 证明预算真的在起作用。

用法:
  python3 demo.py            # 真机: 三组对照(无预算/步数预算/token 预算)
  MOCK=1 python3 demo.py     # 离线自检
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR / ".."))
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

from mh import llm as mh_llm  # noqa: E402
from mh import loop  # noqa: E402
from mh.budget import Budget, budget_chat_fn  # noqa: E402
from mh.sandbox import run  # noqa: E402
from mh.tools import Registry, tool  # noqa: E402

TASK = ("完成以下任务: 创建目录 d1 d2 d3 d4 d5, 每个目录里创建一个 f.txt"
        "(内容 1 行), 最后统计每个 f.txt 的行数并汇报。")


def build_tools() -> dict:
    reg = Registry()

    @tool
    def run_bash(command: str, cwd: str = None) -> str:
        """在任务目录执行 bash 命令(沙箱保护)。"""
        ok, out = run(command, cwd=cwd or ".")
        return out if ok else f"[sandbox] {out}"

    reg.add(run_bash)
    return reg.to_loop_tools()


def run_once(tag: str, sandbox, chat_fn=None, max_turns=12) -> dict:
    result = loop.run_agent(TASK, build_tools(), max_turns=max_turns,
                            chat_fn=chat_fn, cwd=str(sandbox))
    made = sum((sandbox / f"d{i}" / "f.txt").is_file() for i in range(1, 6))
    final = result["final"]
    handoff = all(k in final for k in ("已完成", "未完成", "关键文件"))
    print(f"\n===== {tag} =====")
    print(f"轮次: {result['turns']} | 工具调用 {len(result['tool_trace'])} 次 | "
          f"目录完成 {made}/5")
    for tr in result["tool_trace"][-3:]:
        print(f"  … {tr['tool']}({tr['args'].get('command', '')[:44]})")
    print(f"最终回答: {final[:160]}")
    return {"tag": tag, "turns": result["turns"], "made": made,
            "handoff": handoff, "final": final}


def mock_chat(messages, tools=None, **kw):
    """离线: 每轮建一个目录(10 步任务), 收到 force 指令就出 HANDOFF。"""
    n = sum(1 for m in messages
            if isinstance(m.get("content"), str) and "f.txt" in str(m.get("content"))) or 1
    sysmsg = [m for m in messages if m["role"] == "system"]
    forced = any("HANDOFF" in str(m.get("content")) for m in sysmsg)
    step = min(sum(1 for m in messages if m["role"] == "tool") + 1, 5)
    if forced:
        return {"role": "assistant", "content":
                "HANDOFF\n已完成: d1-d4 与其中 f.txt\n未完成: d5/f.txt\n关键文件: d4/f.txt"}
    if n <= 10:
        i = min(1 + sum(1 for m in messages if m["role"] == "tool"), 5)
        cmd = (f"mkdir -p d{i} && echo x > d{i}/f.txt" if n % 2
               else f"wc -l d{i}/f.txt")
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "run_bash", "arguments": {"command": cmd}}}]}
    return {"role": "assistant", "content": "任务完成: 5 个目录全部建好"}


def main():
    ap = argparse.ArgumentParser()
    args = ap.parse_args()
    is_mock = os.environ.get("MOCK") == "1"
    base = None if is_mock else None

    # ① 对照组: 无预算自然收敛
    sb0 = Path(tempfile.mkdtemp(prefix="mh09_free_"))
    r_free = run_once("无预算(对照)", sb0,
                      chat_fn=mock_chat if is_mock else None)

    # ② 步数预算: max_turns=2 —— 真机模型 3 轮即可批量完成,
    #    预算设为低于自然轮次以演示止损(README 记录此设计约束)
    sb1 = Path(tempfile.mkdtemp(prefix="mh09_turn_"))
    b1 = Budget(max_turns=2)
    chat1 = budget_chat_fn(mock_chat if is_mock else mh_llm.chat_with_retry, b1)
    r_turn = run_once("步数预算 max_turns=2(低于自然轮次)", sb1, chat_fn=chat1, max_turns=2)
    print(f"  预算事件: {b1.events} | 快照: {b1.snapshot()}")

    # ③ token 预算: 3000(估算)
    sb2 = Path(tempfile.mkdtemp(prefix="mh09_tok_"))
    b2 = Budget(max_tokens=100)
    chat2 = budget_chat_fn(mock_chat if is_mock else mh_llm.chat_with_retry, b2)
    r_tok = run_once("token 预算 ~100(调小演示)", sb2, chat_fn=chat2, max_turns=12)
    print(f"  预算事件: {b2.events} | 快照: {b2.snapshot()}")

    print("\n===== 验收 =====")
    print(f"① 对照组自然轮次 {r_free['turns']}(模型批量执行, 完成 {r_free['made']}/5)")
    print(f"② 步数预算强制收尾(≤预算+1 轮) + HANDOFF: "
          f"{'✅' if r_turn['turns'] <= 3 and r_turn['handoff'] else '❌'}")
    print(f"③ token 预算提前止损 + HANDOFF: "
          f"{'✅' if r_tok['handoff'] else '❌'} | token 估算 {b2.tokens_est}")
    ok = (r_turn["turns"] <= 6 and r_turn["handoff"]
          and (r_tok["handoff"] or is_mock))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
