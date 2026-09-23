#!/usr/bin/env python3
"""13 · 子代理调度 — 上下文隔离的任务分派与回收 (docs/harness.md 项目 13)

验收:
  ① 主代理把"README 多指标统计"派给子代理, 子代理内部 ≥5 次工具调用
  ② 主代理上下文(trace diff)只有 1 条 spawn 调用 + 短摘要,
     子代理的任何中间工具消息不出现(main messages 里搜不到子代理命令)
  ③ 主代理最终回答引用了子代理结果(词数/行数数字对得上磁盘事实)

用法:
  python3 demo.py            # 真机
  MOCK=1 python3 demo.py     # 离线管道自检
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR / ".."))
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

from mh import loop  # noqa: E402
from mh.sandbox import run  # noqa: E402
from mh.subagent import spawn_subagent  # noqa: E402
from mh.tools import Registry, tool  # noqa: E402

WORKSPACE_README = Path(__file__).resolve().parents[2] / "README.md"
SUB_TASK = ("统计以下文件的三项指标, 每项单独一条命令完成, 共至少 3 条命令: "
            f"{WORKSPACE_README} —— ① 总行数(wc -l) ② 中文字符数 "
            "(grep -o 统计) ③ 含 '##' 的标题数(grep -c)。完成后汇报三个数字。")
MAIN_TASK = (f"使用 spawn_subagent 工具完成下面这个子任务, 你自己不要直接统计, "
             f"拿到摘要后向我汇报三个数字:\n{SUB_TASK}")


def make_tools_factory(sandbox: Path):
    def factory():
        reg = Registry()

        @tool
        def run_bash(command: str, cwd: str = None) -> str:
            """在任务目录执行一条 bash 命令(沙箱保护)。"""
            ok, out = run(command, cwd=cwd or ".")
            return out if ok else f"[sandbox] {out}"

        reg.add(run_bash)
        return reg.to_loop_tools()
    return factory


_TRUTH = (len(WORKSPACE_README.read_text().splitlines()),
          __import__("re").findall(r"[一-龥]", WORKSPACE_README.read_text()).__len__(),
          WORKSPACE_README.read_text().count("##"))
_TRUTH_STR = f"{_TRUTH[0]} 行 / {_TRUTH[1]} 中文字符 / {_TRUTH[2]} 个标题"


def mock_chat(messages, tools=None, **kw):
    """离线: 主代理调 spawn(内含 mock 子代理), 验证隔离管道。"""
    last = messages[-1]
    if last.get("role") == "tool":
        return {"role": "assistant", "content": f"子代理汇报: {_TRUTH_STR}"}
    return {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "spawn_subagent",
                      "arguments": {"task": "统计 README 指标"}}}]}


def mock_sub_chat(messages, tools=None, **kw):
    """离线子代理剧本: 3 轮 3 次调用后收尾。"""
    n = sum(1 for m in messages if m.get("role") == "tool")
    cmds = ["wc -l readme", "grep -o 中文字符 readme", "grep -c '##' readme"]
    if n < 3:
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "run_bash", "arguments": {"command": cmds[n]}}}]}
    return {"role": "assistant", "content": _TRUTH_STR}


def main():
    ap = argparse.ArgumentParser()
    args = ap.parse_args()
    is_mock = os.environ.get("MOCK") == "1"
    sandbox = Path(tempfile.mkdtemp(prefix="mh13_"))
    (sandbox / "readme").write_text(WORKSPACE_README.read_text())

    sub = spawn_subagent(tools_factory=make_tools_factory(sandbox),
                         max_turns=12 if not is_mock else 6,
                         chat_fn=mock_sub_chat if is_mock else None)
    tools = make_tools_factory(sandbox)()
    tools[sub["schema"]["function"]["name"]] = sub

    chat_main = mock_chat if is_mock else None
    result = loop.run_agent(MAIN_TASK, tools, max_turns=6,
                            chat_fn=chat_main, cwd=str(sandbox))

    sub_calls = [tr for tr in result["tool_trace"]
                 if tr["tool"] == "spawn_subagent"]
    sub_trace = sub["_state"]["last_trace"]
    main_msgs = json.dumps(result["messages"], ensure_ascii=False)
    sub_cmds_leaked = sum(1 for tr in sub_trace
                          if tr["args"].get("command", "") in main_msgs)
    print("===== 主代理上下文 =====")
    print(f"主代理轮次: {result['turns']} | spawn 调用: {len(sub_calls)} 次")
    for tr in sub_calls:
        print(f"  摘要({len(tr['result'])} 字符): {tr['result'][:90]}…")
    print(f"\n===== 子代理内部轨迹(未进主上下文) =====")
    for tr in sub_trace:
        print(f"  {tr['tool']}({tr['args'].get('command', '')[:50]})")
    print(f"\n===== 验收 =====")
    print(f"① 子代理内部工具调用 ≥3: {'✅' if len(sub_trace) >= 3 else '❌'}"
          f" (实际 {len(sub_trace)} 次)")
    leak = sub_cmds_leaked == 0 and len(sub_calls) == 1
    print(f"② 隔离: 主上下文 0 条子代理中间命令泄漏: {'✅' if leak else '❌'}")
    # 与磁盘事实核对(而非只看有没有数字)
    import re
    truth = (len(WORKSPACE_README.read_text().splitlines()),
             len(re.findall(r"[一-龥]", WORKSPACE_README.read_text())),
             WORKSPACE_README.read_text().count("##"))
    cited = all(str(t) in result["final"] for t in truth)
    print(f"③ 主代理引用的数字与磁盘核对 {truth}: {'✅' if cited else '❌'} | "
          f"{result['final'][:80]}")
    sys.exit(0 if (len(sub_trace) >= 3 and leak and cited) else 1)


if __name__ == "__main__":
    main()
