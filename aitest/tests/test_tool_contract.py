"""tests/test_tool_contract.py — 工具契约离线单测 (docs/aitest.md 项目 14)

用合成调用日志验证两类断言与变体构造, 不真调模型。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, AITEST_DIR)

import pytest  # noqa: E402

from testbench.suites import tool_contract as T  # noqa: E402


def _log(*pairs):
    return [{"name": n, "args": a} for n, a in pairs]


# ---------- 参数契约 ----------

def test_args_ok():
    log = _log(("write_note", {"title": "h", "body": "w"}),
               ("calc_sum", {"a": 21, "b": 21}))
    assert T.check_args(log) == []


@pytest.mark.parametrize("log,kind", [
    (_log(("calc_sum", {"a": "21", "b": 21})), "wrong_type"),
    (_log(("write_note", {"title": "h"})), "missing_param"),
    (_log(("calc_sum", {"a": 1})), "missing_param"),
])
def test_args_catch(log, kind):
    vs = T.check_args(log)
    assert any(v["kind"] == kind for v in vs)


def test_unknown_tool_not_args_checked():
    # 多余工具的"参数"不归参数断言管(序列断言负责)
    assert T.check_args(_log(("save_memo", {"x": 1}))) == []


# ---------- 序列契约 ----------

def test_sequence_ok():
    log = _log(("list_notes", {}), ("write_note", {}), ("calc_sum", {}))
    assert T.check_sequence(log) == []


def test_sequence_missing_first():
    # 首个期望项缺失时, 后续项仍应被正确识别(不误报 calc_sum 缺失)
    log = _log(("save_memo", {}), ("calc_sum", {}))
    kinds = [(v["kind"], v["tool"]) for v in T.check_sequence(log)]
    assert ("missing_call", "write_note") in kinds
    assert ("extra_call", "save_memo") in kinds
    assert ("missing_call", "calc_sum") not in kinds


def test_sequence_extra_call():
    log = _log(("write_note", {}), ("debug_dump", {}), ("calc_sum", {}))
    vs = T.check_sequence(log)
    assert [(v["kind"], v["tool"]) for v in vs] == \
        [("extra_call", "debug_dump")]


def test_sequence_order_violation():
    # calc_sum 在 write_note 之前: 顺序破坏
    log = _log(("calc_sum", {}), ("write_note", {}))
    vs = T.check_sequence(log)
    assert any(v["kind"] == "missing_call" for v in vs)


# ---------- 变体构造 ----------

def test_variants_shape():
    normal = T.describe_tools(None)
    wt = T.describe_tools("wrong_type")
    mp = T.describe_tools("missing_param")
    ec = T.describe_tools("extra_call")
    assert wt["calc_sum"]["function"]["parameters"]["properties"]["a"]["type"] \
        == "string"
    assert "body" not in mp["write_note"]["function"]["parameters"]\
        ["properties"]
    assert "save_memo" in ec and "save_memo" not in normal
    assert "只读" in ec["write_note"]["function"]["description"]
    with pytest.raises(ValueError):
        T.describe_tools("nope")


def test_recording_wrapper_logs_calls():
    tools, log = T.build_tools(None)
    tools["calc_sum"]["fn"](a=1, b=2)
    assert log == [{"name": "calc_sum", "args": {"a": 1, "b": 2}}]
