"""test_judge_rubric — judge 校准离线测试 (docs/aitest.md 项目 7)

judge 打桩(固定输出), 验证解析链路/对齐统计/容错; 真机对齐率在 demo 里测。
跑法: cd aitest && python3 -m pytest tests/test_judge_rubric.py -q
"""

from testbench.judges import rubric as R


def _chat_returns(payload):
    return lambda messages, **kw: payload


def test_score_answer_parses_valid_json():
    jr = R.score_answer("q", "a", _chat_returns('{"score": 4, "reason": "正确但少细节"}'))
    assert jr.score == 4 and "少" in jr.reason


def test_score_answer_repairs_prose_wrapped_json():
    jr = R.score_answer("q", "a", _chat_returns('评分如下: {"score": 3, "reason": "含糊"} 谢谢'))
    assert jr.score == 3


def test_score_answer_llm_retry_on_missing_field():
    seq = {"n": 0}

    def chat(messages, **kw):
        seq["n"] += 1
        return ('{"score": 5}' if seq["n"] == 1
                else '{"score": 2, "reason": "补上理由"}')
    jr = R.score_answer("q", "a", chat)
    assert jr.score == 2 and any("LLM 修复重试" in r for r in jr.repairs)


def test_score_answer_unusable_when_unrepairable():
    jr = R.score_answer("q", "a", _chat_returns("我觉得挺好的"))
    assert jr.score is None and "不可用评分" in jr.reason


def test_score_out_of_enum_rejected():
    jr = R.score_answer("q", "a", _chat_returns('{"score": 9, "reason": "超纲"}'))
    assert jr.score is None


def test_load_labeled_inventory():
    samples = R.load_labeled()
    assert len(samples) == 20
    from collections import Counter
    dist = Counter(s["human_score"] for s in samples)
    assert dist == {1: 4, 2: 4, 3: 4, 4: 4, 5: 4}, "五档各 4 条"


def test_selftest_alignment_math_with_stub():
    """打桩 judge 输出=人工分+1(截断到 5): 相邻一致 100%, 稳定性 100%。"""
    samples = R.load_labeled()

    def chat(messages, **kw):
        # 从 prompt 里还原标准答案 -> 查人工分 -> 返回 +1 档
        ans = messages[0]["content"].split("回答: ")[1].rsplit("\n", 1)[0]
        human = next(s["human_score"] for s in samples if s["answer"] == ans)
        score = min(human + 1, 5)
        return '{"score": %d, "reason": "stub"}' % score
    assert R.selftest(chat) is True
