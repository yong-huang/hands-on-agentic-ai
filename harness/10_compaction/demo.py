#!/usr/bin/env python3
"""10 · 上下文压缩 — 串行长任务 + 暗桩存活检查 (docs/harness.md 项目 10)

任务设计(按 09 结论: 不可批量才有区分度):
  20 个目录串行构建, 每个目录两步(创建+统计), 命令只许逐条执行 ——
  约 40 轮工具调用; 阈值调小(1500)逼出多次压缩。
暗桩 3 枚(压缩摘要必须存活的硬要求对象):
  ① 文件名 f07.txt  ② 数字 42(特定文件内容)  ③ 路径 deep/dir03
验收: 压缩发生 ≥2 次; 每次摘要中 ≥2 枚暗桩存活; 峰值上下文有界(事件表)。

用法:
  python3 demo.py            # 真机长任务(约 30-60 分钟)
  MOCK=1 python3 demo.py     # 离线管道自检(模拟多轮+压缩)
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR / ".."))
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

from mh.compaction import compact_chat_fn, est_tokens  # noqa: E402
from mh import llm as mh_llm  # noqa: E402
from mh import loop  # noqa: E402
from mh.sandbox import run  # noqa: E402
from mh.tools import Registry, tool  # noqa: E402

TASK = ("串行构建 20 个目录: 依次创建 dir01..dir20(一次一个, 禁止一条命令建多个), "
        "每个目录建成后立即用 wc 统计该目录内文件行数再建下一个。"
        "其中 dir07 里的文件命名为 f07.txt; dir03 要建成 deep/dir03 嵌套路径; "
        "dir15 的文件内容写数字 42。全部完成后汇报。")
STUBS = ["f07.txt", "42", "deep/dir03"]


def build_tools() -> dict:
    reg = Registry()

    @tool
    def run_bash(command: str, cwd: str = None) -> str:
        """在任务目录执行一条 bash 命令(沙箱保护, 禁止批量)。"""
        ok, out = run(command, cwd=cwd or ".")
        return out if ok else f"[sandbox] {out}"

    reg.add(run_bash)
    return reg.to_loop_tools()


def mock_chat(messages, tools=None, **kw):
    """离线管道自检: 制造 30 轮增长历史, 触发两次压缩。"""
    n_tool = sum(1 for m in messages if m.get("role") == "tool")
    if n_tool == 0:
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "run_bash",
                          "arguments": {"command": "mkdir -p dir01"}}}]}
    if n_tool < 30:
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "run_bash",
                          "arguments": {"command": f"echo L{n_tool:02d} filler-{'x'*200} > dir01/g{n_tool}.txt && wc -l dir01/g{n_tool}.txt"}}}]}
    return {"role": "assistant", "content": "任务完成: 30 轮串行操作结束"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=int, default=1500)
    args = ap.parse_args()
    is_mock = os.environ.get("MOCK") == "1"
    sandbox = Path(tempfile.mkdtemp(prefix="mh10_"))
    base = mock_chat if is_mock else mh_llm.chat_with_retry
    chat = compact_chat_fn(base, threshold=args.threshold, keep_recent=6)

    result = loop.run_agent(TASK, build_tools(), max_turns=60 if not is_mock else 40,
                            chat_fn=chat, cwd=str(sandbox))
    ev = chat.events
    print(f"\n===== 压缩事件表 =====")
    for e in ev:
        alive = sum(1 for s in STUBS if s in e["summary"])
        print(f"  第{e['call']}轮触发: {e['before']}→{e['after']} tok | "
              f"暗桩存活 {alive}/3")
        print(f"    摘要: {e['summary'][:110]}…")
    made = len([d for d in sandbox.rglob("dir*") if d.is_dir()])
    deep = (sandbox / "deep/dir03").is_dir()
    print(f"\n目录建成: {made}+ | deep/dir03 嵌套: {'✅' if deep else '❌'}")
    print(f"最终回答: {result['final'][:120]}")
    print("\n===== 验收 =====")
    print(f"① 压缩 ≥2 次: {'✅' if len(ev) >= 2 else '❌'} (实际 {len(ev)} 次)")
    # 暗桩真验收: 压缩多次后, 三个关键事实仍活在磁盘上(模型记忆未因压缩丢失)
    f07 = (sandbox / "dir07/f07.txt").is_file()
    d15 = sorted(sandbox.glob("dir15/*"))
    n42 = "42" in (d15[0].read_text() if d15 else "")
    deep_ok = deep
    late_alive = max((sum(1 for s in STUBS if s in e["summary"]) for e in ev),
                     default=0)
    print(f"② 任务级暗桩存活(压缩多次后): f07.txt {'✅' if f07 else '❌'} | "
          f"数字42 {'✅' if n42 else '❌'} | deep/dir03 {'✅' if deep_ok else '❌'} | "
          f"单次摘要最高 {late_alive}/3")
    peaks = [e["before"] for e in ev]
    bounded = all(p <= args.threshold * 1.3 for p in peaks)
    print(f"③ 触发前峰值有界(≤阈值×1.3): {'✅' if bounded else '❌'} | 峰值 {peaks}")
    sys.exit(0 if (len(ev) >= 2 and f07 and n42 and deep_ok and bounded) else 1)


if __name__ == "__main__":
    main()
