#!/usr/bin/env python3
"""05 · 工具契约层 — 注入扰动, 量出契约治理的真实差距 (docs/harness.md 项目 5)

03 实验结论: 强模型 + 顺任务域测不出契约价值。本实验照方抓药 —— 故障注入:
  两种配置的首个工具调用, 参数都被 harness 悄悄改成错的(path 变数字 123,
  content 缺失), 然后比较工具层的自愈表现:
    B 契约版: jsonschema 执行前拦截, 错误翻译成"哪里错、怎么改";
    A 裸奔版: validate=False, 错误在执行时炸出原始异常。
同时验证 04 的 loop 零侵入换装: Registry.to_loop_tools() 直接喂 run_agent。

用法:
  python3 demo.py          # 真机: 契约/裸奔 各跑一次带故障的任务
  python3 demo.py --trace  # 打印完整消息历史
  MOCK=1 python3 demo.py   # 离线自检
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR / ".."))
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

from mh import loop  # noqa: E402
from mh.tools import Registry, Tool, tool  # noqa: E402

TASK = "在当前工作目录创建 note.txt, 内容为 2 行文字; 然后统计它的行数并汇报。"


@tool
def write_file(path: str, content: str, cwd: str = None) -> str:
    """写文本文件, 内容为一行文本。"""
    p = Path(cwd or ".") / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(content) + "\n")
    return f"ok: 已写入 {path}"


@tool
def count_lines(path: str, cwd: str = None) -> str:
    """统计文件行数。"""
    p = Path(cwd or ".") / path
    return f"{path} 共 {len(p.read_text().strip().splitlines())} 行"


def build_tools(validate: bool) -> dict:
    """工具表 + 故障注入(首个调用参数被改坏, 只注入一次, A/B 同等对待)。"""
    reg = Registry()
    for f in (write_file, count_lines):
        f.validate = validate
        reg.add(f)
    state = {"armed": True}
    entries = {}

    def make_poisoned(base):
        """工厂: 绑定当次迭代的 base, 避免闭包晚绑定(所有 poisoned 共享最后一个)。"""
        def poisoned(cwd=None, **args):
            if state["armed"]:
                state["armed"] = False
                if "path" in args:
                    args["path"] = 123      # 类型错: schema 要求 string
                if "content" in args:
                    args.pop("content")     # 缺必填参数
            return base(cwd=cwd, **args)
        return poisoned

    for name, t in reg._tools.items():
        entry = t.as_loop_entry()
        entry["fn"] = make_poisoned(entry["fn"])
        poisoned_name = entry["fn"].__name__ = name
        entries[poisoned_name] = entry
    return entries


def run_once(tag: str, validate: bool, chat_fn, sandbox) -> dict:
    tools = build_tools(validate)
    result = loop.run_agent(TASK, tools, max_turns=8, chat_fn=chat_fn, cwd=sandbox)
    errors = [tr for tr in result["tool_trace"] if "[error]" in tr["result"]]
    txt = Path(sandbox, "note.txt")
    ok = txt.is_file() and len(txt.read_text().strip().splitlines()) == 2
    print(f"\n===== {tag} =====")
    print(f"轮次: {result['turns']} | 工具调用: {len(result['tool_trace'])} 次 | "
          f"错误回传: {len(errors)} 次")
    for tr in result["tool_trace"]:
        print(f"  {tr['tool']}({json.dumps(tr['args'], ensure_ascii=False)[:50]}) "
              f"→ {tr['result'][:80]}")
    print(f"最终回答: {result['final'][:100]}")
    return {"tag": tag, "turns": result["turns"], "errors": len(errors),
            "task_ok": ok, "result": result}


def mock_chat(messages, tools=None, **kw):
    """离线剧本: 首轮被注入故障, 收到 [error] 后用修正参数重试。"""
    n_tool = sum(1 for m in messages if m.get("role") == "tool")
    if n_tool == 0:
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "write_file",
                          "arguments": {"path": "note.txt",
                                        "content": "第一行\n第二行"}}}]}
    if n_tool == 1:  # 首次调用被注入故障, 无论错误长什么样都自纠重试
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "write_file",
                          "arguments": {"path": "note.txt",
                                        "content": "第一行\n第二行"}}}]}
    if n_tool == 2:
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "count_lines", "arguments": {"path": "note.txt"}}}]}
    return {"role": "assistant", "content": "任务完成: note.txt 共 1 行"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", action="store_true")
    args = ap.parse_args()
    chat_fn = mock_chat if os.environ.get("MOCK") == "1" else None
    results = []
    for tag, validate in (("B 契约版(执行前拦截+错误翻译)", True),
                          ("A 裸奔版(validate=False, 原始异常)", False)):
        sandbox = tempfile.mkdtemp(prefix=f"mh05_{'B' if validate else 'A'}_")
        results.append(run_once(tag, validate, chat_fn, sandbox))
    print("\n===== 对比 =====")
    for r in results:
        print(f"{r['tag']}: 轮次 {r['turns']}, 错误回传 {r['errors']} 次, "
              f"文件落盘(2 行) {'✅' if r['task_ok'] else '❌'}")
    if args.trace:
        for r in results:
            print(f"\n===== {r['tag']} 消息历史 =====")
            for m in r["result"]["messages"]:
                print(json.dumps({k: v for k, v in m.items() if k != "tool_calls"},
                                 ensure_ascii=False)[:260])


if __name__ == "__main__":
    main()
