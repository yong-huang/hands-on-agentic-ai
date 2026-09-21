#!/usr/bin/env python3
"""03 · 固定模型变 Harness — 亲手复现"换 harness 比换模型影响大" (docs/harness.md 项目 3)

受控变量法: 固定 qwen3.8, 同一 10 任务集, 只变 harness 配置 ——
  配置 A(裸奔): 工具无 schema 校验(参数直传)、错误只回原始 stderr、输出不截断、
              JSON 解析失败直接判负(无修复机会)
  配置 B(契约治理): jsonschema 参数校验 + 友好错误回传(模型可自纠一轮) + 8KB 输出截断 +
              解析失败给一次结构修复机会
模型、任务、判分器完全相同。产出 markdown 对比表: 解决率 / 平均 token(轮次近似) / 平均轮次。

用法:
  python3 scaffold_ab_test.py                 # 真机跑 10 任务 × 2 配置
  python3 scaffold_ab_test.py --tasks 3       # 快速冒烟
  MOCK=1 python3 scaffold_ab_test.py --selftest
输出: results/trial_<配置><任务号>.json + results/COMPARE.md
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
RESULTS_DIR = LAB_DIR / "results"
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")
sys.path.insert(0, str(LAB_DIR / ".." / ".." / "interview"))
from llm import chat, mock_chat  # noqa: E402

NUM_PREDICT = 1200
MAX_TURNS = 5
TOOLS = {
    "write_file": {"desc": "写文本文件", "required": ["path", "content"]},
    "append_file": {"desc": "追加一行", "required": ["path", "line"]},
    "mkdir": {"desc": "建目录", "required": ["path"]},
    "count_lines": {"desc": "统计文件行数", "required": ["path"]},
}
PROTOCOL = (
    "你是运维助手。只能输出一个 JSON 对象表示下一步工具调用:\n"
    '{"tool": "工具名", "args": {...}}\n'
    f"可用工具: " + ", ".join(f'{k}({v["desc"]}, 必填参数 {v["required"]})'
                              for k, v in TOOLS.items()) + "\n"
    "路径一律相对路径。任务完成后输出 {\"tool\": \"done\"}。不要输出别的文字。/no_think")

# 10 个可自动判分的任务: (指令, 判分函数(沙箱路径)->bool)
TASKS = [
    ("创建 notes.txt, 内容为 2 行文字", lambda s: (s / "notes.txt").is_file() and len((s / "notes.txt").read_text().strip().splitlines()) == 2),
    ("创建目录 docs, 并在其中创建 a.md(1 行)", lambda s: (s / "docs/a.md").is_file() and len((s / "docs/a.md").read_text().strip().splitlines()) == 1),
    ("创建 data.csv, 共 3 行, 每行一个数字", lambda s: (s / "data.csv").is_file() and len((s / "data.csv").read_text().split()) == 3),
    ("先创建 log.txt(1 行), 再向它追加 1 行, 共 2 行", lambda s: (s / "log.txt").is_file() and len((s / "log.txt").read_text().strip().splitlines()) == 2),
    ("创建 3 个文件 f1.txt f2.txt f3.txt, 各 1 行", lambda s: all((s / f"f{i}.txt").is_file() for i in (1, 2, 3))),
    ("创建目录 src/mvc(两层), 其中写 main.py(1 行)", lambda s: (s / "src/mvc/main.py").is_file()),
    ("创建 todo.txt 写 4 行, 再追加第 5 行", lambda s: (s / "todo.txt").is_file() and len((s / "todo.txt").read_text().strip().splitlines()) == 5),
    ("创建 empty.txt(空文件, 0 行)和 one.txt(1 行)", lambda s: (s / "empty.txt").exists() and (s / "one.txt").is_file() and len((s / "one.txt").read_text().strip().splitlines()) == 1),
    ("创建目录 bin, 在其中建 tool.sh(内容 1 行)", lambda s: (s / "bin/tool.sh").is_file()),
    ("创建 report.md, 内容 2 行, 第二行是数字 42", lambda s: (s / "report.md").is_file() and (s / "report.md").read_text().strip().splitlines()[-1:] == ["42"]),
]


# ---------- 工具执行层: A/B 的全部差异都在这里 ----------

def exec_tool(cfg, name, args, sandbox):
    """执行一次工具调用, 返回 (回喂文本, 是否正常)。"""
    if name == "done":
        return "", True
    if name not in TOOLS:
        return f"错误: 未知工具 {name}", False
    if cfg == "B":  # 契约治理: schema 校验 + 友好错误
        missing = [k for k in TOOLS[name]["required"] if not isinstance(args, dict) or k not in args]
        if missing:
            return (f"参数校验失败: 工具 {name} 缺少必填参数 {missing}。"
                    f"请重新输出完整 JSON。"), False
    if not isinstance(args, dict):
        args = {}
    try:
        if name == "write_file":
            p = sandbox / args["path"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(args.get("content", "")) + "\n")
            return f"ok: 已写入 {args['path']}", True
        if name == "append_file":
            p = sandbox / args["path"]
            with p.open("a") as f:
                f.write(str(args.get("line", "")) + "\n")
            return f"ok: 已追加 {args['path']}", True
        if name == "mkdir":
            (sandbox / args["path"]).mkdir(parents=True, exist_ok=True)
            return f"ok: 已创建目录 {args['path']}", True
        if name == "count_lines":
            p = sandbox / args["path"]
            n = len(p.read_text().strip().splitlines()) if p.exists() else -1
            return f"{args['path']} 共 {n} 行", True
    except Exception as e:  # A: 原始异常直接甩给模型; B: 归纳成可读错误
        msg = repr(e) if cfg == "A" else f"执行失败: {type(e).__name__}: {e}。请修正参数重试。"
        return msg, False
    return "未知工具", False


def feed(cfg, text):
    return text if cfg == "A" else text[:8000]  # B: 8KB 截断


# ---------- runner ----------

def run_task(cfg, idx, llm) -> dict:
    rec_path = RESULTS_DIR / f"trial_{cfg}{idx}.json"
    if rec_path.exists():
        return json.loads(rec_path.read_text())
    sandbox = Path(tempfile.mkdtemp(prefix=f"mh03_{cfg}{idx}_"))
    messages = [{"role": "system", "content": PROTOCOL},
                {"role": "user", "content": f"任务: {TASKS[idx][0]}"}]
    turns, trace, repair_used = 0, [], {"parse": 0}
    for _ in range(MAX_TURNS):
        turns += 1
        try:
            reply = llm(messages, num_predict=NUM_PREDICT)
        except Exception as e:
            trace.append(f"llm 调用失败: {e}")
            break
        m = re.search(r"\{.*\}", reply, re.S)
        if not m:
            if cfg == "B" and repair_used["parse"] < 1:  # B 给一次结构修复机会
                repair_used["parse"] += 1
                messages += [{"role": "assistant", "content": reply},
                             {"role": "user", "content": "输出不是合法 JSON 对象。请只输出一个 JSON 对象。"}]
                continue
            trace.append(f"JSON 解析失败: {reply[:100]}")
            break
        try:
            call = json.loads(m.group())
        except json.JSONDecodeError:
            trace.append(f"JSON 解析失败: {m.group()[:100]}")
            break
        name, args = call.get("tool"), call.get("args", {})
        if name == "done":
            trace.append("done")
            break
        out, ok = exec_tool(cfg, name, args, sandbox)
        trace.append(f"{name}({args}) -> {'ok' if ok else feed(cfg, out)[:60]}")
        if not ok or cfg == "A":
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"工具结果: {feed(cfg, out)}\n请继续。"}]
        else:
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": "工具执行成功, 请继续。"}]
    success = TASKS[idx][1](sandbox)
    rec = {"cfg": cfg, "task": idx, "success": success, "turns": turns,
           "trace": trace, "parse_repair": repair_used["parse"]}
    rec_path.parent.mkdir(exist_ok=True)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    shutil.rmtree(sandbox, ignore_errors=True)
    return rec


def write_compare(recs) -> Path:
    rows, ok = {}, {"A": 0, "B": 0}
    for cfg in "AB":
        cs = [r for r in recs if r["cfg"] == cfg]
        ok[cfg] = sum(r["success"] for r in cs)
        rows[cfg] = (len(cs), ok[cfg],
                     sum(r["turns"] for r in cs) / max(len(cs), 1))
    md = ["# 固定模型变 Harness 对照 (自动生成)\n",
          "| 配置 | 任务数 | 解决率 | 平均轮次 |", "|:--|:--:|:--:|:--:|",
          f"| A 裸奔 | {rows['A'][0]} | {rows['A'][1]}/{rows['A'][0]} | {rows['A'][2]:.1f} |",
          f"| B 契约治理 | {rows['B'][0]} | {rows['B'][1]}/{rows['B'][0]} | {rows['B'][2]:.1f} |",
          "", "> 同一模型(qwen3.8)、同一任务集、同一判分器, 只变 harness 配置。",
          f"> 配置 B 修复机会使用次数: {sum(r['parse_repair'] for r in recs if r['cfg'] == 'B')} 次\n"]
    out = RESULTS_DIR / "COMPARE.md"
    out.write_text("\n".join(md))
    return out


def make_mock():
    seq = iter([
        '{"tool": "write_file", "args": {"path": "x.txt", "content": "a"}}',
        '{"tool": "done"}',
        '{bad json',  # 演示 B 的结构修复
        '{"tool": "done"}',
    ])
    def _mock(messages, temperature=0.0, num_predict=500, timeout=180):
        user = messages[-1]["content"]
        try:
            return next(seq)
        except StopIteration:
            return '{"tool": "done"}'
    return _mock


def selftest():
    global RESULTS_DIR
    import tempfile
    RESULTS_DIR = Path(tempfile.mkdtemp(prefix="mh03_selftest_"))
    r = run_task("B", 0, make_mock())
    assert isinstance(r["success"], bool) and r["turns"] >= 1
    print("selftest OK: runner/判分/记录管道可用 (mock 数据写临时目录)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tasks", type=int, default=10)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    llm = make_mock() if os.environ.get("MOCK") == "1" else llm_with_retry
    recs = []
    for cfg in "AB":
        for i in range(args.tasks):
            r = run_task(cfg, i, llm)
            recs.append(r)
            print(f"[{cfg}{i}] {r['turns']} 轮 → {'✅' if r['success'] else '❌ ' + (r['trace'][-1][:40] if r['trace'] else '')}")
    report = write_compare(recs)
    print(f"\n对比表 → {report}")


def llm_with_retry(messages, num_predict=NUM_PREDICT, attempts=3):
    for i in range(attempts):
        try:
            return chat(messages, num_predict=num_predict, timeout=180 * (i + 1))
        except (TimeoutError, OSError) as e:
            if i == attempts - 1:
                raise
            print(f"  [retry {i + 1}] llm 失败({e}), 重试…")


if __name__ == "__main__":
    main()
