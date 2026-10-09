"""tests/test_checkup.py — 四维体检离线单测 (docs/aitest.md 项目 21)"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, AITEST_DIR)

from final_checkup import checkup as C  # noqa: E402


def _report(rates=None, sec=True, perf=None, degraded=0):
    rates = rates if rates is not None else {"schema": 1.0, "semantic": 0.5,
                                             "factuality": 0.2, "judge": 0.9}
    perf = perf if perf is not None else {"p50_s": 10, "p95_s": 20,
                                          "tokens_est": 1000}
    return {"meta": {"sut": "mh", "level": "smoke", "model": "qwen3:4b",
                     "generated_at": "t", "elapsed_s": 1.0},
            "modules": [
                {"name": "eval", "status": "ok", "passed": None,
                 "metrics": {"rates": rates}, "elapsed_s": 1,
                 "detail": ""},
                {"name": "security", "status": "ok", "passed": sec,
                 "metrics": {"injection": 0.0}, "elapsed_s": 1, "detail": ""},
                {"name": "perf", "status": "ok", "passed": None,
                 "metrics": perf, "elapsed_s": 1, "detail": ""},
                {"name": "regression", "status": "ok", "passed": None,
                 "metrics": {"degraded": degraded, "improved": 0, "flat": 5},
                 "elapsed_s": 1, "detail": ""},
                {"name": "contract", "status": "ok", "passed": True,
                 "metrics": {}, "elapsed_s": 1, "detail": ""},
                {"name": "e2e", "status": "ok", "passed": None,
                 "metrics": {"success": 2, "total": 2}, "elapsed_s": 1,
                 "detail": ""},
                {"name": "trajectory", "status": "ok", "passed": True,
                 "metrics": {}, "elapsed_s": 0, "detail": ""},
            ]}


def test_all_green_grade_a():
    s = C.summarize(_report())
    assert s["grade"] == "A" and s["misses"] == 0


def test_each_dimension_can_fail():
    bad_rates = {"schema": 1.0, "semantic": 0.2, "judge": 0.9}
    assert C.summarize(_report(rates=bad_rates))["grade"] == "B"
    assert C.summarize(_report(sec=False))["grade"] == "B"
    assert C.summarize(_report(degraded=2))["grade"] == "B"
    assert C.summarize(_report(perf={"p50_s": 999, "p95_s": 999,
                                     "tokens_est": 999999}))["grade"] == "B"
    s = C.summarize(_report(rates=bad_rates, sec=False, degraded=1,
                            perf={"p50_s": 999, "p95_s": 999,
                                  "tokens_est": 9}))
    assert s["grade"] == "F" and s["misses"] == 4


def test_missing_perf_counts_miss():
    s = C.summarize(_report(perf={}))
    assert s["dims"]["性能"]["ok"] is False


def test_render_has_four_sections_and_grade():
    rep = _report()
    md = C.render_md(rep, C.summarize(rep), "quick")
    for sec in ("## 功能", "## 安全", "## 性能", "## 回归"):
        assert sec in md
    assert "## 总评级：A" in md
    assert "## 修复建议" in md


def test_recommendations_generated():
    s = C.summarize(_report(sec=False, degraded=3))
    assert len(s["recommendations"]) >= 2
    assert any("安全" in r for r in s["recommendations"])
    assert any("回归" in r for r in s["recommendations"])
