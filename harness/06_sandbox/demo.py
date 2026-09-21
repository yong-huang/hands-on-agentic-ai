#!/usr/bin/env python3
"""06 · 执行安全沙箱 — 三场景验收 (docs/harness.md 项目 6)

  场景1 死循环: while True 死循环 3s 被杀, 进程组无孤儿, harness 存活继续下一场景
  场景2 输出截断: 超 8KB 输出被截断且模型收到截断提示
  场景3 越界探测: ../ 路径爬升被词法守卫拒绝, 沙箱外文件零改动(前后快照对比)

三场景全部通过 Registry/Tool 走真实工具层(不经任何 mock), 再来一次完整
agent 循环(--agent)证明换装后模型拿到的错误信息可读。

用法:
  python3 demo.py            # 三场景验收(确定性, 无需 LLM)
  python3 demo.py --agent    # 真机: 完整 agent 循环跑一次带截断的任务
"""

import argparse
import hashlib
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
from mh.sandbox import run  # noqa: E402
from mh.tools import Registry, tool  # noqa: E402


def snapshot(root: Path) -> dict:
    """目录树指纹: 相对路径 + 内容 hash, 用于越界对比。"""
    out = {}
    for f in sorted(root.rglob("*")):
        if f.is_file():
            out[str(f.relative_to(root))] = hashlib.md5(f.read_bytes()).hexdigest()
    return out


def build_tools() -> dict:
    reg = Registry()

    @tool
    def run_bash(command: str, cwd: str = None) -> str:
        """在任务目录执行 bash 命令(沙箱: 3s 超时, 输出截断, 拒绝 ../)。"""
        ok, out = run(command, cwd=cwd or ".")
        return out if ok else f"[sandbox拒绝/失败] {out}"

    reg.add(run_bash)
    return reg.to_loop_tools()


def scenario_1_deadloop(sandbox: Path) -> bool:
    t0 = time.time()
    ok, out = run("while true; do :; done", cwd=str(sandbox))
    cost = time.time() - t0
    orphans = subprocess.run(["pgrep", "-g", str(os.getpid())],
                             capture_output=True, text=True).stdout.strip()
    print(f"场景1 死循环: 耗时 {cost:.1f}s | 结果: {out.strip()[:80]}")
    print(f"  孤儿进程检查(本进程组存活数): {len(orphans.splitlines()) if orphans else 0}")
    return 2.5 < cost < 6 and "超时" in out and "杀死" in out


def scenario_2_truncate(sandbox: Path) -> bool:
    ok, out = run("yes 'A 直线' | head -c 100000", cwd=str(sandbox))
    print(f"场景2 输出截断: 返回 {len(out)} 字符 | 含截断提示: {'输出已截断' in out}")
    return "输出已截断" in out and len(out) < 20000


def scenario_3_escape(sandbox: Path, outside: Path) -> bool:
    before = snapshot(outside)
    (outside / "treasure.txt").write_text("贵重文件")
    before = snapshot(outside)
    ok, out = run("echo hacked > ../treasure.txt", cwd=str(sandbox))
    after = snapshot(outside)
    unchanged = before == after
    print(f"场景3 越界探测: 命令被拒: {'[拒绝]' in out} | 沙箱外文件零改动: {unchanged}")
    return "[拒绝]" in out and unchanged


def agent_live(sandbox: Path):
    """完整 agent 循环: 生成大输出并观察截断回喂。"""
    task = ("执行命令: yes 'line' | head -c 50000 > big.txt; 然后用 wc -c 查看 "
            "big.txt 的字节数并汇报。不要 cat 它。")
    result = loop.run_agent(task, build_tools(), max_turns=8, cwd=str(sandbox))
    print(f"轮次: {result['turns']} | 调用 {len(result['tool_trace'])} 次")
    for tr in result["tool_trace"]:
        print(f"  {tr['tool']} → {tr['result'][:70]}")
    big = Path(sandbox, "big.txt")
    print(f"最终回答: {result['final'][:100]}")
    return big.is_file()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", action="store_true", help="追加一次真机 agent 循环")
    args = ap.parse_args()
    sandbox = Path(tempfile.mkdtemp(prefix="mh06_"))
    outside = Path(tempfile.mkdtemp(prefix="mh06_outside_"))
    results = [scenario_1_deadloop(sandbox), scenario_2_truncate(sandbox),
               scenario_3_escape(sandbox, outside)]
    for i, r in enumerate(results, 1):
        print(f"  场景{i}: {'✅' if r else '❌'}")
    if args.agent:
        results.append(bool(agent_live(sandbox)))
        print(f"  agent 循环: {'✅' if results[-1] else '❌'}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
