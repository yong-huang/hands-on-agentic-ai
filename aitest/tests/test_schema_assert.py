"""test_schema_assert — 结构化输出断言测试 (docs/aitest.md 项目 4)

全离线: 规则修复与校验器是纯函数; LLM 重试路径用假 chat_fn 模拟。
跑法: cd aitest && python3 -m pytest tests/test_schema_assert.py -q
"""

from testbench.asserts import schema as S


def _schema(confidence="number"):
    return {"type": "object", "required": ["answer", "confidence"],
            "properties": {"answer": {"type": "string"},
                           "confidence": {"type": confidence}},
            "additionalProperties": False}


# ------------------------------------------------------------
# 提取
# ------------------------------------------------------------

def test_extract_strips_fence_and_prose():
    c, notes = S.extract_json('前言 ```json\n{"a": 1}\n``` 后记')
    assert c == '{"a": 1}' and notes


def test_extract_reports_unterminated():
    c, notes = S.extract_json('{"a": "未闭合')
    assert c is not None and any("截断" in n for n in notes)
    c2, _ = S.extract_json("完全没有花括号")
    assert c2 is None


# ------------------------------------------------------------
# 规则修复
# ------------------------------------------------------------

def test_repair_truncated_string_and_object():
    fixed, fixes = S.repair_rules('{"answer": "Git 提交')
    assert fixed == '{"answer": "Git 提交"}' and fixes


def test_repair_trailing_comma_and_quotes():
    fixed, _ = S.repair_rules('{"a": 1,}')
    assert fixed == '{"a": 1}'
    fixed2, fixes2 = S.repair_rules("{'a': 'x'}")
    assert fixed2 == '{"a": "x"}' and fixes2


# ------------------------------------------------------------
# 校验器
# ------------------------------------------------------------

def test_validate_required_and_types():
    errors = S.validate({"answer": "x"}, _schema())
    assert any("confidence" in e for e in errors)
    errors2 = S.validate({"answer": 1, "confidence": 0.5}, _schema())
    assert any("answer" in e and "string" in e for e in errors2)


def test_validate_rejects_unknown_field():
    errors = S.validate({"answer": "x", "confidence": 0.9, "junk": 1}, _schema())
    assert any("junk" in e for e in errors)


def test_validate_enum():
    schema = {"type": "object", "required": ["grade"],
              "properties": {"grade": {"type": "string", "enum": ["A", "B"]}}}
    assert S.validate({"grade": "C"}, schema)


# ------------------------------------------------------------
# check() 主入口
# ------------------------------------------------------------

def test_check_end_to_end_repairs():
    r = S.check('模型说: ```json\n{"answer": "ok", "confidence": "0.8", "x": 1}\n```')
    assert r.ok and r.data["confidence"] == 0.8 and r.repairs


def test_check_fails_without_chat_fn_on_missing_field():
    r = S.check('{"answer": "只有答案"}')
    assert not r.ok and "confidence" in r.error


def test_check_llm_retry_path_with_fake_chat():
    def fake_chat(messages, **kw):
        assert "confidence" in messages[0]["content"]   # 错误清单被喂回模型
        return '{"answer": "修复后的回答", "confidence": 0.9}'
    r = S.check('{"answer": "只有答案"}', chat_fn=fake_chat)
    assert r.ok and "LLM 修复重试" in r.repairs


def test_selftest_passes_threshold():
    assert S.selftest() is True
