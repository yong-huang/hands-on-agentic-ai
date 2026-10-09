"""test_semantic_assert — 语义断言纯函数测试 (docs/aitest.md 项目 5)

cosine 与阈值逻辑全离线; embed 打桩, 不碰网络。
跑法: cd aitest && python3 -m pytest tests/test_semantic_assert.py -q
"""

import math

import pytest

from testbench.asserts import semantic as SEM


def test_cosine_identical_and_orthogonal():
    assert SEM.cosine([1, 0], [1, 0]) == 1.0
    assert SEM.cosine([1, 0], [0, 1]) == 0.0
    assert math.isclose(SEM.cosine([1, 0], [-1, 0]), -1.0)


def test_cosine_zero_vector_is_zero():
    assert SEM.cosine([0, 0], [1, 2]) == 0.0


def test_calibration_pairs_shape():
    assert len(SEM.PARAPHRASE_PAIRS) == 10
    assert len(SEM.UNRELATED_PAIRS) == 10
    for r, p in SEM.PARAPHRASE_PAIRS + SEM.UNRELATED_PAIRS:
        assert isinstance(r, str) and isinstance(p, str) and r and p


def test_check_threshold_logic(monkeypatch):
    """打桩 embed: 同向/反向向量, 只验阈值判定不动网络。"""
    vectors = {"同向": [1.0, 0.0], "反向": [-1.0, 0.0]}
    monkeypatch.setattr(SEM, "embed", lambda t, **kw: vectors[t])
    r = SEM.check("同向", "同向", threshold=0.5)
    assert r.ok and r.sim == 1.0
    r2 = SEM.check("同向", "反向", threshold=0.5)
    assert not r2.ok and r2.sim == -1.0


def test_semantic_result_fields():
    res = SEM.SemanticResult(True, 0.81234, 0.6)
    assert res.sim == 0.8123 and res.threshold == 0.6


@pytest.mark.skipif(
    __import__("os").environ.get("MOCK") == "1",
    reason="MOCK=1 离线档跳过真机 embedding")
def test_real_embed_dim_and_identical_similarity():
    vec = SEM.embed("探活文本")
    assert len(vec) == 768
    sim = SEM.similarity("回归测试是改后重跑旧用例",
                         "回归测试是在软件修改后重新运行已有测试")
    assert sim > 0.5, "真机等价句相似度应显著高于随机"
