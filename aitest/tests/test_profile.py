"""test_profile — 非确定性画像指标单测 (docs/aitest.md 项目 3)

指标函数是纯函数, 全离线可测; profile.py 本体通过 importlib 按路径加载。
跑法: cd aitest && python3 -m pytest tests/test_profile.py -q
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE_PY = os.path.join(os.path.dirname(HERE), "03_nondeterminism", "profile.py")

spec = importlib.util.spec_from_file_location("profile_mod", PROFILE_PY)
profile_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile_mod)


def test_exact_consistency_modal_share():
    outs = ["A"] * 7 + ["B"] * 3
    assert profile_mod.exact_consistency(outs) == 0.7
    assert profile_mod.exact_consistency([]) == 0.0


def test_semantic_consistency_bounds():
    assert profile_mod.semantic_consistency(["同一句"] * 5) == 1.0
    assert profile_mod.semantic_consistency(["唯一"]) == 1.0
    # 措辞不同的近义句: 相似度应明显低于全同、高于随机汉字串
    same = ["回归测试是改动后重跑旧用例确认功能未破坏"] * 4
    mixed = same + [" Completely unrelated gibberish xyzzy "]
    sim_uniform = profile_mod.semantic_consistency(same)
    sim_mixed = profile_mod.semantic_consistency(mixed)
    assert sim_mixed < sim_uniform


def test_summarize_shape():
    s = profile_mod.summarize(["A", "A", "B"])
    assert set(s) == {"exact", "semantic", "distinct", "modal"}
    assert s["distinct"] == 2 and abs(s["exact"] - 2 / 3) < 0.01


def test_mock_groups_ordered_variance():
    """MOCK 池: temp0 组近全同, temp0.8 组高度分散 —— 管道演示的前提。"""
    s0, _ = profile_mod.mock_group(0, 8)
    s8, _ = profile_mod.mock_group(8, 8)
    assert profile_mod.exact_consistency(s0) > profile_mod.exact_consistency(s8)
    assert profile_mod.summarize(s8)["distinct"] >= 5
