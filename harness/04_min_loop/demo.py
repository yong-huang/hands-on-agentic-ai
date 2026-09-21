#!/usr/bin/env python3
"""04 · 最小 Agent Loop — mini-harness v0.1 首航 (docs/harness.md 项目 4)

验收: python3 demo.py 一条命令, agent 全自主完成两步任务——
  1. 在沙箱目录创建 hello.py(内容为打印今天日期的脚本)
  2. 运行 hello.py 并汇报输出
全程零人工干预; --trace 可看每一轮完整消息历史。

用法:
  python3 demo.py                # 真机 (LLM_MODEL 可切换)
  python3 demo.py --trace        # 打印完整消息历史
  MOCK=1 python3 demo.py         # 离线演示
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR / ".."))
os_no_proxy = __import__("os").environ.setdefault
os_no_proxy("NO_PROXY", "localhost,127.0.0.1")
os_no_proxy("no_proxy", "localhost,127.0.0.1")

from mh import loop  # noqa: E402

TASK = ("在当前工作目录创建 hello.py, 内容是一个打印今天日期(YYYY-MM-DD)的 Python 脚本; "
        "然后运行它, 并告诉我脚本的输出。")


def run_bash(command: str, cwd: str = None) -> str:
    """项目 4 的唯一工具: 最小执行层(06 项目会换装沙箱)。"""
    p = subprocess.run(["bash", "-c", command], cwd=cwd,
                       capture_output=True, text=True, timeout=15)
    return (p.stdout + p.stderr).strip() or "(无输出)"


TOOLS = {
    "run_bash": {
        "desc": "在任务目录执行 bash 命令, 返回 stdout+stderr",
        "schema": {"type": "function", "function": {
            "name": "run_bash",
            "description": "在任务目录执行 bash 命令, 返回 stdout+stderr",
            "parameters": {"type": "object",
                           "properties": {"command": {"type": "string",
                                                      "description": "要执行的 bash 命令"}},
                           "required": ["command"]}},
        },
        "fn": run_bash,
    },
}


def mock_chat(messages, tools=None, **kw):
    """离线剧本: 真实走完整 loop 协议(message.tool_calls → role:tool)。"""
    last = messages[-1]
    if last.get("role") == "tool":
        if "hello.py" in (last.get("content") or "") and "脚本" not in (last.get("content") or ""):
            pass
        step = sum(1 for m in messages if m.get("role") == "tool")
    else:
        step = sum(1 for m in messages if m.get("role") == "tool")
    if step == 0:
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "run_bash",
                          "arguments": {"command": "printf 'from datetime import date\\nprint(date.today())' > hello.py"}}}]}
    if step == 1:
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "run_bash", "arguments": {"command": "python3 hello.py"}}}]}
    return {"role": "assistant", "content": f"任务完成: hello.py 已创建并运行, 输出 {date.today()}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", action="store_true", help="打印完整消息历史")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    sandbox = tempfile.mkdtemp(prefix="mh04_")
    chat_fn = mock_chat if __import__("os").environ.get("MOCK") == "1" else None

    def on_event(kind, *info):
        if kind == "round":
            turn, content, calls = info
            print(f"--- 第 {turn} 轮 ---")
            for name, cargs in calls:
                print(f"  >> {name}({json.dumps(cargs, ensure_ascii=False)[:100]})")
        else:
            print(f"--- 达到轮次上限 {info[0]} ---")

    result = loop.run_agent(TASK, TOOLS, max_turns=8, chat_fn=chat_fn,
                            cwd=sandbox, on_event=on_event)
    script = Path(sandbox) / "hello.py"
    out = ""
    if script.is_file():
        r = subprocess.run(["python3", "hello.py"], cwd=sandbox,
                           capture_output=True, text=True, timeout=15)
        out = r.stdout.strip()
    ok = script.is_file() and out == date.today().isoformat()
    print(f"\n[验收] hello.py 存在: {'✅' if script.is_file() else '❌'}")
    print(f"[验收] 脚本输出 = 今天({date.today().isoformat()}): {out or '(无)'} {'✅' if ok else '❌'}")
    print(f"[验收] 轮次: {result['turns']}, 工具调用: {len(result['tool_trace'])} 次")
    print(f"[验收] 最终回答: {result['final'][:120]}")
    if args.trace:
        print("\n===== 完整消息历史 =====")
        for m in result["messages"]:
            body = {k: v for k, v in m.items() if k != "tool_calls"}
            print(json.dumps(body, ensure_ascii=False)[:300])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
