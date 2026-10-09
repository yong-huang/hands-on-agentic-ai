"""tests/test_report.py — 报告生成器离线单测 (docs/aitest.md 项目 19)"""

import json
import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, AITEST_DIR)

import pytest  # noqa: E402

from testbench import report as RP  # noqa: E402


def _fake_report():
    return {
        "meta": {"sut": "mh", "level": "smoke", "model": "qwen3:4b",
                 "generated_at": "2026-10-09T17:00:00", "elapsed_s": 1.5,
                 "modules_n": 7},
        "modules": [
            {"name": "eval", "status": "ok", "passed": None,
             "metrics": {"overall_pass_rate": 0.667,
                         "rates": {"semantic": 0.5}},
             "elapsed_s": 1.0, "detail": "2 条"},
            {"name": "regression", "status": "ok", "passed": None,
             "metrics": {"improved": 1, "flat": 1, "degraded": 0},
             "elapsed_s": 1.0, "detail": "2 条"},
            {"name": "security", "status": "ok", "passed": True,
             "metrics": {"injection": 0.0, "jailbreak": 0.667,
                         "fuzz": 0.0},
             "elapsed_s": 1.0, "detail": "failed=无"},
            {"name": "contract", "status": "ok", "passed": True,
             "metrics": {"normal": 0}, "elapsed_s": 1.0, "detail": "1 变体"},
            {"name": "e2e", "status": "ok", "passed": None,
             "metrics": {"success": 2, "total": 2, "rate": 1.0},
             "elapsed_s": 1.0, "detail": "2 任务"},
            {"name": "trajectory", "status": "ok", "passed": True,
             "metrics": {"fast": 100, "slow": 60, "loop": 0},
             "elapsed_s": 0.0, "detail": "自证"},
            {"name": "perf", "status": "ok", "passed": None,
             "metrics": {"p50_s": 12.3, "p95_s": 14.0,
                         "tokens_est": 4000},
             "elapsed_s": 1.0, "detail": "1×1"},
        ],
    }


def test_five_sections_present(tmp_path):
    html = RP.build_html(_fake_report())
    for sid in ("overview", "eval", "security", "behavior", "performance"):
        assert f"id='{sid}'" in html
    assert "评测" in html and "安全" in html and "性能" in html


def test_numbers_embedded_and_verified():
    rep = _fake_report()
    html = RP.build_html(rep)
    checks = RP.verify(html, rep, samples=3)
    assert len(checks) == 3
    assert all(ok for _, ok in checks)
    # 抽查值确实在 HTML 中
    assert "0.667" in html and "100" in html


def test_verify_detects_tamper():
    rep = _fake_report()
    html = RP.build_html(rep)
    rep["modules"][0]["metrics"]["overall_pass_rate"] = 0.999  # 数字被改
    checks = RP.verify(html, rep, samples=3)
    assert any(not ok for _, ok in checks)


def test_passed_false_highlighted():
    rep = _fake_report()
    rep["modules"][2]["passed"] = False
    rep["modules"][2]["status"] = "error"
    rep["modules"][2]["detail"] = "RuntimeError: boom"
    html = RP.build_html(rep)
    assert "class='bad'>error" in html
    assert "RuntimeError" in html


def test_cli_generates(tmp_path):
    rep = _fake_report()
    inp = tmp_path / "r.json"
    outp = tmp_path / "report.html"
    inp.write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        RP.main([str(inp), "--out", str(outp), "--verify"])
    assert e.value.code == 0          # 抽查全过才退 0
    assert outp.exists()
