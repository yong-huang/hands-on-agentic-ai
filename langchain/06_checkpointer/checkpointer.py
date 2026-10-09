"""
06 · Checkpointer：断点恢复与时间旅行

纯离线实验（不调用任何模型），用 SqliteSaver 见证三件事：
  A. 崩溃恢复 — 子进程跑到步骤 4 被 SIGKILL（真 kill -9），重启后用同一
     thread 续跑：已完成步骤不重算，落盘的 ledger 可取证
  B. 检查点历史 — get_state_history 拿到每个超步的快照，长度单调递增
  C. 时间旅行 — 从历史检查点 update_state 改输入分叉重放，得到新分支，
     旧分支的最终快照仍可单独读取

用法:
  python langchain/06_checkpointer/checkpointer.py            # 主流程（会 fork 子进程）
  python langchain/06_checkpointer/checkpointer.py --worker --crash-at 4 --workdir DIR --db DB
"""

import argparse
import operator
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Annotated, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

STEPS = ["s1", "s2", "s3", "s4", "s5", "s6"]

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, ok))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def section(title):
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")


class JobState(TypedDict):
    done_steps: Annotated[list[str], operator.add]
    branch: str


def make_step(i, workdir, crash_at):
    name = f"s{i}"

    def step(_state):
        if crash_at == i:
            # 检查点是后台线程异步落盘的：等一拍再杀，让 s3 的检查点写完，
            # 这样恢复时从 s4 续跑（不等待的话最近 1-2 个检查点可能丢失，
            # 表现为恢复后重算几步——即"至少一次"语义，见 README 踩坑 1）
            time.sleep(1.0)
            os.kill(os.getpid(), signal.SIGKILL)
        with open(os.path.join(workdir, "ledger.txt"), "a", encoding="utf-8") as f:
            f.write(name + "\n")
        return {"done_steps": [name]}

    return step


def build_graph(db_path, workdir, crash_at=None):
    g = StateGraph(JobState)
    for i in range(1, len(STEPS) + 1):
        g.add_node(f"s{i}", make_step(i, workdir, crash_at))
        if i == 1:
            g.add_edge(START, f"s{i}")
        else:
            g.add_edge(f"s{i - 1}", f"s{i}")
    g.add_edge(f"s{len(STEPS)}", END)
    # SqliteSaver 在后台线程写检查点：连接必须允许跨线程（from_conn_string 同款做法）
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return g.compile(checkpointer=SqliteSaver(conn))


def read_ledger(workdir):
    path = os.path.join(workdir, "ledger.txt")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def run_worker(workdir, db, crash_at):
    graph = build_graph(db, workdir, crash_at)
    graph.invoke({"done_steps": [], "branch": "original"},
                 {"configurable": {"thread_id": "crash-job"}})


def part_a_crash_resume(tmp):
    section("[A] 崩溃恢复：SIGKILL 后同 thread 续跑")
    workdir = os.path.join(tmp, "a")
    os.makedirs(workdir)
    db = os.path.join(workdir, "job.db")

    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__),
         "--worker", "--crash-at", "4", "--workdir", workdir, "--db", db],
        capture_output=True, text=True,
    )
    print(f"  子进程退出: returncode={proc.returncode}（-9 = SIGKILL）")
    check("工作进程在步骤 4 被 SIGKILL 杀死", proc.returncode == -9)

    ledger = read_ledger(workdir)
    print(f"  崩溃时 ledger: {ledger}")
    check("崩溃时只留下已完成步骤 s1-s3", ledger == ["s1", "s2", "s3"])

    graph = build_graph(db, workdir)
    cfg = {"configurable": {"thread_id": "crash-job"}}
    final = graph.invoke(None, cfg)  # None = 从最后检查点续跑
    ledger = read_ledger(workdir)
    print(f"  续跑后 ledger: {ledger}")
    print(f"  续跑后 done_steps: {final['done_steps']}")
    check("恢复后完整跑完且每步恰好执行一次",
          ledger == STEPS and final["done_steps"] == STEPS)
    return workdir, db


def part_b_history(tmp):
    section("[B] 检查点历史：每个超步一个快照")
    workdir = os.path.join(tmp, "b")
    os.makedirs(workdir)
    db = os.path.join(workdir, "job.db")
    graph = build_graph(db, workdir)
    cfg = {"configurable": {"thread_id": "history-job"}}
    graph.invoke({"done_steps": [], "branch": "original"}, cfg)

    hist = list(graph.get_state_history(cfg))
    lengths = [len(h.values["done_steps"]) for h in hist]
    print(f"  快照数: {len(hist)}（新→旧），各快照已完成步骤数: {lengths}")
    check("快照数量覆盖全部超步且长度单调递减",
          len(hist) >= 7 and lengths == sorted(lengths, reverse=True))
    return graph, cfg, hist


def part_c_time_travel(graph, cfg, hist, tmp):
    section("[C] 时间旅行：从历史检查点分叉重放")
    target = next(h for h in hist
                  if h.values["done_steps"] == ["s1", "s2", "s3"])
    original_final_cfg = hist[0].config  # 分叉前的最终快照

    fork_cfg = graph.update_state(target.config, {"done_steps": ["fork"], "branch": "forked"})
    forked = graph.invoke(None, fork_cfg)
    print(f"  分叉重放结果: {forked['done_steps']} (branch={forked['branch']})")
    check("分叉分支包含 fork 标记并继续跑完 s4-s6",
          forked["done_steps"] == ["s1", "s2", "s3", "fork", "s4", "s5", "s6"]
          and forked["branch"] == "forked")

    original = graph.get_state(original_final_cfg)
    print(f"  旧分支最终快照: {original.values['done_steps']} "
          f"(branch={original.values['branch']})")
    check("旧分支最终快照仍可单独读取",
          original.values["done_steps"] == STEPS
          and original.values["branch"] == "original")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--crash-at", type=int, default=None)
    parser.add_argument("--workdir", default=None)
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    if args.worker:
        run_worker(args.workdir, args.db, args.crash_at)
        return 0

    print("=" * 64)
    print("[06] Checkpointer：断点恢复与时间旅行（纯离线）")
    print("=" * 64)

    with tempfile.TemporaryDirectory(prefix="checkpointer_") as tmp:
        part_a_crash_resume(tmp)
        graph, cfg, hist = part_b_history(tmp)
        part_c_time_travel(graph, cfg, hist, tmp)

    passed = sum(1 for _, ok in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{'=' * 64}")
    print(f"验收: {passed}/{total} 通过" + (" ✅" if passed == total else " ❌"))
    print("=" * 64)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
