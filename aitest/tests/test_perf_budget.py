"""tests/test_perf_budget.py — 性能门禁离线单测 (docs/aitest.md 项目 17)"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, AITEST_DIR)

from testbench.suites import perf_budget as P  # noqa: E402


def test_percentile_small_sample():
    vals = [1, 2, 3, 4, 5]
    assert P._percentile(vals, 0.5) == 3
    assert P._percentile(vals, 0.95) == 5
    assert P._percentile([], 0.5) == 0.0


def test_budget_pass():
    graded, failed = P.evaluate_budget(
        {"p50_s": 3.0, "p95_s": 8.0, "tokens_est": 5000})
    assert failed == [] and all(d["pass"] for d in graded.values())


def test_budget_strict_fail():
    graded, failed = P.evaluate_budget(
        {"p50_s": 3.0, "p95_s": 8.0, "tokens_est": 5000},
        P.STRICT_BUDGET)
    assert failed == ["p50_s"]
    assert graded["p50_s"]["pass"] is False


def test_budget_missing_metric_fails_closed():
    graded, failed = P.evaluate_budget(
        {"p50_s": 1.0, "p95_s": None, "tokens_est": 10})
    assert "p95_s" in failed


def test_run_round_with_fake():
    tasks = [{"id": "t1", "task": "x"}, {"id": "t2", "task": "y"}]

    def fake(task):
        return {"elapsed_s": 2.5 if task == "x" else 3.5}, {"chars": 400}

    rr = P.run_round(tasks, run_fn=fake)
    assert rr["latencies"] == [2.5, 3.5]
    assert rr["tokens"] == [100, 100]
