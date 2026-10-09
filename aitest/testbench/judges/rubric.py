"""judges.rubric — LLM-as-Judge 校准 (docs/aitest.md 项目 7)

LLM 当判分员之前, 先回答两个问题:
  对齐  judge 的打分和人类标注差多远?   (校准集 20 条人工预标注)
  稳定  同一份卷子再判一遍, 分数会变吗? (temperature=0 重复评 2 轮)

    score_answer(question, answer, chat_fn) -> JudgeResult(score, reason)

judge 输出用项目 4 的结构化断言解析(schema 校验 + 规则修复 + 重试),
解析失败在 judge 这一层不是错误而是"不可用评分", 如实计入。

校准口径(实测见 selftest):
  相邻一致率 |judge-human| <= 1 >= 0.80  (5 档量表上, 差一档以内视为校准)
  重复一致率  两轮同分                    >= 0.90  (temperature=0)
精确一致率同时给出, 不作为验收线 —— 5 档上要求逐分精确属于过度校准。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))            # aitest/

from testbench.asserts import schema as schema_assert  # noqa: E402

RUBRIC = (
    "1 分: 答非所问, 或核心内容错误；"
    "2 分: 有明显事实错误, 或只答对极小部分；"
    "3 分: 大方向正确但含糊其辞、冗余明显, 或关键细节缺失；"
    "4 分: 正确且清楚, 但比最优回答少 1 个要点或细节；"
    "5 分: 正确、完整、具体, 直接可用。"
)

SCORE_SCHEMA = {
    "type": "object",
    "required": ["score", "reason"],
    "properties": {
        "score": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "reason": {"type": "string"},
    },
    "additionalProperties": False,
}

JUDGE_PROMPT = ("你是严格的评分员, 按评分标准给回答打 1-5 分。\n"
                "评分标准: {rubric}\n"
                "问题: {question}\n回答: {answer}\n"
                "只输出 JSON: {{\"score\": <1-5 整数>, \"reason\": \"<30 字内理由>\"}} /no_think")


class JudgeResult:
    def __init__(self, score, reason, repairs=None):
        self.score = score            # int 1-5; None = 不可用评分
        self.reason = reason
        self.repairs = repairs or []

    def __repr__(self):
        return f"JudgeResult(score={self.score}, reason={self.reason!r})"


def score_answer(question, answer, chat_fn):
    """让 judge 按 rubric 打分; 结构断言(项目 4)负责解析与修复重试。"""
    prompt = JUDGE_PROMPT.format(rubric=RUBRIC, question=question, answer=answer)
    raw = chat_fn([{"role": "user", "content": prompt}])
    r = schema_assert.check(raw, SCORE_SCHEMA, chat_fn=chat_fn)
    if not r.ok:
        return JudgeResult(None, f"不可用评分: {r.error}", r.repairs)
    return JudgeResult(r.data["score"], r.data["reason"], r.repairs)


def load_labeled():
    """加载校准集 aitest/datasets/judge_labeled.yaml。"""
    import yaml
    aitest_dir = os.path.dirname(os.path.dirname(HERE))   # testbench/judges -> aitest/
    path = os.path.join(aitest_dir, "datasets", "judge_labeled.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["samples"]


def selftest(chat_fn):
    """校准双指标: 相邻一致率 >=0.80 且 重复一致率 >=0.90。"""
    samples = load_labeled()
    rows = []
    for s in samples:                                   # 第 1 轮
        jr = score_answer(s["question"], s["answer"], chat_fn)
        rows.append((s["id"], s["human_score"], jr.score, jr.reason))
        print(f"  [{s['id']}] 人工={s['human_score']} judge={jr.score} "
              f"{'✅' if jr.score is not None and abs(jr.score - s['human_score']) <= 1 else '❌'}"
              f" ({jr.reason})")
    exact = sum(1 for _, h, j, _ in rows if j == h)
    adjacent = sum(1 for _, h, j, _ in rows if j is not None and abs(j - h) <= 1)
    print(f"\n对齐: 精确一致 {exact}/{len(rows)} · 相邻一致(|Δ|<=1) {adjacent}/{len(rows)}"
          f" (验收 ≥{int(len(rows)*0.8)})")

    mism = 0                                            # 第 2 轮测稳定性
    for s in samples:
        jr = score_answer(s["question"], s["answer"], chat_fn)
        first = next(r[2] for r in rows if r[0] == s["id"])
        if jr.score != first:
            mism += 1
            print(f"  [稳定] {s['id']}: 第 1 轮 {first} -> 第 2 轮 {jr.score}")
    stable_rate = 1 - mism / len(samples)
    print(f"稳定性: 重复评分一致 {len(samples) - mism}/{len(samples)} (验收 ≥{int(len(samples)*0.9)})")
    return adjacent >= len(samples) * 0.8 and stable_rate >= 0.9


if __name__ == "__main__":
    import functools
    qa_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "qa")
    sys.path.insert(0, qa_dir)
    import llm as qa_llm
    chat = functools.partial(qa_llm.chat, num_predict=800, temperature=0)
    sys.exit(0 if selftest(chat) else 1)
