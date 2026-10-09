"""suites.prompt_regression — 提示词回归套件 (docs/aitest.md 项目 9)

promptfoo 思想的自研最小实现: 同一 golden set, 两版 system prompt 各跑一遍
SUT, 逐用例对比断言结果, 输出 改善/持平/劣化 三栏 markdown 报告。

    python3 -m testbench.suites.prompt_regression --base <sys> --candidate <sys>

"劣化变体"内置: PROMPT_DEGRADED(把 rubric 式的严谨人设换成含糊人设),
用于自证回归套件能抓到真实劣化 —— 套件先证明自己能报出劣化, 才有资格
报"没有劣化"。

对比口径(每条用例):
  semantic 通过数(0.60 阈值) 与 judge 分数(>=4) 两个信号, candidate 低于
  base 即记一次劣化; 报告附逐用例明细与两个信号的总体变化。
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, AITEST_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(AITEST_DIR), "qa"))

from testbench import suts                                       # noqa: E402
from testbench.datasets import load as load_dataset              # noqa: E402
from testbench.judges import rubric                              # noqa: E402

BASE_PROMPT = ("你是严谨的运维助手, 通过工具完成用户任务。回答前先确认事实, "
               "不确定就说明不确定。/no_think")
PROMPT_DEGRADED = ("你是个热情的助手, 想到什么说什么就行, 不用核实, 越快回答越好。/no_think")

THRESHOLD = 0.60
JUDGE_PASS = 4


def _judge_chat():
    import functools
    import llm as qa_llm
    return functools.partial(qa_llm.chat, num_predict=800, temperature=0)


def _score_case(case, system, chat_fn, model):
    """单条用例在一版 prompt 下的两个信号。"""
    r = suts.run_sut(case["query"], system=system, model=model)
    answer = str(r["final"])
    sims = []
    from testbench.asserts import semantic
    for p in case.get("expected_points") or []:
        sims.append(semantic.check(answer, p, THRESHOLD).ok)
    jr = rubric.score_answer(case["query"], answer, chat_fn)
    sem_pass = sum(1 for s in sims if s)
    return {"id": case["id"], "answer_preview": answer[:50],
            "sem_pass": sem_pass, "sem_total": len(sims),
            "judge": jr.score,
            "pass": bool(case.get("expected_points")) and
                    sem_pass == len(sims) and
                    (jr.score is not None and jr.score >= JUDGE_PASS)}


def verdict_for(base_row, cand_row):
    """对比口径: semantic 通过数或 judge 分任一下降即 degraded, 任一上升即 improved。"""
    delta = (cand_row["sem_pass"] - base_row["sem_pass"],
             (cand_row["judge"] or 0) - (base_row["judge"] or 0))
    if delta[0] > 0 or delta[1] > 0:
        return "improved", delta
    if delta[0] < 0 or delta[1] < 0:
        return "degraded", delta
    return "flat", delta


def run_regression(base_prompt=BASE_PROMPT, cand_prompt=PROMPT_DEGRADED,
                   dataset="golden_v1", model="qwen3:4b", limit=None,
                   verbose=True):
    """跑两版对比, 返回 results dict 并落盘 aitest/results/regression.json。"""
    cases = load_dataset(dataset)["cases"]
    if limit:
        cases = cases[:limit]
    chat_fn = _judge_chat()
    rows = []
    for i, case in enumerate(cases, 1):
        b = _score_case(case, base_prompt, chat_fn, model)
        c = _score_case(case, cand_prompt, chat_fn, model)
        verdict, delta = verdict_for(b, c)
        rows.append({"id": case["id"], "base": b, "cand": c,
                     "delta": delta, "verdict": verdict})
        if verbose:
            mark = {"improved": "📈", "degraded": "📉", "flat": "➖"}[verdict]
            print(f"  [{i:02d}/{len(cases)}] {case['id']} {mark} "
                  f"sem {b['sem_pass']}->{c['sem_pass']} "
                  f"judge {b['judge']}->{c['judge']}")

    degraded = [r for r in rows if r["verdict"] == "degraded"]
    improved = [r for r in rows if r["verdict"] == "improved"]
    results = {
        "meta": {"dataset": dataset, "model": model,
                 "base_prompt": base_prompt[:50], "cand_prompt": cand_prompt[:50],
                 "generated_at": datetime.now().isoformat(timespec="seconds")},
        "rows": rows,
        "summary": {"degraded": len(degraded), "improved": len(improved),
                    "flat": len(rows) - len(degraded) - len(improved)},
    }
    out = Path(AITEST_DIR) / "results" / "regression.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n回归结论: 改善 {len(improved)} · 持平 "
          f"{len(rows) - len(degraded) - len(improved)} · 劣化 {len(degraded)}"
          f" -> {out}")
    return results


def render_report(results):
    """markdown 三栏报告(改善/持平/劣化)。"""
    s = results["summary"]
    lines = [
        "# 提示词回归报告", "",
        f"- 生成: {results['meta']['generated_at']} · "
        f"模型 {results['meta']['model']}",
        f"- base: {results['meta']['base_prompt']}...",
        f"- cand: {results['meta']['cand_prompt']}...",
        "",
        f"| 改善 | 持平 | 劣化 |",
        f"|:--:|:--:|:--:|",
        f"| {s['improved']} | {s['flat']} | **{s['degraded']}** |",
        "",
        "## 劣化明细", "",
    ]
    for r in results["rows"]:
        if r["verdict"] != "degraded":
            continue
        lines.append(f"- `{r['id']}`: 期望要点通过 "
                     f"{r['base']['sem_pass']}/{r['base']['sem_total']} → "
                     f"{r['cand']['sem_pass']}/{r['cand']['sem_total']} · "
                     f"judge {r['base']['judge']} → {r['cand']['judge']}")
    if not any(r["verdict"] == "degraded" for r in results["rows"]):
        lines.append("- (无劣化项)")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE_PROMPT)
    ap.add_argument("--candidate", default=PROMPT_DEGRADED)
    ap.add_argument("--dataset", default="golden_v1")
    ap.add_argument("--model", default="qwen3:4b")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    results = run_regression(args.base, args.candidate, args.dataset,
                             args.model, args.limit)
    report = Path(AITEST_DIR) / "results" / "regression_report.md"
    report.write_text(render_report(results), encoding="utf-8")
    print(f"报告 -> {report}")
    return 0 if results["summary"]["degraded"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
