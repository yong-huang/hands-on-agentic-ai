"""test_datasets — 评测集模块测试 (docs/aitest.md 项目 2)

跑法: cd aitest && python3 -m pytest tests/test_datasets.py -q
"""

import subprocess
import sys

from testbench import datasets


def _case(cid="fact_001", category="fact", query="q?", points=None):
    return {"id": cid, "category": category, "query": query,
            "expected_points": points or ["要点一"]}


# ------------------------------------------------------------
# golden_v1 真实数据集
# ------------------------------------------------------------

def test_golden_v1_validates():
    data = datasets.load("golden_v1")
    assert datasets.validate_dataset(data, "golden_v1") == []
    assert len(data["cases"]) >= 20, "清单要求 ≥20 条"
    cats = {c["category"] for c in data["cases"]}
    assert cats == {"fact", "tool", "injection", "chitchat"}, "四类必须齐备"


def test_golden_v1_ids_unique_and_wellformed():
    ids = [c["id"] for c in datasets.load("golden_v1")["cases"]]
    assert len(ids) == len(set(ids))
    assert all(datasets.ID_PATTERN.match(i) for i in ids)


# ------------------------------------------------------------
# 校验器规则
# ------------------------------------------------------------

def test_validator_reports_all_errors_at_once():
    data = {"schema_version": 2, "cases": [
        _case(cid="BAD-ID"),
        {"id": "tool_001", "category": "tool", "query": " "},
        _case(cid="tool_001"),          # 与上一条 id 重复
    ]}
    errors = datasets.validate_dataset(data)
    assert len(errors) >= 4, "schema_version/坏id/空query/重复id 一次报全"
    assert any("schema_version" in e for e in errors)


# ------------------------------------------------------------
# diff 语义
# ------------------------------------------------------------

def test_diff_added_removed_changed():
    base = {"cases": [_case(cid="fact_001"), _case(cid="tool_001", query="旧任务")]}

    cand = {"cases": [
        _case(cid="fact_001"),                                   # 不变
        _case(cid="tool_001", query="新任务"),                    # 改
        _case(cid="fact_002", category="chitchat", query="hi"),  # 增(借 id 位)
    ]}
    d = datasets.diff_datasets(base, cand)
    # fact_002 在 base 缺席 -> added; 无 removed
    assert d["added"] == ["fact_002"]
    assert d["removed"] == []
    assert ("tool_001", ["query"]) in d["changed"]


def test_diff_removed_case():
    base = {"cases": [_case(cid="fact_001"), _case(cid="tool_001")]}
    cand = {"cases": [_case(cid="fact_001")]}
    d = datasets.diff_datasets(base, cand)
    assert d["removed"] == ["tool_001"] and d["added"] == [] and d["changed"] == []


def test_cli_validate_exit_code():
    import os
    aitest_dir = os.path.dirname(datasets.HERE)   # python -m 需要 aitest/ 为 cwd
    p = subprocess.run(
        [sys.executable, "-m", "testbench.datasets", "validate"],
        cwd=aitest_dir, capture_output=True, text=True)
    assert p.returncode == 0 and p.stdout.startswith("PASS")
