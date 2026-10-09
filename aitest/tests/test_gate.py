"""tests/test_gate.py — CI 门禁分级离线单测 (docs/aitest.md 项目 20)"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, AITEST_DIR)

from testbench import gate as G  # noqa: E402


# ---------- 路由规则 ----------

def test_route_smoke_for_data_changes():
    assert G.route(["aitest/datasets/tasks.yaml"]) == "smoke"
    assert G.route(["aitest/payloads/injection.yaml"]) == "smoke"
    assert G.route(["aitest/datasets/a.yaml",
                    "aitest/payloads/b.yaml"]) == "smoke"


def test_route_full_for_sut_and_unknown():
    assert G.route(["harness/mh/loop.py"]) == "full"
    assert G.route(["aitest/testbench/runner.py"]) == "full"
    assert G.route(["README.md"]) == "full"      # 未知 fail-safe
    assert G.route([]) == "full"


def test_route_mixed_prefers_full():
    assert G.route(["aitest/datasets/x.yaml", "harness/mh/llm.py"]) == "full"


# ---------- 退出码判定 ----------

def test_decide_pass_and_fail():
    ok = {"modules": [{"name": "security", "status": "ok", "passed": True},
                      {"name": "e2e", "status": "ok", "passed": None}]}
    assert G.decide(ok)[0] == 0
    bad = {"modules": [{"name": "security", "status": "ok", "passed": False}]}
    code, reasons = G.decide(bad)
    assert code == 1 and "security" in reasons[0]
    crash = {"modules": [{"name": "perf", "status": "error", "passed": False}]}
    assert G.decide(crash)[0] == 1


# ---------- 自检函数 ----------

def test_selftest_green():
    assert G.selftest(verbose=False) is True
