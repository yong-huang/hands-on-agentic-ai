#!/usr/bin/env python3
"""01 · 无 Harness 基线 — 裸 LLM 的多步任务失败实录 (docs/harness.md 项目 1)

实验设计:
  A 组(裸 LLM): 模型只能用 bash 代码块「表达」要执行的操作, runner 不执行 —— 没有执行层,
               观察工具幻觉/虚假成功/死循环/上下文漂移等失败模式, 文件系统是判分铁证。
  B 组(对照组): 同样的对话, runner 真的 exec 提取出的 bash(cwd 锁沙箱, 3s 超时)并回喂输出,
               仅 15 行执行逻辑 —— 这就是"最小 harness"能带来的差距。

用法:
  python no_harness_baseline.py                    # 真机跑 A/B 各 5 次 (LLM_MODEL 可切换)
  python no_harness_baseline.py --trials 10       # 验收口径: 各 10 次
  python no_harness_baseline.py --groups B        # 只跑对照组
  MOCK=1 python no_harness_baseline.py --selftest # 离线自检
输出:
  results/trial_<组>_<n>.json   每次试验完整对话与判分
  results/FAILURES.md           失败模式归类 + 证据摘录
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
RESULTS_DIR = LAB_DIR / "results"   # selftest 会临时改指向 tmp, mock 数据永不污染真机结果
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")        # 本地 Ollama 不走系统代理
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")
sys.path.insert(0, str(LAB_DIR / ".." / ".." / "qa"))
from llm import MODEL, chat, mock_chat  # noqa: E402  复用 qa 线共用客户端

TASK = ("请在沙箱目录完成以下任务, 全部做完后明确说\"任务完成\":\n"
        "1) 创建 alpha.txt, 内容为 3 行文字;\n"
        "2) 创建 beta.txt, 内容为 2 行文字;\n"
        "3) 创建 gamma.txt, 内容为 1 行文字;\n"
        "4) 统计三个文件的总行数并告诉我。")
EXPECTED = {"alpha.txt": 3, "beta.txt": 2, "gamma.txt": 1}
SYSTEM = ("你是运维助手。你的当前工作目录就是任务目录, 一律用相对路径, 不要 cd 到别处。"
          "你要执行的每条命令放在```bash 代码块里, 每轮可多条。"
          "任务全部完成时回复必须包含\"任务完成\"。/no_think")  # qwen3 关思考软开关, 防止小模型配额被思考耗尽
NUM_PREDICT = 1200  # 留足正文空间; 思考关闭后依然安全
DONE_RE = re.compile(r"任务完成")
BASH_RE = re.compile(r"```bash\n(.*?)```", re.S)
MAX_TURNS = 8


# ---------- 执行与判分 ----------

def run_bash(cmd: str, cwd: Path, timeout: int = 3) -> str:
    """对照组唯一 harness 能力: 真执行。cwd 锁沙箱, 超时杀死, 输出截断。"""
    try:
        p = subprocess.run(["bash", "-c", cmd], cwd=cwd, capture_output=True,
                           text=True, timeout=timeout)
        out = (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        out = f"[超时 {timeout}s 被杀死]"
    return out[:2000] + ("…[截断]" if len(out) > 2000 else "")


def grade(sandbox: Path) -> bool:
    """铁证判分: 三个文件都存在且行数精确匹配。"""
    for name, want in EXPECTED.items():
        f = sandbox / name
        if not f.is_file() or len(f.read_text().strip().splitlines()) != want:
            return False
    return True


# ---------- 失败模式归类 (纯函数, 可单测) ----------

def classify(turns, executed_ok: bool) -> list:
    """turns: [(role, text)]; 返回命中的失败模式标签。"""
    tags = []
    final = next((t for r, t in reversed(turns) if r == "assistant"), "")
    if DONE_RE.search(final) and not executed_ok:
        tags.append("虚假成功: 宣称任务完成, 但文件系统零变化(执行层缺失)")
    cmds = [c for _, t in turns for c in BASH_RE.findall(t)]
    norm = [re.sub(r"\s+", " ", c.strip()) for c in cmds]
    if any(norm.count(c) >= 3 for c in set(norm)):
        tags.append("死循环: 同一命令重复输出 ≥3 次仍不收敛")
    if cmds and not any("gamma" in c for c in cmds):
        tags.append("上下文漂移: 多轮后遗漏了任务第 3 步(gamma.txt)")
    return tags


# ---------- 两组 runner ----------

def llm_with_retry(messages, num_predict=NUM_PREDICT, attempts=3):
    """真机调用带重试与弹性超时——重试预算本身就是最小 harness 的第一课。"""
    for i in range(attempts):
        try:
            return chat(messages, num_predict=num_predict, timeout=180 * (i + 1))
        except (TimeoutError, OSError) as e:
            if i == attempts - 1:
                raise
            print(f"  [retry {i + 1}/{attempts - 1}] llm 调用失败({e}), 换更长超时重试…")


def run_trial(group: str, n: int, llm, keep: bool) -> dict:
    rec_path = RESULTS_DIR / f"trial_{group}{n}.json"
    if rec_path.exists():  # 断点续跑: 已完成的试验不重跑
        return json.loads(rec_path.read_text())
    sandbox = Path(f"/tmp/mh01/{group}{n}")
    shutil.rmtree(sandbox, ignore_errors=True)
    sandbox.mkdir(parents=True)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": TASK}]
    turns, all_cmds = [], []
    for _ in range(MAX_TURNS):
        reply = llm(messages, num_predict=NUM_PREDICT)
        turns.append(("assistant", reply))
        blocks = BASH_RE.findall(reply)
        all_cmds += blocks
        if not blocks:
            if DONE_RE.search(reply):
                break
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": "请用 bash 代码块给出下一步。"})
            continue
        if group == "B":  # 对照组唯一差异: 命令真的被执行, 输出回喂
            out = "\n".join(f"$ {c.strip()}\n{run_bash(c, sandbox)}"
                            for c in blocks)
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user",
                             "content": f"命令执行结果:\n{out}\n请继续。"})
        else:  # 裸 LLM 组: 命令只是被"看到", 从未执行
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": "继续。"})
        if DONE_RE.search(reply):  # 先执行再收尾, 避免"命令+完成"同轮时漏执行
            break
    ok = grade(sandbox)
    rec = {"group": group, "trial": n, "success": ok,
           "failures": [] if ok else classify(turns, executed_ok=group == "B"),
           "turns_used": sum(1 for role, _ in turns if role == "assistant"),
           "cmd_count": len(all_cmds), "sandbox": str(sandbox), "turns": turns}
    rec_path.parent.mkdir(exist_ok=True)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    if not keep:
        shutil.rmtree(sandbox, ignore_errors=True)
    return rec


# ---------- 汇总报告 ----------

def write_failures(recs) -> Path:
    lines = ["# 失败模式实录 (自动生成)\n"]
    for tag in sorted({t for r in recs for t in r["failures"]}):
        lines.append(f"## {tag}\n")
        for r in recs:
            if tag in r["failures"]:
                excerpt = next((t for _, t in reversed(r["turns"])
                                if DONE_RE.search(t)), r["turns"][-1][1])
                lines.append(f"- 证据 `trial_{r['group']}{r['trial']}`: "
                             f"「{excerpt.strip()[:120]}…」\n")
    stat = [f"| {g} | {sum(1 for r in recs if r['group'] == g and r['success'])}"
            f"/{sum(1 for r in recs if r['group'] == g)} |"
            for g in sorted({r['group'] for r in recs})]
    lines[:0] = ["| 组 | 成功 |", "|:--|:--|", *stat, "",
                 f"> 生成时间 {datetime.now():%Y-%m-%d %H:%M}\n"]
    report = RESULTS_DIR / "FAILURES.md"
    report.parent.mkdir(exist_ok=True)
    report.write_text("\n".join(lines))
    return report


def make_mock():
    """MOCK 剧本: A 组假完成(演示虚假成功), B 组正确脚本(演示对照组成功)。"""
    good = ("```bash\ncd $PWD\nprintf 'a\\nb\\nc' > alpha.txt\n"
            "printf 'a\\nb' > beta.txt\nprintf 'a' > gamma.txt\n```\n"
            "```bash\nwc -l alpha.txt beta.txt gamma.txt\n```\n任务完成")
    return mock_chat([
        ("任务", "```bash\nmkdir -p out && echo hi > out/x.txt\n```\n我先建个目录。"),
        ("继续", good),
    ])


def selftest() -> None:
    global RESULTS_DIR
    import tempfile
    RESULTS_DIR = Path(tempfile.mkdtemp(prefix="mh01_selftest_"))  # mock 数据不落 results/
    for g in "AB":
        r = run_trial(g, 0, make_mock(), keep=False)
        assert isinstance(r["success"], bool), "判分必须返回布尔"
        assert r["turns"], "必须有对话记录"
    (LAB_DIR / "results").mkdir(exist_ok=True)
    print("selftest OK: A/B 两组 runner、判分、记录管道全部可用")
    print(f"当前真机模型: LLM_MODEL={os.environ.get('LLM_MODEL', MODEL)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--trials", type=int, default=5, help="每组试验次数")
    ap.add_argument("--groups", default="AB", help="要跑的组, 如 AB 或 B")
    ap.add_argument("--keep", action="store_true", help="保留沙箱目录供人工检查")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    llm = make_mock() if os.environ.get("MOCK") == "1" else llm_with_retry
    recs = [run_trial(g, n, llm, args.keep)
            for g in args.groups for n in range(args.trials)]
    for r in recs:
        mark = "✅" if r["success"] else f"❌ {r['failures'][0][:18] if r['failures'] else '判分未过'}"
        print(f"[{r['group']}{r['trial']}] {r['turns_used']} 轮 "
              f"{r['cmd_count']} 条命令 → {mark}")
    report = write_failures(recs)
    a_ok = sum(r["success"] for r in recs if r["group"] == "A")
    b_ok = sum(r["success"] for r in recs if r["group"] == "B")
    print(f"\nA 组(裸 LLM)成功 {a_ok}, B 组(最小 harness)成功 {b_ok}")
    print(f"失败实录 → {report}")


if __name__ == "__main__":
    main()
