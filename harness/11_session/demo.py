#!/usr/bin/env python3
"""11 · 会话持久化与崩溃恢复 — kill -9 后从断点爬起 (docs/harness.md 项目 11)

流程:
  Phase A(子进程): 串行创建 d1..d8(一次一个, 不可批量), 每轮快照+副作用清单
  父进程: 启动子进程 → 等它做完若干目录 → kill -9 → 核对 checkpoint 存在
  Phase B(本进程): 加载 checkpoint → 恢复消息历史 + 已完成命令跳过重放 →
  断言: ① 已完成目录的文件 mtime 不变(未重复执行) ② 任务最终完成
        ③ 恢复事件在 checkpoint 里 ④ done_commands 跳过发生过

用法:
  python3 demo.py              # 完整 kill -9 → resume 流程
  python3 demo.py --worker     # 仅 Phase A(被父进程调用)
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR / ".."))
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

from mh import loop  # noqa: E402
from mh import llm as mh_llm  # noqa: E402
from mh.sandbox import run  # noqa: E402
from mh.session import (SessionStore, record_chat_fn,  # noqa: E402
                        skip_redo_tools, snapshotting_tools)
from mh.tools import Registry, tool  # noqa: E402

TASK = ("串行创建目录 d1 到 d8: 一次只建一个, 每个目录里建 f.txt(内容 1 行), "
        "建完一个立刻做下一个, 全部完成后汇报。禁止一条命令建多个目录。")


def build_tools() -> dict:
    reg = Registry()

    @tool
    def run_bash(command: str, cwd: str = None) -> str:
        """在任务目录执行一条 bash 命令(沙箱保护)。"""
        ok, out = run(command, cwd=cwd or ".")
        return out if ok else f"[sandbox] {out}"

    reg.add(run_bash)
    return reg.to_loop_tools()


def worker(checkpoint: str, sandbox: str):
    """Phase A 子进程: 带 SessionStore 跑任务(会被 kill -9 打断)。"""
    store = SessionStore(checkpoint)
    tools = snapshotting_tools(build_tools(), store)
    chat = record_chat_fn(mh_llm.chat_with_retry, store)
    loop.run_agent(TASK, tools, max_turns=25, chat_fn=chat, cwd=sandbox)
    print("[worker] 任务自然完成(不应发生, 父进程会提前杀)")


def mtimes(root: Path) -> dict:
    return {str(p.relative_to(root)): p.stat().st_mtime_ns
            for p in sorted(root.rglob("f.txt"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--checkpoint")
    ap.add_argument("--sandbox")
    args = ap.parse_args()
    if args.worker:
        worker(args.checkpoint, args.sandbox)
        return

    lab = Path(tempfile.mkdtemp(prefix="mh11_"))
    ckpt, sandbox = lab / "checkpoint.json", lab / "work"
    sandbox.mkdir()

    # Phase A: 启动子进程, 给它 ~35s(约做 3-5 个目录)后 kill -9
    proc = subprocess.Popen(
        [sys.executable, __file__, "--worker",
         "--checkpoint", str(ckpt), "--sandbox", str(sandbox)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(13)
    proc.kill()
    proc.wait()
    print("===== Phase A: kill -9 =====")
    assert ckpt.exists(), "checkpoint 未落盘"
    store_probe = SessionStore(ckpt)
    pre = store_probe.data
    n_done = len(pre["done_commands"])
    print(f"崩溃前: 历史消息 {len(pre['messages'])} 条, "
          f"已成功命令 {n_done} 条, 已建目录 "
          f"{len(list(sandbox.rglob('d*')))} 个")

    # Phase B: 恢复
    print("===== Phase B: resume =====")
    store = SessionStore(ckpt)
    before_mtimes = mtimes(sandbox)
    tools = skip_redo_tools(build_tools(), store)
    # 确定性断言: 拿崩溃前已成功的命令直接再调, 必须被跳过重放
    if pre["done_commands"]:
        probe = tools["run_bash"]["fn"](cwd=str(sandbox),
                                        command=pre["done_commands"][0])
        skip_ok = "跳过重放" in probe
        print(f"跳过重放直调探针: {probe[:60]} → {'✅' if skip_ok else '❌'}")
    else:
        skip_ok = False
    result = loop.run_agent(TASK, build_tools(), max_turns=25,
                            chat_fn=record_chat_fn(mh_llm.chat_with_retry, store),
                            cwd=str(sandbox), messages=store_probe.resume_messages())
    after_mtimes = mtimes(sandbox)
    old = set(before_mtimes)
    untouched = all(after_mtimes[k] == before_mtimes[k] for k in old)
    complete = all((sandbox / f"d{i}" / "f.txt").is_file() for i in range(1, 9))
    print(f"\n===== 验收 =====")
    print(f"① 恢复消息 {len(pre['messages'])} 条注入, 循环继续: "
          f"{result['turns']} 轮")
    print(f"② 崩溃前 {len(old)} 个 f.txt 的 mtime 全部未变(未重复执行): "
          f"{'✅' if untouched else '❌'}")
    print(f"③ 8 个目录最终全部建成: {'✅' if complete else '❌'} "
          f"(实际 {len(list(sandbox.rglob('d*')))})")
    print(f"④ 恢复事件留档: {store.data['recoveries']}")
    print(f"⑤ 跳过重放直调: {'✅' if skip_ok else '❌'} | "
          f"模型侧重放: {sum(1 for tr in result['tool_trace'] if '跳过重放' in str(tr))} 次")
    print(f"最终回答: {result['final'][:120]}")
    ok = untouched and complete and bool(store.data["recoveries"]) and skip_ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
