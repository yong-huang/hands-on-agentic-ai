"""tests/test_runner.py — 统一 runner 离线单测 (docs/aitest.md 项目 18)

schema 契约 + 崩溃隔离 + 七模块齐全, 全部离线(注入假模块)。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, AITEST_DIR)

import jsonschema  # noqa: E402
import pytest  # noqa: E402

from testbench import schema  # noqa: E402
from testbench import runner as R  # noqa: E402


def _ok(_ctx):
    return {"status": "ok", "passed": True, "metrics": {"x": 1},
            "detail": "fine"}


def _boom(_ctx):
    raise RuntimeError("模块崩溃")


def _skip(_ctx):
    return {"status": "skipped", "passed": None, "metrics": {},
            "detail": "离线跳过"}


def test_schema_accepts_good_report():
    rep = R.run_all(level="smoke", modules=[(f"m{i}", _ok) for i in range(7)],
                    verbose=False)
    assert schema.validate(rep) is True


def test_schema_rejects_bad_status():
    rep = R.run_all(level="smoke", modules=[("m", _ok)] * 7, verbose=False)
    rep["modules"][0]["status"] = "weird"
    with pytest.raises(jsonschema.ValidationError):
        schema.validate(rep)


def test_crash_contained_and_others_collected():
    mods = [("ok1", _ok), ("bad", _boom)] + \
        [(f"ok{i}", _ok) for i in range(2, 7)]
    rep = R.run_all(level="smoke", modules=mods, verbose=False)
    by_name = {m["name"]: m for m in rep["modules"]}
    assert by_name["bad"]["status"] == "error"
    assert "RuntimeError" in by_name["bad"]["detail"]
    assert all(by_name[f"ok{i}"]["status"] == "ok" for i in range(7)
               if f"ok{i}" in by_name)
    schema.validate(rep)          # 崩溃后整体仍过 schema


def test_skipped_shape():
    rep = R.run_all(level="smoke", modules=[("s", _skip)] * 7,
                    verbose=False)
    assert all(m["status"] == "skipped" and m["passed"] is None
               for m in rep["modules"])


def test_seven_modules_registered():
    names = [n for n, _ in R.MODULES]
    assert names == ["eval", "regression", "security", "contract",
                     "e2e", "trajectory", "perf"]
