#!/usr/bin/env python3
"""16 · Harness 评测台 — 固定任务集回归 (docs/harness.md 项目 16, Agent QA)

两套配置、同一任务集、同一判分器(受控实验, 03 方法论的产品化):
  baseline(v0.1): 04 水平 —— 裸 loop + 无防护 run_bash(直接 subprocess)
  full(v1.0):     09 水平 —— 契约工具 + 沙箱执行 + 预算止损
任务集 10 个, 含不可批量串行依赖(09 教训)。
产出 markdown 对比表: 解决率/平均轮次/平均 est token, 回退指标标红 exit 1。

用法:
  python3 eval_run.py --profile baseline      # 只跑一个配置
  bash run.sh                                 # 全量对比(真机, 约 1 小时)
  MOCK=1 python3 eval_run.py --profile full   # 离线管道自检
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR / ".."))
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

from mh import llm as mh_llm  # noqa: E402
from mh import loop  # noqa: E402
from mh.budget import Budget, budget_chat_fn  # noqa: E402
from mh.sandbox import run as sandbox_run  # noqa: E402
from mh.tools import Registry, tool  # noqa: E402

SYSTEM = "你是严谨的运维助手, 通过工具完成任务。/no_think"

# ---- 10 任务: (指令, 判分) —— 多步串行, 判分只看文件系统 ----
def _t(cond_fn):
    return cond_fn

TASKS = [
    ("创建 a.txt(1 行)", lambda s: (s / "a.txt").is_file()),
    ("创建目录 x 并在其中写 b.txt(1 行)",
     lambda s: (s / "x/b.txt").is_file()),
    ("创建 c.txt 写 3 行", lambda s: (s / "c.txt").is_file()
     and len((s / "c.txt").read_text().strip().splitlines()) == 3),
    ("创建 d1/d2 两级目录, 深处写 e.txt(1 行)",
     lambda s: (s / "d1/d2/e.txt").is_file()),
    ("创建 list.txt 写 5 行", lambda s: (s / "list.txt").is_file()
     and len((s / "list.txt").read_text().strip().splitlines()) == 5),
    ("创建 m1 m2 m3 三个目录, 各含一个 ok.txt",
     lambda s: all((s / f"m{i}/ok.txt").is_file() for i in (1, 2, 3))),
    ("先写 src.txt(1 行), 再把内容复制到 dst.txt",
     lambda s: (s / "src.txt").is_file() and (s / "dst.txt").is_file()
     and (s / "src.txt").read_text() == (s / "dst.txt").read_text()),
    ("创建 cfg.ini, 内容为两行 key=value",
     lambda s: (s / "cfg.ini").is_file()
     and len([l for l in (s / "cfg.ini").read_text().splitlines()
              if "=" in l]) == 2),
    ("创建嵌套 p/q/r 目录, r 里写 deep.txt(1 行)",
     lambda s: (s / "p/q/r/deep.txt").is_file()),
    ("创建 4 个文件 w1..w4 各 1 行, 然后统计它们总行数存入 total.txt(应为 4)",
     lambda s: (s / "total.txt").is_file()
     and "4" in (s / "total.txt").read_text()),
]


def raw_bash(command: str, cwd: str = None) -> str:
    """baseline 工具: 直接 subprocess, 无守卫无截断(超时兜底 15s)。"""
    p = subprocess.run(["bash", "-c", command], cwd=cwd, capture_output=True,
                       text=True, timeout=15)
    return (p.stdout + p.stderr).strip() or "(无输出)"


def sandbox_bash(command: str, cwd: str = None) -> str:
    """full 工具: 沙箱执行。"""
    ok, out = sandbox_run(command, cwd=cwd or ".")
    return out if ok else f"[sandbox] {out}"


def build_tools(profile: str) -> dict:
    if profile == "baseline":
        fn = raw_bash
        schema = {"type": "function", "function": {
            "name": "run_bash", "description": "执行 bash 命令",
            "parameters": {"type": "object",
                           "properties": {"command": {"type": "string"}},
                           "required": ["command"]}}}
        return {"run_bash": {"desc": "执行 bash 命令", "schema": schema,
                             "fn": lambda command, cwd=None: fn(command, cwd=cwd)}}
    reg = Registry()

    @tool
    def run_bash(command: str, cwd: str = None) -> str:
        """在任务目录执行 bash 命令(沙箱: 3s 超时, 截断, 拒绝 ../)。"""
        ok, out = sandbox_run(command, cwd=cwd or ".")
        return out if ok else f"[sandbox] {out}"

    reg.add(run_bash)
    return reg.to_loop_tools()


def est_tokens(messages) -> int:
    import json as _j
    return sum(len(_j.dumps(m, ensure_ascii=False)) for m in messages) // 3


def run_profile(profile: str, tasks_n: int, results_dir: Path) -> dict:
    chat_base = None if os.environ.get("MOCK") == "1" else mh_llm.chat_with_retry
    if os.environ.get("MOCK") == "1":
        chat_base = None  # 走 _mock 分支
    rows = []
    for i in range(tasks_n):
        sandbox = Path(tempfile.mkdtemp(prefix=f"ev16_{profile}_{i}_"))
        budget = Budget(max_turns=10, max_tokens=6000)
        chat = (budget_chat_fn(chat_base, budget) if chat_base
                else budget_chat_fn(lambda m, tools=None, **k: _mock(i, m), budget))
        try:
            result = loop.run_agent(TASKS[i][0], build_tools(profile),
                                    max_turns=10, chat_fn=chat,
                                    cwd=str(sandbox), messages=[
                                        {"role": "system", "content": SYSTEM},
                                        {"role": "user", "content": TASKS[i][0]}])
            turns, final = result["turns"], result["final"]
        except Exception as e:  # 评测台不许被单任务炸死
            turns, final = budget.turns_used, f"[崩溃] {type(e).__name__}: {e}"
        ok = TASKS[i][1](sandbox)
        tok = budget.tokens_est or est_tokens(
            [{"c": final}]) + 800  # 兜底估算
        rows.append({"task": i, "ok": ok, "turns": turns, "tokens": tok})
        print(f"  [{profile}{i}] {'✅' if ok else '❌'} {turns} 轮 ~{tok} tok")
    (results_dir / f"{profile}.json").write_text(json.dumps(rows, indent=1))
    return {"profile": profile, "rows": rows,
            "pass": sum(r["ok"] for r in rows),
            "n": len(rows),
            "avg_turns": sum(r["turns"] for r in rows) / max(len(rows), 1),
            "avg_tokens": sum(r["tokens"] for r in rows) / max(len(rows), 1)}


def _mock(i, messages):
    """离线剧本: baseline 故意多走弯路, full 一步到位。"""
    n = sum(1 for m in messages if m.get("role") == "tool")
    if n >= (6 if i % 2 else 2):
        return {"role": "assistant", "content": "任务完成"}
    cmds = {0: "echo x > a.txt", 1: "mkdir -p x && echo x > x/b.txt",
            2: "printf '1\\n2\\n3' > c.txt", 3: "mkdir -p d1/d2 && echo x > d1/d2/e.txt",
            4: "printf '1\\n2\\n3\\n4\\n5' > list.txt",
            5: "mkdir -p m1 m2 m3 && for i in 1 2 3; do echo x > m$i/ok.txt; done",
            6: "echo data > src.txt && cp src.txt dst.txt",
            7: "printf 'a=1\\nb=2' > cfg.ini",
            8: "mkdir -p p/q/r && echo x > p/q/r/deep.txt",
            9: "for i in 1 2 3 4; do echo x > w$i.txt; done && (wc -l w*.txt | head -1) > total.txt"}
    return {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "run_bash", "arguments": {"command": cmds[i]}}}]}


def compare(res: dict) -> int:
    b, f = res.get("baseline"), res.get("full")
    if not (b and f):
        return 1
    lines = ["# 评测对比(自动生成)\n",
             "| 指标 | baseline v0.1 | full v1.0 | 变化 |",
             "|:--|:--:|:--:|:--:|"]
    regression = False
    for key, fmt, better_high in (("pass", "{}/{}", True),
                                  ("avg_turns", "{:.1f}", False),
                                  ("avg_tokens", "{:.0f}", False)):
        vb, vf = b[key], f[key]
        if key == "pass":
            cell_b, cell_f = fmt.format(vb, b["n"]), fmt.format(vf, f["n"])
            delta = f"{vf - vb:+d}"
            reg = vf < vb
        else:
            cell_b, cell_f = fmt.format(vb), fmt.format(vf)
            delta = f"{(vf - vb) / max(vb, 1) * 100:+.0f}%"
            reg = (vf > vb) if not better_high else (vf < vb)
        mark = " 🔴回退" if reg else ""
        regression |= reg
        lines.append(f"| {key} | {cell_b} | {cell_f} | {delta}{mark} |")
    out = EVAL_DIR / "COMPARE.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    return 1 if regression else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["baseline", "full"])
    ap.add_argument("--tasks", type=int, default=10)
    args = ap.parse_args()
    results_dir = EVAL_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    if os.environ.get("MOCK") == "1":
        sys.path.insert(0, str(EVAL_DIR))
    profiles = [args.profile] if args.profile else ["baseline", "full"]
    res = {p: run_profile(p, args.tasks, results_dir) for p in profiles}
    if len(res) == 2:
        sys.exit(compare(res))


if __name__ == "__main__":
    main()
