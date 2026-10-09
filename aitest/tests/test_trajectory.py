"""tests/test_trajectory.py — 轨迹评测离线单测 (docs/aitest.md 项目 16)"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, AITEST_DIR)

from testbench.suites import trajectory as T  # noqa: E402


def test_fast_beats_slow():
    fast = T.score_trajectory(T.FAST_TRACE, expected_steps=2)
    slow = T.score_trajectory(T.SLOW_TRACE, expected_steps=2)
    assert fast["score"] > slow["score"]
    assert fast["score"] == 100          # 全绿轨迹: 满项


def test_loop_zero():
    loop = T.score_trajectory(T.LOOP_TRACE, expected_steps=2)
    assert loop["score"] == 0 and loop["loop"] is True
    assert "连续" in loop["loop_reason"] or "共出现" in loop["loop_reason"]


def test_loop_thresholds():
    # 连续 2 次不算循环; 连续 3 次算
    two = [{"tool": "x", "args": {"a": 1}}] * 2
    three = [{"tool": "x", "args": {"a": 1}}] * 3
    assert T.score_trajectory(two)["loop"] is False
    assert T.score_trajectory(three)["loop"] is True


def test_repeat_not_consecutive_still_loop_at_five():
    steps = ([{"tool": "x", "args": {"a": 1}}, {"tool": "y", "args": {}}] * 3)
    # x 出现 3 次、y 3 次: 未到 5, 且不连续 -> 非循环
    assert T.score_trajectory(steps)["loop"] is False
    heavy = [{"tool": "x", "args": {"a": 1}}] + [{"tool": "y", "args": {}}] * 3 \
        + [{"tool": "x", "args": {"a": 1}}] * 4
    assert T.score_trajectory(heavy)["loop"] is True


def test_empty_and_incomplete():
    empty = T.score_trajectory([])
    assert empty["score"] == 0 and empty["steps"] == 0
    incomplete = T.score_trajectory(T.FAST_TRACE, expected_steps=2,
                                    completed=False)
    assert incomplete["score"] == 80     # 满分 100 减 20 收敛分


def test_normalize_generic_action_key():
    pairs = T.normalize([{"action": "search", "args": {"q": "x"}}])
    assert pairs[0][0] == "search"
