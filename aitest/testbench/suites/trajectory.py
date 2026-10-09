"""suites.trajectory — 轨迹评测: 步数效率/重复动作/死循环 (docs/aitest.md 项目 16)

给 Agent 的执行轨迹打 0-100 分(轨迹 = 工具调用序列):
  死循环检测(同动作连续>=3 或同 (动作,参数) 出现>=5) -> 直接 0 分
  步数效率 = min(1, 期望步数/实际步数) * 40
  无冗余   = (1 - 重复(动作,参数)占比) * 40
  收敛加分 = completed ? 20 : 0

    score_trajectory(steps, expected_steps, completed) -> report dict

接受两种步格式: mh 的 {"tool","args"} 或通用的 {"action","args"}。
"""

import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(os.path.dirname(HERE))
RESULTS_PATH = os.path.join(AITEST_DIR, "results", "trajectory.json")

sys.path.insert(0, AITEST_DIR)


def normalize(steps):
    """把轨迹步规整为 [(action, args_repr)]。"""
    out = []
    for s in steps or []:
        if isinstance(s, dict):
            action = s.get("tool") or s.get("action") or s.get("name") or "?"
            args = s.get("args") or s.get("arguments") or {}
            out.append((str(action), repr(sorted(args.items()))
                        if isinstance(args, dict) else repr(args)))
        else:
            out.append((str(s), ""))
    return out


def detect_loop(pairs, consecutive=3, repeat=5):
    """死循环: 同 (动作,参数) 连续 >=consecutive, 或总出现次数 >=repeat。"""
    n = len(pairs)
    run = 1
    for i in range(1, n):
        run = run + 1 if pairs[i] == pairs[i - 1] else 1
        if run >= consecutive:
            return True, f"同动作连续 {run} 次: {pairs[i][0]}"
    counts = Counter(pairs)
    top, cnt = counts.most_common(1)[0] if counts else (None, 0)
    if cnt >= repeat:
        return True, f"同 (动作,参数) 共出现 {cnt} 次: {top[0]}"
    return False, ""


def score_trajectory(steps, expected_steps=None, completed=True):
    """返回 {score, loop, loop_reason, efficiency, redundancy, metrics...}。"""
    pairs = normalize(steps)
    n = len(pairs)
    if n == 0:
        return {"score": 0, "loop": False, "loop_reason": "",
                "steps": 0, "efficiency": 0.0, "redundancy": 1.0,
                "completed": completed}

    is_loop, reason = detect_loop(pairs)
    if is_loop:
        return {"score": 0, "loop": True, "loop_reason": reason,
                "steps": n, "efficiency": 0.0, "redundancy": 1.0,
                "completed": completed}

    exp = expected_steps or n
    eff = min(1.0, exp / n)
    dup = n - len(set(pairs))                 # 重复(动作,参数)的多余次数
    redundancy = dup / n
    score = round(eff * 40 + (1 - redundancy) * 40 + (20 if completed else 0))
    return {"score": score, "loop": False, "loop_reason": "",
            "steps": n, "expected_steps": exp,
            "efficiency": round(eff, 3),
            "redundancy": round(redundancy, 3),
            "completed": completed}


# ============================================================
# 预置轨迹: 快 / 慢 / 死循环 (自证可区分)
# ============================================================

FAST_TRACE = [
    {"tool": "run_bash", "args": {"command": "printf 'ok' > a.txt"}},
    {"tool": "run_bash", "args": {"command": "cat a.txt"}},
]

SLOW_TRACE = [
    {"tool": "run_bash", "args": {"command": "ls"}},
    {"tool": "run_bash", "args": {"command": "ls"}},                     # 重复
    {"tool": "run_bash", "args": {"command": "pwd"}},                    # 绕路
    {"tool": "run_bash", "args": {"command": "printf 'ok' > a.txt"}},
    {"tool": "run_bash", "args": {"command": "cat a.txt"}},
    {"tool": "run_bash", "args": {"command": "ls"}},                     # 重复
]

LOOP_TRACE = [{"tool": "run_bash", "args": {"command": "ls"}}] * 30


def self_check():
    """快 > 慢, 死循环 = 0 且 loop=True。"""
    fast = score_trajectory(FAST_TRACE, expected_steps=2)
    slow = score_trajectory(SLOW_TRACE, expected_steps=2)
    loop = score_trajectory(LOOP_TRACE, expected_steps=2)
    ok = fast["score"] > slow["score"] and loop["score"] == 0 and loop["loop"]
    return {"fast": fast, "slow": slow, "loop": loop, "ok": ok}


def _cli():
    import argparse
    import json
    ap = argparse.ArgumentParser(description="轨迹评测")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    res = self_check()
    out = Path(RESULTS_PATH)
    out.parent.mkdir(exist_ok=True)
    report = {"generated_at": datetime.now().isoformat(timespec="seconds"),
              **res}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"fast={res['fast']['score']} slow={res['slow']['score']} "
          f"loop={res['loop']['score']}(loop={res['loop']['loop']}) -> {out}")
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    _cli()
