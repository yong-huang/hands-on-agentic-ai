"""checkup — 终极四维体检 (docs/aitest.md 项目 21, 🏁)

把 18 线 runner 的七模块结果组装成四维体检叙事:
    功能 = golden set 通过率(eval)
    安全 = 三维安全指标(security)
    性能 = 预算判定(perf, 默认预算)
    回归 = 双版 prompt 对比(regression 三态)
外加行为三件套(契约/e2e/轨迹)作为附录; 总评级 A-F + 修复建议清单,
输出 FINAL_REPORT.md。重复性口径: 成功率两跑差 <=1 个任务(15 线)。

    run_checkup(level="quick"|"full") -> report dict(并写 FINAL_REPORT.md)
    python3 -m final_checkup.checkup [--quick|--full] [--out FILE]
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
AITEST_DIR = HERE.parent
DEFAULT_OUT = AITEST_DIR / "FINAL_REPORT.md"

sys.path.insert(0, str(AITEST_DIR))


def _metrics(report, name):
    for m in report["modules"]:
        if m["name"] == name:
            return m
    return {}


def summarize(report):
    """七模块结果 -> 四维数字 + 评级 + 建议。纯函数, 单测直接打。"""
    ev = _metrics(report, "eval")
    se = _metrics(report, "security")
    pf = _metrics(report, "perf")
    rg = _metrics(report, "regression")

    dims = {}
    recs = []

    # 功能: 按本线 08 线口径 —— fact 维是趋势信号不做硬门槛,
    # 三项硬门槛: schema >=0.8 且 semantic >=0.5 且 judge >=0.8
    rates = (ev.get("metrics") or {}).get("rates") or {}
    present = {k: v for k, v in rates.items() if v is not None}

    def _ge(key, th):
        v = present.get(key)
        return v is None or v >= th

    functional_ok = bool(present) and _ge("schema", 0.8) and \
        _ge("semantic", 0.5) and _ge("judge", 0.8)
    dims["功能"] = {"value": rates, "ok": functional_ok,
                    "note": "schema≥0.8 且 semantic≥0.5 且 judge≥0.8"
                            "（fact 维按 08 线口径仅作趋势）"}
    if not functional_ok:
        recs.append("功能: 三维门槛未达标(见 report.html 评测区块), "
                    "fact 维仅看趋势不做硬判")

    # 安全
    se_ok = se.get("passed") is True
    dims["安全"] = {"value": se.get("metrics"), "ok": se_ok,
                    "note": "injection ASR/越狱拒绝率/fuzz 异常率 全达标"}
    if not se_ok:
        recs.append("安全: 三维未达标, 复核 13 线扫描器 detail 找出失守维度")

    # 性能
    from testbench.suites.perf_budget import evaluate_budget
    pf_metrics = pf.get("metrics") or {}
    _, failed = evaluate_budget(pf_metrics) if pf_metrics else ([], None)
    perf_ok = bool(pf_metrics) and not failed
    if not pf_metrics:
        perf_ok = False
    dims["性能"] = {"value": pf_metrics, "ok": perf_ok,
                    "note": "P50/P95/tokens 对照默认预算"}
    if not perf_ok:
        recs.append("性能: 超预算或未采集, 检查 17 线门禁与采样规模")

    # 回归
    rsum = rg.get("metrics") or {}
    degraded = rsum.get("degraded")
    reg_ok = degraded == 0 if degraded is not None else None
    dims["回归"] = {"value": rsum, "ok": reg_ok,
                    "note": "双版对比劣化数为 0"}
    if reg_ok is False:
        recs.append(f"回归: 存在 {degraded} 个劣化项, 按 09 线报告逐条复核")

    # 评级: A(0) B(1) C(2) D(3) F(4 及以上) —— 无 E 档
    misses = sum(1 for d in dims.values() if d["ok"] is False)
    grade = "ABCDF"[min(misses, 4)]
    if not recs:
        recs.append("无语义级问题; 按周计划继续扩充任务集与弹药库")

    return {"dims": dims, "grade": grade, "misses": misses,
            "recommendations": recs}


def render_md(report, summary, level):
    meta = report["meta"]
    lines = ["# FINAL_REPORT — harness/mh 四维体检", ""]
    lines.append(f"> 档位: {level} · SUT: {meta['sut']} · 模型: {meta.get('model')} "
                 f"· 生成于 {meta['generated_at']}（总耗时 {meta['elapsed_s']}s）")
    lines.append("")
    lines.append(f"## 总评级：{summary['grade']}"
                 f"（失守维度 {summary['misses']}/4）")
    lines.append("")
    lines.append("## 功能（golden set）")
    d = summary["dims"]["功能"]
    lines.append(f"- 各维通过率: {d['value']}（标准 {d['note']}）— "
                 f"{'✅' if d['ok'] else '❌'}")
    lines.append("")
    lines.append("## 安全（三维）")
    d = summary["dims"]["安全"]
    lines.append(f"- 指标: {json.dumps(d['value'], ensure_ascii=False)} — "
                 f"{'✅' if d['ok'] else '❌'}")
    lines.append("")
    lines.append("## 性能（预算）")
    d = summary["dims"]["性能"]
    lines.append(f"- 指标: {json.dumps(d['value'], ensure_ascii=False)} — "
                 f"{'✅' if d['ok'] else '❌'}")
    lines.append("")
    lines.append("## 回归（prompt diff）")
    d = summary["dims"]["回归"]
    lines.append(f"- 三态: {json.dumps(d['value'], ensure_ascii=False)} — "
                 f"{'✅' if d['ok'] else '❌' if d['ok'] is False else '⏭️ 未采集'}")
    lines.append("")
    lines.append("## 附录：行为三件套")
    for name in ("contract", "e2e", "trajectory"):
        m = _metrics(report, name)
        lines.append(f"- {name}: status={m.get('status')} "
                     f"passed={m.get('passed')} metrics="
                     f"{json.dumps(m.get('metrics'), ensure_ascii=False)}")
    lines.append("")
    lines.append("## 修复建议")
    for r in summary["recommendations"]:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("## 可复现性")
    lines.append("- 机制类结论确定性(离线自证); 端到端成功率复跑差值 ≤1 个任务"
                 "即视为可复现(15 线口径)")
    lines.append("")
    return "\n".join(lines)


def run_checkup(level="quick", model="qwen3:4b", out=None, verbose=True):
    from testbench import runner as R
    runner_level = "smoke" if level == "quick" else "full"
    report = R.run_all(level=runner_level, model=model, verbose=verbose)
    summary = summarize(report)
    md = render_md(report, summary, level)
    path = Path(out or DEFAULT_OUT)
    path.write_text(md, encoding="utf-8")
    if verbose:
        print(f"\n总评级: {summary['grade']} | 建议 {len(summary['recommendations'])} 条")
        print(f"报告 -> {path}")
    return {"report": report, "summary": summary, "path": str(path)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="终极四维体检")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--quick", action="store_true", help="smoke 档(约 7 分钟)")
    g.add_argument("--full", action="store_true", help="全量档(约 30 分钟)")
    ap.add_argument("--model", default="qwen3:4b")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    level = "full" if args.full else "quick"
    res = run_checkup(level=level, model=args.model, out=args.out)
    sys.exit(0 if res["summary"]["grade"] in "ABC" else 1)


if __name__ == "__main__":
    main()
