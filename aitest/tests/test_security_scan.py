"""tests/test_security_scan.py — 安全门离线单测 (docs/aitest.md 项目 13)

纯函数门禁判定 + 扫描组装(注入假维度) + 终端渲染, 全部离线。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, AITEST_DIR)

from testbench import security_scan as S  # noqa: E402


def _dims(asr=0.0, refusal=0.8, uncaught=0.0):
    return {
        "injection": {"metric": "asr", "value": asr, "detail": {}, "rows": []},
        "jailbreak": {"metric": "refusal_rate", "value": refusal,
                      "detail": {}, "rows": []},
        "fuzz": {"metric": "uncaught_exception_rate", "value": uncaught,
                 "detail": {}, "rows": []},
    }


# ---------- 门禁判定: 三种阈值方向 ----------

def test_gate_all_pass():
    graded, failed = S.evaluate_gate(_dims(asr=0.1, refusal=0.6, uncaught=0.0))
    assert failed == []
    assert all(d["pass"] for d in graded.values())


def test_gate_asr_over_threshold_fails():
    graded, failed = S.evaluate_gate(_dims(asr=0.3))
    assert failed == ["injection"]
    assert graded["injection"]["pass"] is False


def test_gate_low_refusal_fails():
    _, failed = S.evaluate_gate(_dims(refusal=0.4))
    assert failed == ["jailbreak"]


def test_gate_custom_thresholds():
    # ASR 收紧到 0: 0.05 也应不达标
    _, failed = S.evaluate_gate(_dims(asr=0.05),
                                {"injection_asr": 0.0})
    assert failed == ["injection"]


def test_gate_missing_value_fails_closed():
    dims = _dims()
    dims["fuzz"]["value"] = None          # 采集失败 -> fail-closed
    _, failed = S.evaluate_gate(dims)
    assert "fuzz" in failed


# ---------- scan 组装: 注入假采集器, 不碰真机 ----------

def test_scan_with_fake_collectors(tmp_path):
    fake = {
        "injection": lambda **kw: {"metric": "asr", "value": 0.067,
                                   "detail": {}, "rows": []},
        "jailbreak": lambda **kw: {"metric": "refusal_rate", "value": 0.667,
                                   "detail": {}, "rows": []},
        "fuzz": lambda **kw: {"metric": "uncaught_exception_rate",
                              "value": 0.0, "detail": {}, "rows": []},
    }
    rep = S.scan(verbose=False, collectors=fake,
                 out_path=tmp_path / "s.json")
    assert rep["verdict"] == "pass"
    assert rep["failed_dimensions"] == []
    assert (tmp_path / "s.json").exists()


def test_scan_fail_verdict(tmp_path):
    fake = {
        "injection": lambda **kw: {"metric": "asr", "value": 0.5,
                                   "detail": {}, "rows": []},
        "jailbreak": lambda **kw: {"metric": "refusal_rate", "value": 0.9,
                                   "detail": {}, "rows": []},
        "fuzz": lambda **kw: {"metric": "uncaught_exception_rate",
                              "value": 0.0, "detail": {}, "rows": []},
    }
    rep = S.scan(verbose=False, collectors=fake,
                 out_path=tmp_path / "s.json")
    assert rep["verdict"] == "fail"
    assert rep["failed_dimensions"] == ["injection"]


def test_scan_collector_crash_is_contained(tmp_path):
    def boom(**kw):
        raise RuntimeError("collector down")

    fake = {"injection": boom,
            "jailbreak": lambda **kw: {"metric": "refusal_rate",
                                       "value": 0.9, "detail": {}, "rows": []},
            "fuzz": lambda **kw: {"metric": "uncaught_exception_rate",
                                  "value": 0.0, "detail": {}, "rows": []}}
    rep = S.scan(verbose=False, collectors=fake,
                 out_path=tmp_path / "s.json")
    # 采集崩溃 -> 该维 None -> fail-closed, 其余维度照常
    assert rep["verdict"] == "fail"
    assert "injection" in rep["failed_dimensions"]
    assert rep["dimensions"]["injection"]["detail"]["error"]


# ---------- 渲染 ----------

def test_render_contains_metrics():
    graded, _ = S.evaluate_gate(_dims())
    rep = {"sut": "mh", "verdict": "pass", "dimensions": graded}
    text = S.render(rep)
    assert "PASS" in text and "asr" in text and "refusal_rate" in text
