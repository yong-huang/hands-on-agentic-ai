"""test_prompt_regression — 回归套件离线测试 (docs/aitest.md 项目 9)

三态判定与报告渲染是纯逻辑; SUT/judge 全部打桩。
跑法: cd aitest && python3 -m pytest tests/test_prompt_regression.py -q
"""

from testbench.suites import prompt_regression as PR


def _row(sem_pass, judge, total=2):
    return {"id": "x", "sem_pass": sem_pass, "sem_total": total, "judge": judge}


def test_verdict_degraded_on_semantic_drop():
    v, _ = PR.verdict_for(_row(2, 5), _row(1, 5))
    assert v == "degraded"


def test_verdict_degraded_on_judge_drop_only():
    v, _ = PR.verdict_for(_row(2, 5), _row(2, 3))
    assert v == "degraded"


def test_verdict_improved_and_flat():
    assert PR.verdict_for(_row(1, 3), _row(2, 3))[0] == "improved"
    assert PR.verdict_for(_row(2, 4), _row(2, 4))[0] == "flat"


def test_verdict_none_judge_treated_as_zero():
    v, _ = PR.verdict_for(_row(2, 4), _row(2, None))
    assert v == "degraded"


def test_render_report_marks_degraded_bold():
    results = {
        "meta": {"generated_at": "t", "model": "m",
                 "base_prompt": "B" * 60, "cand_prompt": "C" * 60},
        "rows": [
            {"id": "a", "verdict": "degraded",
             "base": _row(2, 5), "cand": _row(1, 3)},
            {"id": "b", "verdict": "flat",
             "base": _row(2, 4), "cand": _row(2, 4)},
        ],
        "summary": {"degraded": 1, "improved": 0, "flat": 1},
    }
    md = PR.render_report(results)
    assert "| 0 | 1 | **1** |" in md and "`a`" in md


def test_degraded_prompt_constant_exists():
    assert "不用核实" in PR.PROMPT_DEGRADED and "严谨" in PR.BASE_PROMPT
