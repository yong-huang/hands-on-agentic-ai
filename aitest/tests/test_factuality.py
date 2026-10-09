"""test_factuality — 幻觉检测器离线测试 (docs/aitest.md 项目 6)

拆分/归一化/数字规则/覆盖率子串/裁判解析全部纯函数可测; judge 打桩。
跑法: cd aitest && python3 -m pytest tests/test_factuality.py -q
"""

from testbench.asserts import factuality as F


def test_split_claims_filters_short_and_empty():
    claims = F.split_claims("git commit 会记录版本快照。好的！嗯。push 上传到远程。")
    assert claims == ["git commit 会记录版本快照", "push 上传到远程"]


def test_norm_strips_punct_and_space():
    assert F._norm("HTTP, 默认: 80 端口！") == "HTTP默认80端口"


def test_numeric_all_absent_is_caught_without_judge():
    r = F.check("每次 commit 生成一个 SHA-256 哈希作为标识。", F.SOURCES["git"])
    assert r.has_hallucination
    assert r.unsupported[0]["method"] == "numeric"


def test_number_free_claim_without_judge_never_fabricates_verdict():
    """无 judge 时主题词复用的幻觉句 -> unknown, 不许假装支持或反对。"""
    r = F.check("Python 的 list 和 tuple 都是可变容器。", F.SOURCES["python"])
    assert r.claims[0]["verdict"] == "unknown"
    assert r.has_hallucination is False   # unknown 不算检出, 也不算通过


def test_substring_needs_majority_coverage():
    copied = "git push 用于把本地提交上传到远程仓库"
    r = F.check(copied, F.SOURCES["git"])
    assert r.claims[0] == {"claim": copied, "verdict": "supported",
                           "method": "substring"}
    twisted = "git push 用于把远程仓库的提交拉取到本地"
    r2 = F.check(twisted, F.SOURCES["git"])       # 主题对、方向反 -> 不许放行
    assert r2.claims[0]["verdict"] != "supported"


def test_judge_parsing_and_empty_retry():
    assert F._judge("c", "s", lambda m: "SUPPORTED") == "supported"
    assert F._judge("c", "s", lambda m: "UNSUPPORTED") == "unsupported"
    calls = []

    def flaky(messages):
        calls.append(1)
        return "" if len(calls) == 1 else "SUPPORTED"
    assert F._judge("c", "s", flaky) == "supported" and len(calls) == 2


def test_check_with_fake_judge_end_to_end():
    def judge_supports(messages):
        return "SUPPORTED"
    r = F.check("list 可变而 tuple 不可变。", F.SOURCES["python"],
                chat_fn=judge_supports)
    assert r.claims[0]["verdict"] == "supported" and r.claims[0]["method"] == "judge"


def test_samples_inventory():
    hall = [s for s in F.SAMPLES if s[2]]
    faith = [s for s in F.SAMPLES if not s[2]]
    assert len(hall) == 10 and len(faith) == 10
    assert set(F.SOURCES) == {"git", "http", "perm", "python", "redirect"}
