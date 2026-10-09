"""tests/test_fuzz.py — 鲁棒性 fuzz 离线单测 (docs/aitest.md 项目 12)

覆盖: 生成器规模与分类 / 驱动层异常安全(未捕获=0) / 分类口径
(ok、empty_output、sut_error、timeout) / findings 留痕。全部离线,
用注入的 run_fn 模拟各种 SUT 行为, 不真调模型。
"""

import json
import os
import sys
import time

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, AITEST_DIR)

from collections import Counter  # noqa: E402

from testbench.suites import fuzz as F  # noqa: E402


# ---------- 生成器: 规模与分类 ----------

def test_generate_100_six_classes():
    cases = F.generate_cases(100)
    assert len(cases) == 100
    dist = Counter(c["class"] for c in cases)
    assert set(dist) == {"empty", "long", "unicode",
                         "tool_args", "nested_json", "control"}
    assert all(c["text"] for c in cases if c["class"] != "empty")
    assert "" in [c["text"] for c in cases if c["class"] == "empty"]
    ids = [c["id"] for c in cases]
    assert len(set(ids)) == 100


def test_generate_partial():
    cases = F.generate_cases(7)
    assert len(cases) == 7
    assert len(set(c["class"] for c in cases)) >= 5   # 轮转取类


# ---------- 驱动层: 异常安全 + 分类 ----------

def test_driver_never_raises(tmp_path):
    """SUT 各种炸法都不能让驱动抛出: 未捕获异常率恒为 0。"""
    def evil(text):
        if "长" in text:
            raise RuntimeError("boom")
        if text.startswith("{"):
            return {"final": ""}
        return {"final": "ok"}

    rep = F.run_fuzz(run_fn=evil, limit=100, verbose=False, timeout_s=0,
                     findings_path=tmp_path / "f.jsonl",
                     report_path=tmp_path / "r.json")
    assert rep["uncaught_exception_rate"] == 0
    assert rep["total"] == 100
    assert rep["outcomes"].get("sut_error", 0) > 0
    assert rep["outcomes"].get("empty_output", 0) > 0


def test_timeout_classified(tmp_path):
    def slow(_text):
        time.sleep(3)
        return {"final": "ok"}

    rep = F.run_fuzz(run_fn=slow, limit=1, verbose=False, timeout_s=1,
                     findings_path=tmp_path / "f.jsonl",
                     report_path=tmp_path / "r.json")
    assert rep["outcomes"] == {"timeout": 1}
    assert rep["uncaught_exception_rate"] == 0


# ---------- findings 留痕 ----------

def test_findings_written(tmp_path):
    path = tmp_path / "f.jsonl"
    _ = F.run_fuzz(
        run_fn=lambda t: (_ for _ in ()).throw(ValueError("bad")),
        limit=5, verbose=False, timeout_s=0,
        findings_path=path, report_path=tmp_path / "r.json")
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 5
    assert all(x["outcome"] == "sut_error" for x in lines)
    assert all("detail" in x and "input_head" in x for x in lines)


def test_all_ok_leaves_findings_empty(tmp_path):
    path = tmp_path / "f.jsonl"
    rep = F.run_fuzz(run_fn=lambda t: {"final": "fine"}, limit=10,
                     verbose=False, timeout_s=0,
                     findings_path=path, report_path=tmp_path / "r.json")
    assert rep["outcomes"] == {"ok": 10}
    assert path.read_text(encoding="utf-8") == ""
