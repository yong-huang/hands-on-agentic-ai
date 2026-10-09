"""test_run_eval — 全量评测聚合与协议测试 (docs/aitest.md 项目 8)

聚合数学/协议分派全离线; SUT 与 judge 全打桩。
跑法: cd aitest && python3 -m pytest tests/test_run_eval.py -q
"""

from testbench import run_eval as RE
from testbench.asserts import evaluate_case


def _case(cid="fact_001", category="fact", points=None):
    return {"id": cid, "category": category, "query": "q?",
            "expected_points": points or ["要点一", "要点二"]}


def _offline_chat():
    def chat(messages, **kw):
        content = messages[0]["content"]
        if "SUPPORTED" in content:
            return "SUPPORTED"
        if "评分" in content or "score" in content:
            return '{"score": 5, "reason": "stub"}'
        return "好的"
    return chat


# ------------------------------------------------------------
# evaluate_case 协议分派
# ------------------------------------------------------------

def test_evaluate_case_tool_case_has_no_schema_dim():
    row = evaluate_case(_case(category="tool"), "回答文本",
                        chat_fn=_offline_chat(), schema_answer=None)
    assert row["schema"] is None


def test_evaluate_case_schema_dim_with_answer():
    row = evaluate_case(_case(), "回答文本",
                        chat_fn=_offline_chat(),
                        schema_answer='{"answer": "x", "confidence": 0.9}')
    assert row["schema"]["pass"] is True


def test_evaluate_case_judge_dimension():
    row = evaluate_case(_case(), "回答文本", chat_fn=_offline_chat())
    assert row["judge"]["score"] == 5 and row["judge"]["pass"] is True


def test_evaluate_case_judge_none_without_chat():
    row = evaluate_case(_case(), "回答文本", chat_fn=None)
    assert row["judge"] is None and row["pass"] is False   # 缺 judge 维不算全过


# ------------------------------------------------------------
# 聚合数学
# ------------------------------------------------------------

def test_aggregate_rates_skip_none_dims():
    rows = [
        {"category": "fact", "pass": True, "schema": None,
         "semantic": {"pass": True}, "factuality": {"pass": True},
         "judge": {"pass": True}},
        {"category": "tool", "pass": False, "schema": {"pass": False},
         "semantic": {"pass": True}, "factuality": {"pass": True},
         "judge": {"pass": False}},
    ]
    s = RE._aggregate(rows)
    assert s["rates"]["schema"] == 0.0            # 只有 1 个适用样本
    assert s["rates"]["judge"] == 0.5
    assert s["overall_pass_rate"] == 0.5
    assert s["total_by_category"] == {"fact": 1, "tool": 1}


def test_aggregate_empty():
    s = RE._aggregate([])
    assert s["overall_pass_rate"] == 0.0 and s["rates"]["schema"] is None


# ------------------------------------------------------------
# 离线管道: mini SUT + 脚本 judge, 只验证管线不冒充指标
# ------------------------------------------------------------

def test_offline_pipeline_smoke():
    results = RE.run(dataset="golden_v1", sut="mini", limit=2,
                     offline_chat=True, verbose=False)
    assert len(results["cases"]) == 2
    assert set(results["summary"]["rates"]) == {
        "schema", "semantic", "factuality", "judge"}
    import json
    raw = json.dumps(results)
    assert "offline" in results["meta"] and results["meta"]["offline"] is True
