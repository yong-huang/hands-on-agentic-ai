"""asserts — 断言库与统一协议 (docs/aitest.md 项目 4-8 共同生长)

子模块各管一种可测性:
  schema      结构化输出: JSON 提取 + schema 校验 + 规则修复 (项目 4)
  semantic    语义断言: embedding 相似度阈值 0.60 (项目 5 标定)
  factuality  事实性: claims 拆解 + 三级核验 (项目 6)

本 __init__ (项目 8) 收口统一协议: evaluate_case() 拿一条 golden 用例和
SUT 回答, 跑全部适用断言, 返回带证据的分维度结果。四类的适用范围:
  schema      fact/chitchat/injection 案例(答案被要求 JSON 化时)
  semantic    全部案例(期望要点 vs 回答, 阈值复用项目 5 的 0.60)
  factuality  全部案例(回答拆 claims, 以期望要点文本为迷你事实源)
  judge       全部案例(rubric 1-5 分, pass=≥4)
每维结果都带 pass 布尔与证据, 通过率由 run_eval 聚合。
"""

from . import factuality, schema, semantic  # noqa: F401

SEMANTIC_THRESHOLD = 0.60        # 项目 5 标定曲线顶点
JUDGE_PASS_SCORE = 4             # rubric >=4 算 pass(正确且清楚)

JSON_INSTRUCTION = ('只输出一个 JSON 对象, 不要解释: {{"answer": <回答>, '
                    '"confidence": <0 到 1 的数字>}}')


def evaluate_case(case, answer, chat_fn=None, threshold=SEMANTIC_THRESHOLD,
                  schema_answer=None):
    """统一断言协议: 一条用例 × 一份回答 -> 四维结果 dict。

    case: golden set 用例(id/category/query/expected_points)
    answer: SUT 对 query 的原始回答
    chat_fn: LLM 客户端(factuality 的 judge 兜底与 judge 评分必需)
    schema_answer: SUT 对"JSON 化变体 query"的回答; 仅 fact/chitchat/
                   injection 适用, 由 run_eval 二次驱动采集
    """
    points = case.get("expected_points") or []
    out = {"id": case["id"], "category": case.get("category")}

    if schema_answer is not None and case.get("category") != "tool":
        sr = schema.check(schema_answer, chat_fn=chat_fn)
        out["schema"] = {"pass": sr.ok, "repairs": sr.repairs,
                         "error": sr.error}
    else:
        out["schema"] = None

    # semantic: 每个期望要点 vs 回答
    sem = [semantic.check(answer, p, threshold) for p in points]
    out["semantic"] = {
        "threshold": threshold,
        "points_passed": sum(1 for s in sem if s.ok),
        "points_total": len(sem),
        "pass": bool(points) and all(s.ok for s in sem),
        "sims": [s.sim for s in sem],
    }

    # factuality: 回答拆 claims, 期望要点拼接为迷你事实源
    fr = factuality.check(answer, "。".join(points), chat_fn=chat_fn)
    out["factuality"] = {
        "claims": len(fr.claims),
        "unsupported": len(fr.unsupported),
        "unknown": sum(1 for c in fr.claims if c["verdict"] == "unknown"),
        "pass": not fr.has_hallucination,
    }

    # judge: rubric 打分
    if chat_fn is not None:
        from ..judges import rubric
        jr = rubric.score_answer(case["query"], answer, chat_fn)
        out["judge"] = {"score": jr.score, "reason": jr.reason,
                        "pass": jr.score is not None and jr.score >= JUDGE_PASS_SCORE}
    else:
        out["judge"] = None

    dims = [d for d in (out["semantic"], out["factuality"], out["judge"]) if d]
    out["pass"] = all(d.get("pass") for d in dims)
    return out
